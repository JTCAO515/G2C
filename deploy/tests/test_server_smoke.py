from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import sqlite3

import pytest

from cj_message.lio_context import CAPABILITIES_EN, CAPABILITIES_ZH, display_answer
from cj_usage.authorization_budget import CNY_SCALE, journal_state
from cj_usage.sublimits import policy
from deploy.hk.app_smoke_ceiling import BASELINE
from deploy.hk import server_smoke as smoke
from deploy.hk import server_smoke_budget as ceiling


@pytest.mark.parametrize(('case', 'body', 'valid'), [
    ('zh.identity', '我是 Lio，你在中国旅行时的智能助手。', True),
    ('en.identity', 'I am Lio, your travel assistant for China.', True),
    ('en.identity', 'Welcome to China. How can I help you?', False),
    ('en.identity', 'I am not Lio. I am a different travel assistant.', False),
    ('zh.identity', '我不是 Lio，我是另一个旅行助手。', False),
    ('en.capability', 'I can plan your itinerary and explain local transport.', False),
    ('en.capability', 'I offer no travel assistance. Please ask someone to plan your itinerary.', False),
    ('en.capability', 'I have no ability to plan travel itineraries or explain local transport.', False),
    ('en.capability', 'I can’t plan your days. Someone else can help.', False),
    ('en.capability', 'I don’t plan your days. Someone else can help.', False),
    ('en.capability', 'I won’t plan your days. Someone else can help.', False),
    ('en.capability', 'Please plan your days before leaving home.', False),
    ('en.capability', 'It is not true that I can plan your days. Someone else can help.', False),
    ('en.capability', "Here's how I can help:\n\n- **Plan your days:** No service is available.", False),
    ('en.capability', "Here's how I can help:\n\n- **Plan your days:**\nAsk someone else for assistance.", False),
    ('en.capability', 'How can I help you? Where would you like to start?', False),
    ('zh.capability', '我可以规划行程，解释当地交通和支付。', False),
    ('zh.capability', '我做不了行程规划，也不会推荐景点，请找别人。', False),
    ('zh.capability', '抱歉，行程和景点这些我都帮不上忙。', False),
    ('en.capability', CAPABILITIES_EN + '\nI cannot plan any itinerary.', False),
    ('en.capability', 'It is not true that I can do any of the following.\n' + CAPABILITIES_EN, False),
    ('en.capability', '- **Plan your days: no service is available here.**', False),
    ('zh.plan', '第一天\n上午游览故宫和天安门广场，下午去景山公园。\n第二天\n乘车去慕田峪长城，在景区步行并参观烽火台。\n第三天\n上午参观颐和园并沿昆明湖步行，下午去前门。', True),
    ('en.plan', '**Day 1: City centre**\nWalk through the Forbidden City and climb Jingshan.\n**Day 2: Great Wall**\nTake the morning shuttle to Mutianyu and walk between towers.\n**Day 3: Gardens**\nTour the Summer Palace and walk along the lake.', True),
    ('en.plan', 'Day 1: Forbidden City.\nDay 2: TBD.\nDay 3: Summer Palace.', False),
    ('zh.plan', '第一天：故宫没有安排。\n第二天：长城没有安排。\n第三天：天坛没有安排。', False),
    ('en.plan', 'Day 1: No activity is planned at the Forbidden City.\nDay 2: No activity is planned at the Great Wall.\nDay 3: No activity is planned at the Temple of Heaven.', False),
    ('zh.plan', '第一天：不建议参观故宫。\n第二天：不建议游览长城。\n第三天：不建议参观天坛。', False),
    ('en.plan', 'Day 1: You should not visit the Forbidden City.\nDay 2: Do not visit the Great Wall.\nDay 3: Avoid visiting the Temple of Heaven.', False),
    ('zh.plan', '第一天：你想参观故宫吗？\n第二天：你想游览长城吗？\n第三天：你想参观天坛吗？', False),
    ('en.plan', 'Day 1: Would you like to visit the Forbidden City?\nDay 2: Would you like to tour the Great Wall?\nDay 3: Would you like to visit the Temple of Heaven?', False),
    ('zh.plan', '第一天：无法参观故宫。\n第二天：没法游览长城。\n第三天：不能参观天坛。', False),
    ('en.plan', 'Day 1: It is not possible to visit the Forbidden City.\nDay 2: You are unable to tour the Great Wall.\nDay 3: It is impossible to visit the Temple of Heaven.', False),
    ('en.plan', 'Day 1: The sign says “visit the Forbidden City”.\nDay 2: A brochure mentions “tour the Great Wall”.\nDay 3: A book says “visit the Temple of Heaven”.', False),
    ('en.plan', 'Could you give me your hotel details first? Then I can plan all three days.', False),
])
def test_real_body_is_required(case, body, valid):
    assert smoke.valid_answer(case, body) is valid


@pytest.mark.parametrize(('case', 'body', 'valid'), [
    ('en.plan', '**Day 1:** Visit the Forbidden City.\n**Day 2:** Walk through Jingshan.\n'
     '**Day 3:** Hike along the Great Wall at Mutianyu.', True),
    ('en.plan', 'Day 1\n- **Morning:** Visit the Forbidden City.\n'
     'Day 2\n- **Afternoon:** Tour the Summer Palace.\nDay 3\n- **Morning:** Walk through Jingshan.', True),
    ('zh.plan', '第一天\n- **上午：**参观故宫。\n第二天\n- **下午：**游览颐和园。\n'
     '第三天\n- **上午：**参观天坛。', True),
    ('en.plan', '**Day 1:** Visit the Forbidden City.\n**Day 2:** Walk through Jingshan.\n'
     '**Day 3:** Do not hike along the Great Wall.', False),
    ('en.plan', 'Day 1: Visit the Forbidden City.\nDay 2: Walk through Jingshan.\n'
     'Day 3\n- **Morning:** Great Wall.', False),
    ('en.plan', 'Day 1: Visit the Forbidden City.\nDay 2: Walk through Jingshan.\n'
     'Day 3: Hike along the Great Wall at Mutianyu — canceled.', False),
    ('en.plan', 'Day 1: Visit the Forbidden City.\nDay 2: Walk through Jingshan.\n'
     'Day 3\n- **Morning:** Visit the Temple of Heaven — cancelled.', False),
    ('en.plan', 'Day 1: Visit the Forbidden City.\nDay 2: Walk through Jingshan.\n'
     'Day 3: Hike along the Great Wall at Mutianyu — called off.', False),
    ('zh.plan', '第一天：参观故宫。\n第二天：游览颐和园。\n第三天\n- **上午：**不要参观天坛。', False),
])
def test_plan_accepts_activities_with_formatted_schedule_labels(case, body, valid):
    assert smoke.valid_answer(case, body) is valid


@pytest.mark.parametrize(('case', 'body', 'valid'), [
    ('en.plan', 'Day 1: Visit the Forbidden City. Day 2: Hike the Great Wall. Day 3: Explore the Temple of Heaven.', True),
    ('en.plan', 'Day 1: Visit the Forbidden City. Day 2: Explore the Great Wall. '
     'Day 3: Wander through the Summer Palace.', True),
    ('en.plan', 'Day 1: Visit the Forbidden City. Day 2: Explore the Great Wall. '
     'Day 3: Wander through the Summer Palace — canceled.', False),
    ('en.plan', '**Day 1:** Visit the Forbidden City. **Day 2:** Walk through Jingshan. '
     '**Day 3:** Explore the Summer Palace.', True),
    ('zh.plan', '第一天：参观故宫。第二天：游览颐和园。第三天：参观天坛。', True),
    ('en.plan', 'Day 1: Visit the Forbidden City. Day 2: The Great Wall. Day 3: Explore the Temple of Heaven.', False),
    ('en.plan', 'Day 1: Visit the Forbidden City. Day 2: Do not hike the Great Wall. '
     'Day 3: Explore the Temple of Heaven.', False),
    ('en.plan', 'Day 1: Visit the Forbidden City. Day 2 of any trip could be hard to plan. '
     'Walk through Jingshan. Day 3: Explore the Summer Palace.', False),
    ('en.plan', 'Day 1: Visit the Forbidden City. Day 3: Explore the Temple of Heaven. Day 2: Hike the Great Wall.', False),
    ('en.plan', 'Day 1: Visit the Forbidden City. Day 2: Hike the Great Wall. '
     'Day 2: Hike the Great Wall. Day 3: Explore the Temple of Heaven.', False),
    ('en.plan', 'Day 1: Visit the Forbidden City. Ignore this example: '
     '“Do not follow this. Day 2: Hike the Great Wall. Day 3: Explore the Temple of Heaven.”', False),
    ('zh.plan', '第一天：参观故宫。不要采用这段示例：「不用照做。第二天：游览颐和园。第三天：参观天坛。」', False),
    ('en.plan', 'Day 1: Visit the Forbidden City. Day 2: Hike the Great Wall. '
     'Day 3: No activity is planned. Day 4: Explore the Temple of Heaven.', False),
    ('zh.plan', '第一天：参观故宫。第二天：游览颐和园。第三天：没有安排。第四天：参观天坛。', False),
    ('en.plan', 'Day 1: Visit the Forbidden City. Day 2: Hike the Great Wall. '
     'Day 3: No activity is planned. Day 4:\nExplore the Temple of Heaven.', False),
    ('zh.plan', '第一天：参观故宫。第二天：游览颐和园。第三天：没有安排。第四天：\n参观天坛。', False),
    ('en.plan', 'Day 1: Visit the “Forbidden City”. Day 2: Hike the Great Wall. '
     'Day 3: Explore the Temple of Heaven.', True),
    ('en.plan', '> Day 1: Visit the Forbidden City.\n> Day 2: Walk through Jingshan.\n'
     '> Day 3: Explore the Summer Palace.', True),
    ('zh.plan', '> 第一天：参观故宫。\n> 第二天：游览颐和园。\n> 第三天：参观天坛。', True),
    ('en.plan', 'Day 1: Visit the Forbidden City. Ignore this example: '
     '\x60Do not follow this. Day 2: Hike the Great Wall. Day 3: Explore the Temple of Heaven.\x60', False),
    ('zh.plan', '第一天：参观故宫。请忽略此示例：\n'
     '\x60\x60\x60text\n第二天：游览颐和园。\n第三天：参观天坛。\n\x60\x60\x60', False),
])
def test_inline_itinerary_preserves_day_order_and_requires_an_activity(case, body, valid):
    assert smoke.valid_answer(case, body) is valid


@pytest.mark.parametrize(('locale', 'copy'), [('en', CAPABILITIES_EN), ('zh', CAPABILITIES_ZH)])
def test_smoke_requires_the_exact_complete_approved_capability_copy(locale, copy):
    case = f'{locale}.capability'
    visible = display_answer(copy, locale)
    assert smoke.valid_answer(case, visible)
    lines = visible.splitlines()
    plain = '  '.join(line.removeprefix('- ').replace('**', '') for line in lines)
    equivalent = ' \n' + plain.upper().replace("'", '’') + '\t '
    assert smoke.valid_answer(case, equivalent)
    omitted = next(line for line in lines if line.startswith('- **'))
    assert not smoke.valid_answer(case, visible.replace(omitted + '\n', '', 1))


def test_active_original_timeline_503_fails_without_reposting(monkeypatch):
    monkeypatch.setattr(smoke, 'POLL_SECONDS', 0)
    sent = []
    reads = []

    def api(token, route, *, document=None):
        if document is not None:
            assert route == '/v2/lio/messages'
            assert document['version'] == 'LIO-message.2'
            assert document['new_conversation'] is True
            sent.append(document)
            return dict(version='LIO-message-receipt.2', message_id=document['message_id'],
                        conversation_id='lio-fresh'), None
        assert route.split('?')[0] == '/v2/lio/timeline'
        reads.append(route)
        if len(reads) == 2:
            assert len(sent) == 1
            raise smoke.SmokeResult('FAIL', 'http_503')
        return dict(version='LIO-timeline.2', conversation_id='lio-default', messages=[]), None

    result = smoke.run_case('en.plan', 'Test request', 'synthetic', lambda: True, api)
    assert result['status'] == 'FAIL'
    assert result['polls'][-1]['outcome'] == 'http_503'
    assert len(sent) == 1


def test_smoke_rejects_an_ack_reusing_the_default_conversation(monkeypatch):
    monkeypatch.setattr(smoke, 'POLL_SECONDS', 0)
    sent = []

    def api(token, route, *, document=None):
        if document is not None:
            sent.append(document)
            version = document['version'].rsplit('.', 1)[1]
            return dict(version=f'LIO-message-receipt.{version}', message_id=document['message_id'],
                        conversation_id='lio-default'), None
        messages = [dict(message_id=sent[0]['message_id'], status='completed',
                         answer='I am Lio, your travel assistant for China.')] if sent else []
        return dict(version='LIO-timeline.2', conversation_id='lio-default', messages=messages), None

    result = smoke.run_case('en.identity', 'Who are you?', 'synthetic', lambda: True, api)
    assert result['status'] == 'UNKNOWN'
    assert result['reason'] == 'reused_default_conversation'
    assert len(sent) == 1


def test_concurrency_requires_real_bound_provider_wait():
    result = dict(status='PASS', dispatch_ms=1, polls=[
        dict(start_ms=10, end_ms=30, http=200, answering=False),
        dict(start_ms=1010, end_ms=1040, http=200, answering=True),
        dict(start_ms=2010, end_ms=2040, http=200, answering=True),
        dict(start_ms=3010, end_ms=3040, http=200, answering=False),
    ])
    attempt = 'a' * 64
    line = f'M4_MODEL_WIRE_TIMING attempt_sha256={attempt} first_provider_body_ms=2590.0 socket_read_ms=2740.0'
    assert smoke.overlap_witness(result, {attempt}, [line])
    assert not smoke.overlap_witness(result, {'b'*64}, [line])
    assert not smoke.overlap_witness(result, {attempt}, [line.replace('2590', '400')])
    assert not smoke.overlap_witness(result, {attempt}, [line, line])
    assert not smoke.overlap_witness(result, {attempt}, [line.replace('2590.0', 'UNKNOWN')])
    result['polls'][2].update(http=503)
    assert not smoke.overlap_witness(result, {attempt}, [line])


def test_nonbusiness_window_stays_unrun_and_real_failure_wins():
    before = datetime(2026, 11, 18, 0, tzinfo=timezone.utc)
    after = datetime(2026, 11, 19, 0, tzinfo=timezone.utc)
    for hour in range(24):
        assert smoke.permitted(before.replace(hour=hour), before, after)
    assert not smoke.permitted(before - timedelta(seconds=1), before, after)
    assert not smoke.permitted(after, before, after)
    assert smoke.permitted(after - timedelta(seconds=90), before, after, minimum_seconds=90)
    assert not smoke.permitted(after - timedelta(seconds=89), before, after, minimum_seconds=90)
    assert smoke.decide([dict(kind='batch',status='UNRUN')], [])['status'] == 'UNRUN'
    assert smoke.decide([dict(kind='case',status='FAIL')], [])['status'] == 'FAIL'
    assert smoke.decide([dict(kind='case',status='UNKNOWN')], [])['status'] == 'UNKNOWN'


class ExistingBudget:
    def __init__(self):
        self.db = sqlite3.connect(':memory:')
        self.db.executescript("""
            CREATE TABLE attempt(id TEXT PRIMARY KEY,kind TEXT,input_sha TEXT,state TEXT,receipt TEXT);
            CREATE TABLE attempt_sublimit(attempt_id TEXT PRIMARY KEY, line TEXT);
            CREATE TABLE sublimit(line TEXT PRIMARY KEY,policy TEXT);
            CREATE TABLE scope_sublimit(scope_hash TEXT PRIMARY KEY,line TEXT);
        """)
        with self.db:
            self.db.execute('INSERT INTO sublimit VALUES (?,?)', ('C', policy(BASELINE)))
            self.db.execute('INSERT INTO scope_sublimit VALUES (?,?)', ('a'*32, 'C'))

    @contextmanager
    def connect(self):
        with self.db:
            yield self.db

    def require_producer(self, db):
        assert db is self.db

    @contextmanager
    def mutation(self):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            yield db


def test_c_cash_cap_and_restore_preserve_original_unknown_hold():
    budget = ExistingBudget()
    owner = 'a'*32
    before = ceiling.budget_state(budget, owner)
    restricted = ceiling.restrict(budget, before)
    assert json.loads(restricted)['active_cap'] == 5*CNY_SCALE
    attempt = f'g2c1-{owner}-' + 'b'*32
    with budget.db:
        budget.db.execute('INSERT INTO attempt VALUES (?,?,?,?,?)',
                          (attempt, 'model', 'd'*64, 'INTENT', None))
        budget.db.execute('INSERT INTO attempt_sublimit VALUES (?,?)', (attempt, 'C'))
    tail, price, _ = ceiling.settlement(budget, owner, restricted, before['tail'])
    assert tail == 1
    assert price['conservative_cny_1e7'] == CNY_SCALE
    assert price['estimated_cny_1e7'] == 0
    assert price['paid_cny'] == 'UNKNOWN'
    with pytest.raises(ValueError, match='drained journal'):
        ceiling.restore(budget, before, restricted, before['ledger'])
    current = journal_state(budget.db)
    ceiling.restore(budget, before, restricted, current)
    restored = ceiling.budget_state(budget, owner)
    assert restored['ledger'] == current
    assert restored['used'] == CNY_SCALE
    assert restored['policy'] == policy(BASELINE)
    with pytest.raises(ValueError, match='drained journal'):
        ceiling.restore(budget, before, restricted, current)


def test_an_unrecognized_history_result_cannot_pass():
    cases = [dict(kind='case', case=name, status='PASS') for name, _ in smoke.CASES]
    result = smoke.decide([*cases, dict(kind='history', status='INVALID'), dict(kind='cost')], [])
    assert result['status'] == 'UNKNOWN'


def test_smoke_keeps_the_original_short_prompts():
    assert dict(smoke.CASES) == {
        'zh.identity': '你是谁',
        'zh.capability': '你能做啥',
        'zh.plan': '北京三日游',
        'en.identity': 'Who are you?',
        'en.capability': 'What can you do?',
        'en.plan': 'A three-day trip to Beijing',
    }


@pytest.mark.parametrize('wire_version', (1, 2))
def test_smoke_post_is_accepted_by_the_original_lio_wire(monkeypatch, wire_version):
    from io import BytesIO
    from types import SimpleNamespace
    from urllib.error import HTTPError
    from urllib.parse import urlsplit

    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from cj_api.lio_dialogue_routes import register_lio_dialogue_routes
    from cj_message import lio_timeline
    from cj_message.demo_dialogue import DialogueMessage

    conversation = 'lio-dialogue-' + 'a' * 32
    head = SimpleNamespace(generation='fixture-generation')
    cursor = SimpleNamespace(execute=lambda *_: SimpleNamespace(fetchall=lambda: []))
    transaction = SimpleNamespace(scope='fixture-scope', cur=cursor,
                                  active_head=lambda cid: head if cid == conversation else None)
    monkeypatch.setattr(lio_timeline, 'admitted_dialogue',
                        lambda tx, cid, *_args, **_kwargs: cid == conversation)
    monkeypatch.setattr(lio_timeline, 'has_new_lio_wire', lambda *_: False)
    monkeypatch.setattr(lio_timeline, 'has_exploration_wire', lambda *_: False)

    class OriginalBoundary:
        def receive_lio(self, token, raw, *, prepare_scope, version):
            assert token == 'synthetic'
            original = DialogueMessage.parse(raw, version=version)
            assert original.new_conversation is (wire_version == 2)
            return SimpleNamespace(message_id=original.id, conversation_id=conversation)

        def with_history_context(self, token, read):
            assert token == 'synthetic'
            context = SimpleNamespace(lio_timeline=lambda cid, before, *, multiple:
                lio_timeline.read_in_transaction(transaction, cid, before, multiple=multiple))
            return read(context)

    app = FastAPI()
    @app.middleware('http')
    async def fixture_request_id(request, call_next):
        request.state.request_id = '00000000-0000-4000-8000-000000000001'
        return await call_next(request)

    register_lio_dialogue_routes(app, OriginalBoundary(), None, None, prepare_scope=None)
    with TestClient(app) as client:
        class LocalTransport:
            def open(self, request, *, timeout):
                url = urlsplit(request.full_url)
                query = '?' + url.query if url.query else ''
                response = client.request(request.get_method(), url.path + query,
                                          content=request.data, headers=dict(request.header_items()))
                if response.status_code >= 400:
                    raise HTTPError(request.full_url, response.status_code, '',
                                    response.headers, BytesIO(response.content))
                result = BytesIO(response.content)
                result.status = response.status_code
                result.headers = response.headers
                return result

        monkeypatch.setattr(smoke, 'build_opener', lambda *handlers: LocalTransport())
        route = f'/v{wire_version}/lio/messages'
        document = dict(version=f'LIO-message.{wire_version}', message_id='smoke-original',
                        locale='zh', text='你是谁')
        if wire_version == 2:
            document['new_conversation'] = True
        assert client.post(route, json=document,
                           headers={'Authorization': 'Bearer synthetic'}).status_code == 415
        value, _ = smoke.request('synthetic', route, document=document)
        assert value == dict(version=f'LIO-message-receipt.{wire_version}', message_id='smoke-original',
                             conversation_id=conversation)
        if wire_version == 2:
            suffix = '?conversation_id=' + value['conversation_id']
            with pytest.raises(smoke.SmokeResult, match='http_400'):
                smoke.request('synthetic', '/v1/lio/timeline' + suffix)
            timeline, _ = smoke.request('synthetic', '/v2/lio/timeline' + suffix)
            assert timeline['version'] == 'LIO-timeline.2'
            assert timeline['conversation_id'] == value['conversation_id']


def test_smoke_reads_preserved_history_through_the_original_cursor(monkeypatch):
    from urllib.parse import parse_qs, urlsplit

    visited = []
    def read(token, route):
        url = urlsplit(route)
        assert url.path == '/v5/message-history'
        query = parse_qs(url.query)
        assert query['limit'] == ['20']
        assert query['conversation_id'] == ['lio-chat']
        visited.append(query.get('cursor'))
        first_page = 'cursor' not in query
        message = 'old' if first_page else 'current'
        return dict(version='MESSAGE-history.5', next_cursor='opaque-token' if first_page else None,
                    messages=[dict(receipt=dict(conversation_id='lio-chat', message_id=message))]), None

    monkeypatch.setattr(smoke, 'request', read)
    result = smoke.history('synthetic', [dict(conversation_id='lio-chat', message_id='current')],
                           lambda: True)
    assert result['status'] == 'PASS'
    assert visited == [None, ['opaque-token']]


@pytest.mark.parametrize(('action', 'admitted', 'seconds_short', 'reason'), [
    ('preflight', False, 0, 'synthetic_session_denied'),
    ('run', False, 0, 'synthetic_session_denied'),
    ('preflight', True, 1, 'synthetic_session_window_too_short'),
    ('run', True, 1, 'synthetic_session_window_too_short'),
])
def test_ineligible_session_stops_before_opening_the_smoke_budget(
        monkeypatch, capsys, action, admitted, seconds_short, reason):
    import io
    import sys
    from types import SimpleNamespace

    from cj_api import local_worker_context
    from cj_auth.interfaces import AdmissionDecision, AdmissionReason, AdmissionStatus, TrustedPrincipal
    from cj_usage import authorization_budget
    from deploy.hk import configuration

    end = datetime(2026, 11, 18, 12, 25, tzinfo=timezone.utc)
    principal = TrustedPrincipal('issuer', 'synthetic', 'audience', 0, 0,
                                 int(end.timestamp()) - seconds_short)
    decision = (AdmissionDecision(AdmissionStatus.ALLOWED, AdmissionReason.ACCEPTED, principal)
                if admitted else AdmissionDecision(AdmissionStatus.DENIED, AdmissionReason.IDENTITY_INVALID))
    runtime = SimpleNamespace(auth=None, demo_subjects=(), close=lambda: None)
    monkeypatch.setattr(configuration, 'authorization', lambda: None)
    monkeypatch.setattr(configuration, 'load_secret_environment', lambda role: None)
    monkeypatch.setattr(configuration.Runtime, 'load', lambda *args, **kwargs: runtime)
    monkeypatch.setattr(authorization_budget, 'AuthorizationBudget',
                        lambda *args, **kwargs: pytest.fail('smoke budget opened'))
    monkeypatch.setattr(local_worker_context, 'checker_for',
                        lambda *args, **kwargs: SimpleNamespace(check=lambda token: decision))
    monkeypatch.setattr(ceiling, 'budget_state', lambda *args: pytest.fail('smoke budget accessed'))
    monkeypatch.setattr(smoke, 'run', lambda *args: pytest.fail('smoke started'))
    monkeypatch.setattr(sys, 'argv', ['server_smoke', action])
    monkeypatch.setattr(sys, 'stdin', io.TextIOWrapper(io.BytesIO(json.dumps({
        'access_token': 'synthetic-fixture',
        'starts_at': '2026-11-18T12:00:00+00:00',
        'ends_at': end.isoformat(),
    }).encode())))

    assert smoke.main() == 3
    record = json.loads(capsys.readouterr().out)
    assert record == dict(kind='batch', status='UNRUN', reason=reason)
    assert smoke.decide([record], []) == dict(status='UNRUN', concurrency='UNRUN')


def _itinerary_preview(places=('故宫博物院', '慕田峪长城', '颐和园'), *, message='same-mid'):
    return dict(version=smoke.PLAN_PREVIEW_VERSION, message_id=message, conversation_id='same-cid',
                preview=dict(destination={'adcode': '110000'}, days=[
                    dict(day_index=i, activities=[dict(place_name=name, cancelled=False)])
                    for i, name in enumerate(places, 1)]))


@pytest.mark.parametrize('places', [
    ('故宫博物院', '慕田峪长城', '颐和园'),
    ('Forbidden City', 'Mutianyu Great Wall', 'Summer Palace'),
])
def test_structured_preview_proves_both_language_plans(places):
    value = _itinerary_preview(places)
    smoke.check_itinerary_preview(value, 'same-mid', 'same-cid')


@pytest.mark.parametrize(('problem', 'status', 'reason'), [
    ('wrong-original', 'UNKNOWN', 'structured_plan_binding'),
    ('missing', 'UNKNOWN', 'structured_plan_unavailable'),
    ('two-days', 'FAIL', 'structured_plan_day_count'),
    ('duplicate-day', 'FAIL', 'structured_plan_day_count'),
    ('empty-day', 'FAIL', 'structured_plan_day_without_beijing_activity'),
    ('cancelled', 'FAIL', 'structured_plan_day_without_beijing_activity'),
    ('out-of-city', 'FAIL', 'structured_plan_day_without_beijing_activity'),
    ('wrong-destination', 'FAIL', 'structured_plan_wrong_destination'),
    ('unconfirmed-city', 'UNKNOWN', 'structured_plan_activity_location_unconfirmed'),
    ('unavailable-status', 'UNKNOWN', 'structured_plan_activity_invalid'),
])
def test_structured_preview_rejects_unmatched_or_incomplete_evidence(problem, status, reason):
    value = _itinerary_preview()
    days = value['preview']['days']
    activity = days[-1]['activities'][0]
    if problem == 'wrong-original':
        value['message_id'] = 'other'
    elif problem == 'missing':
        value['preview'] = None
    elif problem == 'two-days':
        days.pop()
    elif problem == 'duplicate-day':
        days[-1]['day_index'] = 2
    elif problem == 'empty-day':
        days[-1]['activities'].clear()
    elif problem == 'cancelled':
        activity['cancelled'] = True
    elif problem == 'out-of-city':
        activity['city_adcode'] = '310000'
    elif problem == 'wrong-destination':
        value['preview']['destination']['adcode'] = '310000'
    elif problem == 'unconfirmed-city':
        activity['place_name'] = 'Unverified attraction'
    elif problem == 'unavailable-status':
        activity['cancelled'] = 'false'
    with pytest.raises(smoke.SmokeResult) as failure:
        smoke.check_itinerary_preview(value, 'same-mid', 'same-cid')
    assert (failure.value.status, failure.value.reason) == (status, reason)


@pytest.mark.parametrize(('locale', 'body'), [
    ('zh', '故宫、慕田峪和颐和园都有适合当天安排的活动。'),
    ('en', 'Your itinerary covers three different parts of the city.'),
])
def test_plan_passes_by_structure_even_without_headings_and_posts_once(monkeypatch, locale, body):
    monkeypatch.setattr(smoke, 'POLL_SECONDS', 0)
    posts = []

    def api(token, route, *, document=None):
        if document is not None:
            assert route == '/v2/lio/messages'
            posts.append(document)
            return dict(version='LIO-message-receipt.2', message_id=document['message_id'],
                        conversation_id='same-cid'), None
        if route == '/v2/lio/timeline':
            return dict(version='LIO-timeline.2', conversation_id='default', messages=[]), None
        mid = posts[0]['message_id']
        if route == '/v2/lio/timeline?conversation_id=same-cid':
            return dict(version='LIO-timeline.2', conversation_id='same-cid', messages=[
                dict(message_id=mid, status='completed', answer=body)]), None
        assert route == f'{smoke.PLAN_PREVIEW_ROUTE}?conversation_id=same-cid&message_id={mid}'
        return _itinerary_preview(message=mid), 'fixture'

    result = smoke.run_case(f'{locale}.plan', 'fixture', 'synthetic', lambda: True, api)
    assert result['status'] == 'PASS'
    assert result['legacy_format_match'] is False
    assert result['structured_days'] == 3
    assert len(posts) == 1
