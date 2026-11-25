"""#1516: roadbook place enrichment in the original M4 authorization journal (M4 item 18)."""
from datetime import datetime
from uuid import uuid4

import pytest

from cj_usage import roadbook_budget
from cj_usage.authorization_budget import (
    AuthorizationBudget, CNY_SCALE, MODEL_INPUT_PRICE, MODEL_OUTPUT_PRICE, authorization_usage,
)
from cj_usage.metered_exit import BudgetUnknown
from cj_usage.roadbook_budget import (
    BEIJING, DAILY_BOOKS, DAILY_PLACES, MODEL, SERVICE, RoadbookBudget, RoadbookDuplicate, RoadbookLimit,
    roadbook_price,
)


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
    dict(usage=_usage(10, 1537)), dict(usage={'input_tokens': 10, 'output_tokens': 10, 'extra': 1}),
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
