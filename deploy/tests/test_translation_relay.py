from base64 import b64decode, b64encode
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4
import wave

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx
import pytest

from cj_api.translation import DashScopeTranslation, ROUTE, TranslationRelay, VERSION
from cj_auth.interfaces import AdmissionDecision, AdmissionReason, AdmissionStatus, TrustedPrincipal
from cj_usage.authorization_budget import (
    AuthorizationBudget, CNY_SCALE, HK_PRODUCER, M1_ESTIMATED, M1_UNRESOLVED_CNY, MAC_PRODUCER,
    authorization_usage, journal_state,
)
from cj_usage.translation_budget import (
    BEIJING, IMAGE_MODEL, SPEECH_MODEL, TEXT_MODEL, TranslationBudget, TranslationLimit,
)
from deploy.hk.translation_relay import register_translation_route, socket_request, translation_socket
from scripts.m4_budget_transfer import attempts


def _body(kind='text', **content):
    return dict(version=VERSION, request_id=str(uuid4()), kind=kind,
                source_lang='zh', target_lang='en', **content)


def _wav(seconds=1, rate=16_000, *, frames=None):
    raw = BytesIO()
    with wave.open(raw, 'wb') as audio:
        audio.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        audio.writeframes(b'\0\0' * (seconds * rate if frames is None else frames))
    return b64encode(raw.getvalue()).decode()


def _check(token):
    if token == 'internal-fixture':
        principal = TrustedPrincipal('issuer', 'internal', 'app', 1, 1, 2)
        return AdmissionDecision(AdmissionStatus.ALLOWED, AdmissionReason.ACCEPTED, principal)
    if token == 'external-fixture':
        return AdmissionDecision(AdmissionStatus.DENIED, AdmissionReason.NOT_INVITED)
    return AdmissionDecision(AdmissionStatus.DENIED, AdmissionReason.IDENTITY_INVALID)


@pytest.fixture
def budget(tmp_path):
    real = AuthorizationBudget(tmp_path / 'existing', clock=lambda: datetime(2026, 11, 19, 10, tzinfo=BEIJING))
    return TranslationBudget(real)


@pytest.fixture
def interface(budget, request):
    import json
    from types import SimpleNamespace

    calls = []
    def fake(http_request):
        payload = json.loads(http_request.content)
        model = payload['model']
        calls.append(model)
        assert http_request.url.host == 'dashscope.aliyuncs.com'
        assert http_request.headers['Authorization'] == 'Bearer fixture-key'
        if model == IMAGE_MODEL:
            assert http_request.url.path.endswith('/multimodal-generation/generation')
            return httpx.Response(200, json=dict(request_id=str(uuid4()),
                output={'choices': [{'message': {'content': [{'text': '菜單\n火鍋'}]}}]},
                usage={'input_tokens': 30, 'output_tokens': 8}))
        if model == SPEECH_MODEL:
            scenario = getattr(request, 'param', None)
            if scenario == 'http':
                return httpx.Response(400, json={'error': {'message': 'private provider detail'}})
            if scenario == 'subsecond':
                sent = payload['messages'][0]['content'][0]['input_audio']['data']
                with wave.open(BytesIO(b64decode(sent.partition(',')[2])), 'rb') as audio:
                    seconds = audio.getnframes() // audio.getframerate()
                return httpx.Response(200, json=dict(model=model, id=str(uuid4()), choices=[
                    {'message': {'content': '你好'}, 'finish_reason': 'stop'}], usage={'seconds': seconds}))
            usage = {
                'seconds': {'invalid_seconds': 2}.get(scenario, 1),
            } if scenario != 'missing_usage' else {}
            content = '你好'
            assert payload['messages'][0]['content'][0]['input_audio']['format'] == 'wav'
        else:
            assert payload['translation_options'] == {'source_lang': 'Chinese', 'target_lang': 'English'}
            original = payload['messages'][0]['content']
            if original == '供应商夹具失败':
                return httpx.Response(302, headers={'location': 'https://example.test/secret'})
            usage = {'prompt_tokens': 10, 'completion_tokens': 10}
            content = {'你好': 'Hello', '菜單': 'Menu', '火鍋': 'Hot pot'}[original]
        return httpx.Response(200, json=dict(model=model, id=str(uuid4()),
            choices=[{'message': {'content': content}, 'finish_reason': 'stop'}], usage=usage))

    class Connection:
        def __init__(self, host, timeout):
            self.host = host

        def connect(self):
            assert self.host == 'dashscope.aliyuncs.com'

        def request(self, method, path, *, body, headers):
            assert self.auto_open is False
            self.reply = fake(httpx.Request(method, 'https://' + self.host + path, content=body, headers=headers))

        def getresponse(self):
            status = self.reply.status_code
            frame = (f'HTTP/1.1 {status} Fixture\r\nContent-Length: {len(self.reply.content)}\r\n\r\n'.encode()
                     + self.reply.content)
            response = self.response_class(SimpleNamespace(makefile=lambda _: BytesIO(frame)))
            response.begin()
            return response

        def close(self):
            pass

    with TemporaryDirectory(prefix='g2c-tr-', dir='/tmp') as directory:
        path = Path(directory) / 'relay.sock'
        relay = TranslationRelay(SimpleNamespace(check=_check), budget,
                                 DashScopeTranslation('fixture-key', connection=Connection),
                                 lambda issuer, subject: subject)
        with translation_socket(relay, path=path):
            app = FastAPI()
            register_translation_route(app, send=lambda token, raw: socket_request(token, raw, path=path))
            with TestClient(app) as client:
                yield client, calls, budget.authorization


def _post(client, body, actor='internal-fixture'):
    return client.post(ROUTE, json=body, headers={'Authorization': f'Bearer {actor}'})


def test_all_inputs_use_internal_identity_and_metadata_only(interface):
    client, calls, ledger = interface
    text = _body(text='你好')
    assert _post(client, text, actor='external-fixture').status_code == 403
    assert _post(client, text, actor='invalid-fixture').status_code == 401
    assert calls == []
    expected = [{'source_text': '你好', 'translated_text': 'Hello'}]
    assert _post(client, text).json() == dict(version=VERSION, kind='text', items=expected)
    assert _post(client, text).status_code == 409
    speech = _post(client, _body('speech', media=_wav()))
    assert speech.json() == dict(version=VERSION, kind='speech', items=expected)
    media = b64encode(b'\x89PNG\r\n\x1a\nfixture-image').decode()
    photo = _post(client, _body('image', media=media))
    assert photo.json()['items'] == [
        {'source_text': '菜單', 'translated_text': 'Menu'}, {'source_text': '火鍋', 'translated_text': 'Hot pot'},
    ]
    assert calls == [TEXT_MODEL, SPEECH_MODEL, TEXT_MODEL, IMAGE_MODEL, TEXT_MODEL, TEXT_MODEL]
    journal = repr(ledger.inspect())
    assert not any(secret in journal for secret in ('你好', '菜單', 'Hot pot', media, 'fixture-key', 'internal-fixture'))
    with ledger.connect() as db:
        _, estimates, holds = authorization_usage(db)
    assert estimates['model'] > 0
    assert not holds.get('place')


def test_provider_redirect_is_not_followed_or_retried(interface):
    client, calls, ledger = interface
    body = _body(text='供应商夹具失败')
    assert _post(client, body).status_code == 502
    assert _post(client, body).status_code == 409
    assert calls == [TEXT_MODEL]
    assert ledger.inspect()[0]['state'] == 'INTENT'


@pytest.mark.parametrize(('interface', 'reason', 'upstream_http'), [
    ('http', 'supplier_http', 400),
    ('missing_usage', 'supplier_receipt_shape', 200),
    ('invalid_seconds', 'speech_usage_seconds', 200),
], indirect=['interface'])
def test_asr_502_exposes_only_diagnostics_and_keeps_the_original_hold(
        interface, reason, upstream_http, caplog):
    client, calls, ledger = interface
    body = _body('speech', media=_wav())
    reply = _post(client, body)
    assert reply.status_code == 502
    assert reply.json() == {'version': VERSION, 'error': 'provider_unavailable'}
    assert _post(client, body).status_code == 409
    assert calls == [SPEECH_MODEL]
    assert [row['state'] for row in ledger.inspect()] == ['INTENT']
    messages = [row.getMessage() for row in caplog.records if row.name == 'cj_api.translation']
    assert messages == [
        f'G2C_TRANSLATION_ASR_FAILURE reason={reason} supplier_http={upstream_http}',
    ]
    assert 'private provider detail' not in caplog.text


@pytest.mark.parametrize('interface', ['subsecond'], indirect=True)
def test_subsecond_speech_keeps_the_first_billed_second_and_returns_a_translation(interface):
    client, calls, ledger = interface
    response = _post(client, _body('speech', media=_wav(frames=14959)))
    assert response.status_code == 200
    assert response.json()['items'] == [{'source_text': '你好', 'translated_text': 'Hello'}]
    assert calls == [SPEECH_MODEL, TEXT_MODEL]
    rows = ledger.inspect()
    assert len(rows) == 2 and all(row['state'] == 'RECEIVED' for row in rows)


def test_reject_wrong_encoding_and_disallow_provider_url(interface):
    client, calls, _ = interface
    assert _post(client, _body('speech', media=_wav(rate=8_000))).status_code == 400
    assert _post(client, _body('image', media='https://example.test/person.png')).status_code == 400
    assert _post(client, {**_body(text='你好'), 'model': 'qwen-max'}).status_code == 400
    assert calls == []


def test_voice_limit_is_atomic_and_isolated_per_owner(budget):
    for _ in range(29):
        operation = budget.operation('owner-a', uuid4(), 'speech', 60)
        budget.begin(operation, 0, SPEECH_MODEL)
        budget.finish(operation, 0, SPEECH_MODEL, str(uuid4()), {'seconds': 60})

    def submit(_):
        try:
            budget.begin(budget.operation('owner-a', uuid4(), 'speech', 60), 0, SPEECH_MODEL)
            return 'reserved'
        except TranslationLimit:
            return 'denied'

    with ThreadPoolExecutor(max_workers=2) as workers:
        assert sorted(workers.map(submit, range(2))) == ['denied', 'reserved']
    budget.begin(budget.operation('owner-b', uuid4(), 'speech', 60), 0, SPEECH_MODEL)


def test_translation_ceiling_reserves_unknown_without_using_other_sublimits(budget, monkeypatch):
    from cj_usage import translation_budget

    monkeypatch.setattr(translation_budget, 'SUBLIMIT', CNY_SCALE)
    budget.begin(budget.operation('owner-a', uuid4(), 'text', 1), 0, TEXT_MODEL)
    with pytest.raises(TranslationLimit):
        budget.begin(budget.operation('owner-b', uuid4(), 'text', 1), 0, TEXT_MODEL)
    with budget.authorization.connect() as db:
        _, estimates, holds = authorization_usage(db)
    assert holds['model'] >= CNY_SCALE


def _translation_journal(budget):
    budget.authorization.begin('original-hold', 'model', b'existing non-translation intent')
    text = budget.operation('scope-fixture', uuid4(), 'text', 1)
    budget.begin(text, 0, TEXT_MODEL)
    budget.finish(text, 0, TEXT_MODEL, str(uuid4()), {'input_tokens': 12, 'output_tokens': 5})
    speech = budget.operation('scope-fixture', uuid4(), 'speech', 2)
    budget.begin(speech, 0, SPEECH_MODEL)
    return text.identifier(0), speech.identifier(0)


def test_hk_proof_keeps_translation_intent_and_receipt_in_signed_digest(budget):
    _translation_journal(budget)
    with budget.authorization.connect() as db:
        db.execute('UPDATE producer SET identity=?', (HK_PRODUCER,))
        original = db.execute('SELECT * FROM attempt ORDER BY id').fetchall()
        assert attempts(db) == journal_state(db)
        assert db.execute('SELECT * FROM attempt ORDER BY id').fetchall() == original
        _, estimates, holds = authorization_usage(db)
        assert estimates['model'] > 0 and holds['model'] == (M1_UNRESOLVED_CNY + 2) * CNY_SCALE


@pytest.mark.parametrize('settled', [False, True])
def test_hk_export_can_read_tts_history_without_a_live_tts_route(budget, settled):
    ledger = budget.authorization
    model = 'qwen3-tts-flash'
    operation = budget.operation('scope-fixture', uuid4(), 'tts', 1)
    budget.begin(operation, 0, model)
    if settled:
        budget.finish(operation, 0, model, str(uuid4()), {'characters': 4})
    with ledger.connect() as db:
        db.execute('UPDATE producer SET identity=?', (HK_PRODUCER,))
        assert attempts(db) == journal_state(db)
        _, estimates, holds = authorization_usage(db)
    assert estimates['model'] == M1_ESTIMATED + (3200 if settled else 0)
    assert holds['model'] == (M1_UNRESOLVED_CNY + (0 if settled else 1)) * CNY_SCALE


def test_mac_transfer_keeps_rejecting_runtime_translation_attempts(budget):
    _translation_journal(budget)
    with budget.authorization.connect() as db:
        with pytest.raises(ValueError, match='original_attempt_history_invalid'):
            attempts(db)


@pytest.mark.parametrize('producer', [MAC_PRODUCER, HK_PRODUCER, 'sealed-for-' + HK_PRODUCER])
def test_translation_receipt_cannot_escape_validation_by_renaming_identity(budget, producer):
    text = budget.operation('scope-fixture', uuid4(), 'text', 1)
    budget.begin(text, 0, TEXT_MODEL)
    budget.finish(text, 0, TEXT_MODEL, str(uuid4()), {'input_tokens': 12, 'output_tokens': 5})
    with budget.authorization.connect() as db:
        db.execute('UPDATE producer SET identity=?', (producer,))
        db.execute('UPDATE attempt SET id=? WHERE id=?',
                   (text.identifier(0).replace('translation.1:', 'translation.0:'), text.identifier(0)))
        with pytest.raises(ValueError, match='original_attempt_history_invalid'):
            attempts(db)


@pytest.mark.parametrize('source,field,value', [
    ('pending', 'input_sha', '0' * 64),
    ('pending', 'receipt', None),
    ('received', 'receipt', '{"unexpected":"metadata"}'),
    ('pending', 'kind', 'place'),
])
def test_hk_proof_rejects_tampered_translation_rows(budget, source, field, value):
    text, speech = _translation_journal(budget)
    with budget.authorization.connect() as db:
        db.execute('UPDATE producer SET identity=?', (HK_PRODUCER,))
        db.execute('UPDATE attempt SET ' + field + '=? WHERE id=?',
                   (value, speech if source == 'pending' else text))
        with pytest.raises(ValueError, match='original_attempt_history_invalid'):
            attempts(db)


@pytest.mark.parametrize('kind,model,limit', [('text', TEXT_MODEL, 300), ('image', IMAGE_MODEL, 50)])
def test_text_and_image_daily_counts_are_separate_and_exact(budget, kind, model, limit):
    for _ in range(limit):
        operation = budget.operation('member', uuid4(), kind, 1)
        budget.begin(operation, 0, model)
        budget.finish(operation, 0, model, str(uuid4()), {'input_tokens': 10, 'output_tokens': 5})
    with pytest.raises(TranslationLimit, match='daily translation'):
        budget.begin(budget.operation('member', uuid4(), kind, 1), 0, model)
    other_kind, other_model = ('image', IMAGE_MODEL) if kind == 'text' else ('text', TEXT_MODEL)
    budget.begin(budget.operation('member', uuid4(), other_kind, 1), 0, other_model)


def test_smoke_requires_both_directions_and_original_receipts(budget):
    from uuid import UUID
    from deploy.hk import server_smoke, translation_smoke

    events = [{'kind': 'translation_requirement', 'required': True}]
    sent = []
    scope = 'internal'

    def send(token, route, *, document):
        assert token == 'synthetic-fixture' and route == ROUTE and document['kind'] == 'text'
        source = document['source_lang']
        sent.append(source)
        operation = budget.operation(scope, UUID(document['request_id']), 'text', 1)
        budget.begin(operation, 0, TEXT_MODEL)
        budget.finish(operation, 0, TEXT_MODEL, str(uuid4()), {'input_tokens': 10, 'output_tokens': 5})
        answer = 'Hello!' if source == 'zh' else '早上好。'
        return dict(version=VERSION, kind='text',
                    items=[dict(source_text=document['text'], translated_text=answer)]), None

    translation_smoke.checks(budget.authorization, scope, 'synthetic-fixture',
                             lambda: True, send, events.append, server_smoke.SmokeResult, ready=True)
    assert sent == ['zh', 'en']
    assert [row['status'] for row in events[1:]] == ['PASS', 'PASS']
    assert translation_smoke.complete(events)
    assert not translation_smoke.complete(events[:-1])


def test_smoke_stops_after_a_rejected_translation(budget):
    from deploy.hk import server_smoke, translation_smoke

    calls, events = [], []

    def send(token, route, *, document):
        calls.append(document['source_lang'])
        raise server_smoke.SmokeResult('FAIL', 'http_403')

    translation_smoke.checks(budget.authorization, 'internal', 'synthetic-fixture',
                             lambda: True, send, events.append, server_smoke.SmokeResult, ready=True)
    assert calls == ['zh']
    assert [row['status'] for row in events] == ['FAIL', 'UNRUN']
    assert [row['conservative_cny_1e7'] for row in events] == [CNY_SCALE, 0]
    assert [row['unresolved_attempts'] for row in events] == [1, 0]


def test_smoke_accounts_for_the_original_translation_hold_without_resending(budget):
    from uuid import UUID
    from deploy.hk import server_smoke, translation_smoke

    calls, events = [], []

    def send(token, route, *, document):
        calls.append(document['source_lang'])
        operation = budget.operation('internal', UUID(document['request_id']), 'text', 1)
        budget.begin(operation, 0, TEXT_MODEL)
        raise server_smoke.SmokeResult('UNKNOWN', 'http_timeout')

    assert translation_smoke.checks(budget.authorization, 'internal', 'synthetic-fixture',
        lambda: True, send, events.append, server_smoke.SmokeResult, ready=True) == events
    assert calls == ['zh'] and [row['status'] for row in events] == ['UNKNOWN', 'UNRUN']
    assert [row['state'] for row in budget.authorization.inspect()] == ['INTENT']
    assert events[0]['conservative_cny_1e7'] == CNY_SCALE and events[0]['estimated_cny_1e7'] == 0


def test_revocation_during_tls_connect_blocks_the_supplier_post(budget):
    import json
    from types import SimpleNamespace
    from cj_api.translation import TranslationError, TranslationInput

    current = 'internal-fixture'

    class Connection:
        def __init__(self, host, timeout):
            assert host == 'dashscope.aliyuncs.com'

        def connect(self):
            nonlocal current
            current = 'external-fixture'
            assert budget.authorization.inspect()[0]['state'] == 'INTENT'

        def request(self, *args, **kwargs):
            pytest.fail('revoked member reached the supplier HTTP POST')

        def close(self):
            pass

    relay = TranslationRelay(SimpleNamespace(check=lambda _: _check(current)), budget,
                             DashScopeTranslation('fixture-key', connection=Connection),
                             lambda issuer, subject: subject)
    item = TranslationInput.read(json.dumps(_body(text='你好')))
    owner = relay.authorize('formerly-valid')
    with pytest.raises(TranslationError, match='not_enabled'):
        relay.translate('formerly-valid', item, owner)
    assert budget.authorization.inspect()[0]['state'] == 'INTENT'


def test_bad_optional_roster_leaves_the_existing_worker_loop_available(monkeypatch, capsys):
    from deploy.hk.configuration import TRANSLATION_INTERNAL_SUBJECTS
    from deploy.hk.translation_relay import active_translation

    monkeypatch.setenv(TRANSLATION_INTERNAL_SUBJECTS, '{"invalid": "fixture"}')
    with active_translation(None, None):
        pass
    assert capsys.readouterr().err.strip() == 'ALERT translation_relay_unavailable'


def test_completed_smoke_rejects_missing_translation_requirement_or_evidence(monkeypatch):
    from deploy.hk import server_smoke

    monkeypatch.setattr(server_smoke, 'overlap_witness', lambda *args: True)
    common = [dict(kind='case', case=case, status='PASS', bound_model_attempts=[])
              for case, _ in server_smoke.CASES]
    for row in common:
        if row['case'].endswith('.plan'):
            conversation, message, ref = 'fixture-' + row['case'], str(uuid4()), str(uuid4())
            row.update(conversation_id=conversation, message_id=message, dispatch_ms=0,
                       polls=[dict(ref=ref, http=200, start_ms=1, end_ms=2)],
                       structured_plan=dict(source='timeline_trip', days=3, conversation_id=conversation,
                                            message_id=message, ref=ref, start_ms=1, end_ms=2))
    common += [dict(kind='history', status='PASS'),
               dict(kind='cost', conservative_cny_1e7=0, line_usage_delta_cny_1e7=0)]
    required = dict(kind='translation_requirement', required=True)
    disabled = dict(kind='translation_requirement', required=False)
    unavailable = dict(status='UNKNOWN', concurrency='UNRUN', reason='translation_smoke_incomplete')
    assert server_smoke.decide(common, []) == unavailable
    assert server_smoke.decide(common + [required], []) == unavailable
    assert server_smoke.decide(common + [disabled], [])['status'] == 'PASS'
    translations = [dict(kind='translation', language=language, status='PASS',
                         conservative_cny_1e7=100, estimated_cny_1e7=100, unresolved_attempts=0)
                    for language in ('zh', 'en')]
    assert server_smoke.decide(common + [required, *translations], [])['status'] == 'UNKNOWN'
    assert server_smoke.decide(common + [disabled, *translations], []) == unavailable

    translation_cost = dict(conservative_cny_1e7=200, estimated_cny_1e7=200, unresolved_attempts=0)
    def cost_for(dialogue_amount):
        dialogue_cost = dict(conservative_cny_1e7=dialogue_amount, estimated_cny_1e7=dialogue_amount,
                             unresolved_attempts=0)
        return dict(kind='cost', conservative_cny_1e7=dialogue_amount+200,
                    estimated_cny_1e7=dialogue_amount+200, unresolved_attempts=0,
                    line_usage_delta_cny_1e7=dialogue_amount,
                    dialogue_cost=dialogue_cost, translation_cost=translation_cost)

    for dialogue_amount in (3*CNY_SCALE+1, 5*CNY_SCALE):
        verdict = server_smoke.decide(common[:-1] + [cost_for(dialogue_amount), required, *translations], [])
        assert verdict['reason'] == 'smoke_cost_boundary_unconfirmed'
    good = cost_for(3*CNY_SCALE)
    assert server_smoke.decide(common[:-1] + [good, required, *translations], [])['status'] == 'PASS'
    incomplete = dict(good, conservative_cny_1e7=3*CNY_SCALE)
    assert server_smoke.decide(common[:-1] + [incomplete, required, *translations], [])['status'] == 'UNKNOWN'


@pytest.mark.parametrize('headers,encode', [
    (b'Content-Length: 2000\r\n', lambda body: body),
    (b'Transfer-Encoding: chunked\r\n',
     lambda body: f'{len(body):x}\r\n'.encode() + body + b'\r\n0\r\n'),
])
def test_parseable_but_truncated_provider_response_keeps_hold(budget, headers, encode):
    import json
    from types import SimpleNamespace
    from cj_api.translation import TranslationError, TranslationInput

    body = json.dumps(dict(model=TEXT_MODEL, id=str(uuid4()),
        choices=[dict(message={'content': 'Hello'}, finish_reason='stop')],
        usage={'prompt_tokens': 10, 'completion_tokens': 2})).encode()

    class Connection:
        def __init__(self, host, timeout):
            pass

        def connect(self):
            pass

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            wire = b'HTTP/1.1 200 OK\r\n' + headers + b'\r\n' + encode(body)
            response = self.response_class(SimpleNamespace(makefile=lambda _: BytesIO(wire)))
            response.begin()
            return response

        def close(self):
            pass

    relay = TranslationRelay(SimpleNamespace(check=_check), budget,
                             DashScopeTranslation('fixture-key', connection=Connection),
                             lambda issuer, subject: subject)
    item = TranslationInput.read(json.dumps(_body(text='你好')))
    with pytest.raises(TranslationError, match='provider_unavailable'):
        relay.translate('internal-fixture', item, 'internal')
    assert budget.authorization.inspect()[0]['state'] == 'INTENT'


def test_paid_authorization_expiring_during_tls_blocks_the_post(budget):
    import json
    from types import SimpleNamespace
    from cj_api.translation import TranslationInput
    from cj_usage.metered_exit import BudgetUnknown

    expired = False

    def authorization():
        if expired:
            raise BudgetUnknown('fixture authorization expired')

    class Connection:
        def __init__(self, host, timeout):
            pass

        def connect(self):
            nonlocal expired
            expired = True

        def request(self, *args, **kwargs):
            pytest.fail('expired paid authorization reached HTTP POST')

        def close(self):
            pass

    budget.authorization.authorization_guard = authorization
    relay = TranslationRelay(SimpleNamespace(check=_check), budget,
                             DashScopeTranslation('fixture-key', connection=Connection),
                             lambda issuer, subject: subject)
    item = TranslationInput.read(json.dumps(_body(text='你好')))
    with pytest.raises(BudgetUnknown, match='fixture authorization expired'):
        relay.translate('internal-fixture', item, 'internal')
    assert budget.authorization.inspect()[0]['state'] == 'INTENT'


def test_smoke_uses_only_worker_state_agreeing_with_configuration(monkeypatch):
    from datetime import timedelta, timezone
    from deploy.hk import server_smoke, translation_relay
    from deploy.hk.configuration import TRANSLATION_INTERNAL_SUBJECTS

    start = datetime(2026, 11, 19, 11, tzinfo=timezone.utc)
    class Clock:
        @staticmethod
        def now(tz):
            return start
    monkeypatch.setattr(server_smoke, 'datetime', Clock)
    monkeypatch.setattr(translation_relay, 'translation_state', lambda: False)
    monkeypatch.setenv(TRANSLATION_INTERNAL_SUBJECTS, '["internal"]')
    events = []
    monkeypatch.setattr(server_smoke, 'print_json', events.append)
    assert server_smoke.run(None, None, None, None, None, start, start + timedelta(minutes=5)) == 2
    assert events == [dict(kind='batch', status='UNKNOWN', reason='translation_worker_state_unavailable')]


def test_state_reply_is_private_to_the_worker_and_rejects_other_pid(monkeypatch):
    import os
    import socket
    import struct
    from deploy.hk.translation_relay import translation_state

    real = socket.socket.getsockopt
    option = getattr(socket, 'SO_PEERCRED', 20031)
    monkeypatch.setattr(socket, 'SO_PEERCRED', option, raising=False)
    def peer(connection, level, code, *args):
        if level == socket.SOL_SOCKET and code == option:
            return struct.pack('3i', os.getpid(), os.getuid(), os.getgid())
        return real(connection, level, code, *args)
    monkeypatch.setattr(socket.socket, 'getsockopt', peer)
    with TemporaryDirectory(prefix='g2c-tr-state-', dir='/tmp') as directory:
        path = Path(directory) / 'relay.sock'
        with translation_socket(None, path=path):
            assert translation_state(path, worker_pid=os.getpid()) is False
            with pytest.raises(ValueError, match='active worker'):
                translation_state(path, worker_pid=os.getpid() + 1)
            status, body = socket_request('internal-fixture', b'{}', path=path)
            assert status == 503 and body == dict(version=VERSION, error='unavailable')


def test_intentionally_disabled_translation_returns_403_through_public_api(monkeypatch):
    from deploy.hk import translation_relay
    from deploy.hk.configuration import TRANSLATION_INTERNAL_SUBJECTS

    monkeypatch.delenv(TRANSLATION_INTERNAL_SUBJECTS, raising=False)
    with TemporaryDirectory(prefix='g2c-tr-off-', dir='/tmp') as directory:
        path = Path(directory) / 'relay.sock'
        monkeypatch.setattr(translation_relay, 'translation_socket',
                            lambda relay, **options: translation_socket(relay, path=path, **options))
        with translation_relay.active_translation(None, None):
            app = FastAPI()
            register_translation_route(app, send=lambda token, raw: socket_request(token, raw, path=path))
            with TestClient(app) as client:
                # A bounded media body must not turn early socket closure into an API 503.
                data = b64encode(b'\x89PNG\r\n\x1a\n' + b'x' * 1024 * 1024).decode()
                for payload in (_body(text='你好'), _body('image', media=data)):
                    response = _post(client, payload)
                    assert response.status_code == 403
                    assert response.json() == dict(version=VERSION, error='not_enabled')
