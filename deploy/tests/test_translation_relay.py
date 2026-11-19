from base64 import b64encode
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
from cj_usage.authorization_budget import AuthorizationBudget, CNY_SCALE, authorization_usage
from cj_usage.translation_budget import (
    BEIJING, IMAGE_MODEL, SPEECH_MODEL, TEXT_MODEL, TranslationBudget, TranslationLimit,
)
from deploy.hk.translation_relay import register_translation_route, socket_request, translation_socket


def _body(kind='text', **content):
    return dict(version=VERSION, request_id=str(uuid4()), kind=kind,
                source_lang='zh', target_lang='en', **content)


def _wav(seconds=1, rate=16_000):
    raw = BytesIO()
    with wave.open(raw, 'wb') as audio:
        audio.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        audio.writeframes(b'\0\0' * (seconds * rate))
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
def interface(budget):
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
            usage = {'seconds': 1}
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
            stream = BytesIO(self.reply.content)
            return SimpleNamespace(status=self.reply.status_code, read1=stream.read1, close=stream.close)

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
    common += [dict(kind='history', status='PASS'),
               dict(kind='cost', conservative_cny_1e7=0, line_usage_delta_cny_1e7=0)]
    required = dict(kind='translation_requirement', required=True)
    disabled = dict(kind='translation_requirement', required=False)
    unavailable = dict(status='UNKNOWN', concurrency='UNRUN', reason='translation_smoke_incomplete')
    assert server_smoke.decide(common, []) == unavailable
    assert server_smoke.decide(common + [required], []) == unavailable
    assert server_smoke.decide(common + [disabled], [])['status'] == 'PASS'
    translations = [dict(kind='translation', language=language, status='PASS') for language in ('zh', 'en')]
    assert server_smoke.decide(common + [required, *translations], [])['status'] == 'PASS'
    assert server_smoke.decide(common + [disabled, *translations], []) == unavailable
