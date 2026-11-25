"""#1516: roadbook place enrichment in the original M4 authorization journal (M4 item 18)."""
from datetime import datetime
from uuid import uuid4

import pytest

from cj_usage import roadbook_budget
from cj_usage.authorization_budget import (
    AuthorizationBudget, CNY_SCALE, HK_PRODUCER, LIMITS, M1_UNRESOLVED_CNY, MAC_PRODUCER, MODEL_INPUT_PRICE,
    MODEL_OUTPUT_PRICE, authorization_usage, journal_state,
)
from cj_usage.metered_exit import BudgetUnknown
from cj_usage.roadbook_budget import (
    BEIJING, DAILY_BOOKS, DAILY_PLACES, MODEL, SERVICE, RoadbookBudget, RoadbookDuplicate, RoadbookLimit,
    roadbook_price,
)
from scripts.m4_budget_transfer import attempts


@pytest.fixture
def budget(tmp_path):
    real = AuthorizationBudget(tmp_path / 'existing', clock=lambda: datetime(2026, 11, 26, 10, tzinfo=BEIJING))
    return RoadbookBudget(real)


def _usage(source=1200, output=600):
    return {'input_tokens': source, 'output_tokens': output}


def _call(budget, operation, stage, usage=None):
    budget.begin(operation, stage)
    budget.finish(operation, stage, f'chatcmpl-{uuid4().hex}', usage or _usage())


def _receipt(**changes):
    value = dict(service=SERVICE, region='cn-beijing', model_id=MODEL, day='2026-11-26', places=1, stage=0,
                 receipt_sha256='0' * 64, usage=_usage())
    value.update(changes)
    return value


def test_list_price_uses_the_m4_flash_token_rates():
    assert MODEL == 'qwen3.8-flash'
    assert roadbook_price(_receipt()) == 1200 * MODEL_INPUT_PRICE + 600 * MODEL_OUTPUT_PRICE
    assert roadbook_price(_receipt(usage=_usage(1, 0))) == MODEL_INPUT_PRICE


@pytest.mark.parametrize('changes', [
    dict(service='translation.1'), dict(region='intl'), dict(model_id='qwen-plus'),
    dict(usage={'input_tokens': 10}), dict(usage=_usage(0, 10)), dict(usage=_usage(40_000, 10)),
    dict(usage=_usage(10, 1001)), dict(usage={'input_tokens': 10, 'output_tokens': 10, 'extra': 1}),
    dict(usage=_usage(True, 10)),
])
def test_unpriceable_receipts_stay_held(changes):
    assert roadbook_price(_receipt(**changes)) is None


def test_settled_calls_are_priced_in_the_shared_model_totals(budget):
    operation = budget.operation('scope-a', uuid4(), 1)
    _call(budget, operation, 0)
    with budget.authorization.mutation() as db:
        counts, estimates, holds = authorization_usage(db)
        rows = db.execute('SELECT id,kind,state FROM attempt').fetchall()
    assert rows == [(operation.identifier(0), 'model', 'RECEIVED')]
    assert counts['model'] == 1
    assert estimates['model'] >= 1200 * MODEL_INPUT_PRICE + 600 * MODEL_OUTPUT_PRICE


def test_each_place_has_two_sequential_calls_and_no_more(budget):
    operation = budget.operation('scope-a', uuid4(), 2)
    with pytest.raises(BudgetUnknown):
        budget.begin(operation, 1)  # stage 0 has not settled
    _call(budget, operation, 0)
    with pytest.raises(RoadbookDuplicate):
        budget.begin(operation, 0)
    for stage in (1, 2, 3):
        _call(budget, operation, stage)
    with pytest.raises(BudgetUnknown):
        budget.begin(operation, 4)


def test_new_places_per_day_are_capped_per_owner(budget):
    for places in (20, 20, 15):
        _call(budget, budget.operation('scope-a', uuid4(), places), 0)
    with pytest.raises(RoadbookLimit):
        budget.begin(budget.operation('scope-a', uuid4(), 6), 0)
    _call(budget, budget.operation('scope-a', uuid4(), DAILY_PLACES - 55), 0)
    _call(budget, budget.operation('scope-b', uuid4(), 20), 0)


def test_roadbooks_per_day_are_capped_per_owner(budget):
    for _ in range(DAILY_BOOKS):
        _call(budget, budget.operation('scope-a', uuid4(), 1), 0)
    with pytest.raises(RoadbookLimit):
        budget.begin(budget.operation('scope-a', uuid4(), 1), 0)
    _call(budget, budget.operation('scope-b', uuid4(), 1), 0)


@pytest.mark.parametrize('places', [0, 21, -1])
def test_a_request_names_one_to_twenty_new_places(budget, places):
    with pytest.raises(BudgetUnknown):
        budget.operation('scope-a', uuid4(), places)


def test_eighty_percent_of_the_sublimit_switches_to_cache_only(budget, monkeypatch):
    assert roadbook_budget.cache_only_limit() == 240 * CNY_SCALE
    price = 1200 * MODEL_INPUT_PRICE + 600 * MODEL_OUTPUT_PRICE
    reserve = 1 * CNY_SCALE
    monkeypatch.setattr(roadbook_budget, 'CACHE_ONLY_PERCENT', 100)
    monkeypatch.setattr(roadbook_budget, 'SUBLIMIT', 2 * price + reserve - 1)
    assert not budget.cache_only()
    operation = budget.operation('scope-a', uuid4(), 2)
    _call(budget, operation, 0)
    _call(budget, operation, 1)
    assert budget.cache_only()
    with pytest.raises(RoadbookLimit):
        budget.begin(operation, 2)


def test_an_unknown_call_keeps_its_full_hold_against_the_sublimit(budget, monkeypatch):
    monkeypatch.setattr(roadbook_budget, 'CACHE_ONLY_PERCENT', 100)
    monkeypatch.setattr(roadbook_budget, 'SUBLIMIT', 2 * CNY_SCALE - 1)
    operation = budget.operation('scope-a', uuid4(), 1)
    budget.begin(operation, 0)  # never settled: the supplier result is unknown
    with pytest.raises(RoadbookLimit):
        budget.begin(budget.operation('scope-b', uuid4(), 1), 0)


def test_receipts_without_valid_usage_are_refused(budget):
    operation = budget.operation('scope-a', uuid4(), 1)
    budget.begin(operation, 0)
    with pytest.raises(BudgetUnknown):
        budget.finish(operation, 0, 'chatcmpl-1', {'input_tokens': 10})


def test_output_is_capped_at_the_authorized_thousand_tokens():
    assert roadbook_price(_receipt(usage=_usage(10, 1000))) is not None
    assert roadbook_price(_receipt(usage=_usage(10, 1001))) is None


def test_cache_only_reads_without_writing_and_follows_the_shared_stop_line(budget, monkeypatch):
    with budget.authorization.connect() as db:
        before = journal_state(db)
    assert not budget.cache_only()
    with budget.authorization.connect() as db:
        assert journal_state(db) == before
    monkeypatch.setattr(roadbook_budget, 'LIMITS', dict(LIMITS, model=(0, 1)))
    assert budget.cache_only()
    with pytest.raises(RoadbookLimit):
        budget.begin(budget.operation('scope-a', uuid4(), 1), 0)


def test_cache_only_stops_after_the_authorization_expires(tmp_path):
    expired = AuthorizationBudget(tmp_path / 'expired', clock=lambda: datetime(2027, 1, 2, tzinfo=BEIJING))
    with pytest.raises(BudgetUnknown):
        RoadbookBudget(expired).cache_only()


def _roadbook_journal(budget):
    settled = budget.operation('scope-fixture', uuid4(), 1)
    _call(budget, settled, 0)
    pending = budget.operation('scope-other', uuid4(), 2)
    budget.begin(pending, 0)
    return settled.identifier(0), pending.identifier(0)


def test_hk_proof_accepts_roadbook_intents_and_receipts(budget):
    _roadbook_journal(budget)
    with budget.authorization.connect() as db:
        db.execute('UPDATE producer SET identity=?', (HK_PRODUCER,))
        original = db.execute('SELECT * FROM attempt ORDER BY id').fetchall()
        assert attempts(db) == journal_state(db)
        assert db.execute('SELECT * FROM attempt ORDER BY id').fetchall() == original
        _, estimates, holds = authorization_usage(db)
        assert estimates['model'] > 0 and holds['model'] == (M1_UNRESOLVED_CNY + 1) * CNY_SCALE


def test_mac_transfer_rejects_runtime_roadbook_attempts(budget):
    _roadbook_journal(budget)
    with budget.authorization.connect() as db:
        assert db.execute('SELECT identity FROM producer').fetchone() == (MAC_PRODUCER,)
        with pytest.raises(ValueError, match='original_attempt_history_invalid'):
            attempts(db)


@pytest.mark.parametrize('source,field,value', [
    ('pending', 'input_sha', '0' * 64),
    ('pending', 'receipt', None),
    ('pending', 'kind', 'place'),
    ('received', 'receipt', '{"unexpected":"metadata"}'),
    ('received', 'id', 'roadbook.0:'),
])
def test_hk_proof_rejects_tampered_roadbook_rows(budget, source, field, value):
    settled, pending = _roadbook_journal(budget)
    target = pending if source == 'pending' else settled
    with budget.authorization.connect() as db:
        db.execute('UPDATE producer SET identity=?', (HK_PRODUCER,))
        if field == 'id':
            value = target.replace('roadbook.1:', value)
        db.execute('UPDATE attempt SET ' + field + '=? WHERE id=?', (value, target))
        with pytest.raises(ValueError, match='original_attempt_history_invalid'):
            attempts(db)


@pytest.mark.parametrize('key,value', [('places', 3), ('day', '2026-11-27'), ('stage', 1)])
def test_hk_proof_rejects_edited_roadbook_receipt_metadata(budget, key, value):
    import json
    settled, _ = _roadbook_journal(budget)
    with budget.authorization.connect() as db:
        db.execute('UPDATE producer SET identity=?', (HK_PRODUCER,))
        receipt = json.loads(db.execute('SELECT receipt FROM attempt WHERE id=?', (settled,)).fetchone()[0])
        receipt[key] = value
        from cj_usage.authorization_budget import canonical
        db.execute('UPDATE attempt SET receipt=? WHERE id=?', (canonical(receipt).decode(), settled))
        with pytest.raises(ValueError, match='original_attempt_history_invalid'):
            attempts(db)


# M4 item 18 Gaode calls (JT 2026-11-25: separately counted, at most 2000, sharing only the ¥500 tool cash).

from cj_usage.authorization_budget import AMAP_PRICE, separately_counted_place, shared_place_services
from cj_usage.roadbook_budget import (
    AMAP_DAILY_CALLS, AMAP_OPERATIONS, AMAP_ORIGIN, AMAP_SERVICE, M4_AMAP_LIMIT, RoadbookPlaceBudget,
)


@pytest.fixture
def places(budget):
    return RoadbookPlaceBudget(budget.authorization)


def _gaode(places, scope, request, index, operation):
    attempt = places.begin(scope, request, index, operation)
    places.finish(attempt, b'{"status":"1"}')
    return attempt


def test_gaode_limits_match_the_authorization():
    assert AMAP_SERVICE == 'amap-roadbook.1'
    assert M4_AMAP_LIMIT == 2000
    assert AMAP_DAILY_CALLS == DAILY_PLACES * 2
    assert AMAP_OPERATIONS == {'text': '/v5/place/text', 'detail': '/v5/place/detail', 'around': '/v5/place/around'}
    origin, operations, separate = shared_place_services()[AMAP_SERVICE]
    assert (origin, operations, separate) == (AMAP_ORIGIN, AMAP_OPERATIONS, True)


def test_gaode_calls_are_priced_and_kept_out_of_the_legacy_place_allowance(places):
    request = uuid4()
    _gaode(places, 'scope-a', request, 0, 'text')
    _gaode(places, 'scope-a', request, 0, 'around')
    with places.authorization.mutation() as db:
        counts, estimates, _ = authorization_usage(db)
        assert counts['place'] == 2 and separately_counted_place(db) == 2
        assert estimates['place'] == 2 * AMAP_PRICE


def test_each_place_identifies_once_and_searches_around_once(places):
    request = uuid4()
    _gaode(places, 'scope-a', request, 3, 'detail')
    for operation in ('detail', 'text'):
        with pytest.raises(RoadbookDuplicate):
            places.begin('scope-a', request, 3, operation)
    _gaode(places, 'scope-a', request, 3, 'around')
    with pytest.raises(RoadbookDuplicate):
        places.begin('scope-a', request, 3, 'around')
    _gaode(places, 'scope-a', request, 4, 'text')


@pytest.mark.parametrize('index,operation', [(-1, 'text'), (20, 'text'), (0, 'reverse'), (0, 'search')])
def test_unknown_gaode_steps_are_refused(places, index, operation):
    with pytest.raises(BudgetUnknown):
        places.begin('scope-a', uuid4(), index, operation)


def test_gaode_calls_per_owner_and_day_are_capped(places, monkeypatch):
    monkeypatch.setattr(roadbook_budget, 'AMAP_DAILY_CALLS', 3)
    request = uuid4()
    for index in range(3):
        _gaode(places, 'scope-a', request, index, 'text')
    with pytest.raises(RoadbookLimit):
        places.begin('scope-a', request, 3, 'text')
    _gaode(places, 'scope-b', uuid4(), 0, 'text')


def test_gaode_total_is_capped_for_m4(places, monkeypatch):
    monkeypatch.setattr(roadbook_budget, 'M4_AMAP_LIMIT', 2)
    _gaode(places, 'scope-a', uuid4(), 0, 'text')
    places.begin('scope-b', uuid4(), 0, 'text')  # an unsettled call still counts
    with pytest.raises(RoadbookLimit):
        places.begin('scope-c', uuid4(), 0, 'text')


def test_gaode_calls_share_the_tool_cash_ceiling(places, monkeypatch):
    from cj_usage import authorization_budget
    monkeypatch.setattr(authorization_budget, 'TOOL_TOTAL_CNY', 0)
    monkeypatch.setattr(roadbook_budget, 'TOOL_TOTAL_CNY', 0)
    with pytest.raises(RoadbookLimit):
        places.begin('scope-a', uuid4(), 0, 'text')


def test_hk_proof_accepts_gaode_roadbook_rows(places):
    _gaode(places, 'scope-a', uuid4(), 0, 'text')
    places.begin('scope-a', uuid4(), 1, 'around')
    with places.authorization.connect() as db:
        db.execute('UPDATE producer SET identity=?', (HK_PRODUCER,))
        assert attempts(db) == journal_state(db)


def test_admits_reads_the_same_daily_allowance_without_writing(budget):
    first = budget.operation('scope-a', uuid4(), 20)
    assert budget.admits(first)
    for _ in range(3):
        _call(budget, budget.operation('scope-a', uuid4(), 20), 0)
    with budget.authorization.connect() as db:
        before = journal_state(db)
    assert not budget.admits(budget.operation('scope-a', uuid4(), 1))
    assert budget.admits(budget.operation('scope-b', uuid4(), 20))
    with budget.authorization.connect() as db:
        assert journal_state(db) == before
