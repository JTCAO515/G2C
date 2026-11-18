from contextlib import contextmanager
from datetime import datetime, timezone
import json
import sqlite3

import pytest

from cj_usage.authorization_budget import CNY_SCALE, journal_state
from cj_usage.sublimits import policy
from deploy.hk.app_smoke_ceiling import BASELINE
from deploy.hk import server_smoke as smoke
from deploy.hk import server_smoke_budget as ceiling


@pytest.mark.parametrize(('case', 'body', 'valid'), [
    ('zh.identity', '我是 Lio，你在中国旅行时的智能助手。', True),
    ('en.identity', 'I am Lio, your travel assistant for China.', True),
    ('en.identity', 'Welcome to China. How can I help you?', False),
    ('en.capability', 'I can plan your itinerary and explain local transport.', True),
    ('en.capability', 'I offer no travel assistance. Please ask someone to plan your itinerary.', False),
    ('zh.capability', '我可以规划行程，解释当地交通和支付。', True),
    ('zh.plan', '第一天\n上午游览故宫和天安门广场，下午去景山公园。\n第二天\n乘车去慕田峪长城，在景区步行并参观烽火台。\n第三天\n上午参观颐和园并沿昆明湖步行，下午去前门。', True),
    ('en.plan', '**Day 1: City centre**\nWalk through the Forbidden City and climb Jingshan.\n**Day 2: Great Wall**\nTake the morning shuttle to Mutianyu and walk between towers.\n**Day 3: Gardens**\nTour the Summer Palace and walk along the lake.', True),
    ('en.plan', 'Day 1: Forbidden City.\nDay 2: TBD.\nDay 3: Summer Palace.', False),
    ('zh.plan', '第一天：故宫没有安排。\n第二天：长城没有安排。\n第三天：天坛没有安排。', False),
    ('en.plan', 'Day 1: No activity is planned at the Forbidden City.\nDay 2: No activity is planned at the Great Wall.\nDay 3: No activity is planned at the Temple of Heaven.', False),
    ('zh.plan', '第一天：不建议参观故宫。\n第二天：不建议游览长城。\n第三天：不建议参观天坛。', False),
    ('en.plan', 'Day 1: You should not visit the Forbidden City.\nDay 2: Do not visit the Great Wall.\nDay 3: Avoid visiting the Temple of Heaven.', False),
    ('zh.plan', '第一天：你想参观故宫吗？\n第二天：你想游览长城吗？\n第三天：你想参观天坛吗？', False),
    ('en.plan', 'Day 1: Would you like to visit the Forbidden City?\nDay 2: Would you like to tour the Great Wall?\nDay 3: Would you like to visit the Temple of Heaven?', False),
    ('en.plan', 'Could you give me your hotel details first? Then I can plan all three days.', False),
])
def test_real_body_is_required(case, body, valid):
    assert smoke.valid_answer(case, body) is valid


def test_active_original_timeline_503_fails_without_reposting(monkeypatch):
    monkeypatch.setattr(smoke, 'POLL_SECONDS', 0)
    sent = []
    reads = []

    def api(token, route, *, document=None):
        if document is not None:
            sent.append(document)
            return dict(version='LIO-message-receipt.1', message_id=document['message_id'],
                        conversation_id='lio-chat'), None
        reads.append(route)
        if len(reads) == 2:
            assert len(sent) == 1
            raise smoke.SmokeResult('FAIL', 'http_503')
        return dict(version='LIO-timeline.1', conversation_id='lio-chat', messages=[]), None

    result = smoke.run_case('en.plan', 'Test request', 'synthetic', lambda: True, api)
    assert result['status'] == 'FAIL'
    assert result['polls'][-1]['outcome'] == 'http_503'
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
    for hour, allowed in [(0, True), (14, True), (15, False), (23, False)]:
        assert smoke.permitted(before.replace(hour=hour), before, after) is allowed
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
