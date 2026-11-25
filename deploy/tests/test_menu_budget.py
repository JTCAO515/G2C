"""#1583: menu explanations in the original M4 authorization journal (M4 item 19)."""
from datetime import datetime
import json
from uuid import uuid4

import pytest

from cj_usage import menu_budget
from cj_usage.authorization_budget import (
    AuthorizationBudget, CNY_SCALE, HK_PRODUCER, LIMITS, M1_UNRESOLVED_CNY, MAC_PRODUCER, MODEL_INPUT_PRICE,
    MODEL_OUTPUT_PRICE, authorization_usage, canonical, journal_state,
)
from cj_usage.menu_budget import (
    BEIJING, CALLS_PER_MENU, DAILY_MENUS, MAX_OUTPUT_TOKENS, MODEL, SERVICE, SUBLIMIT, MenuBudget, MenuDuplicate,
    MenuLimit, menu_price,
)
from cj_usage.metered_exit import BudgetUnknown
from scripts.m4_budget_transfer import attempts


@pytest.fixture
def budget(tmp_path):
    real = AuthorizationBudget(tmp_path / 'existing', clock=lambda: datetime(2026, 11, 26, 10, tzinfo=BEIJING))
    return MenuBudget(real)


def _usage(source=1500, output=2500):
    return {'input_tokens': source, 'output_tokens': output}


def _call(budget, operation, stage, usage=None):
    budget.begin(operation, stage)
    budget.finish(operation, stage, f'chatcmpl-{uuid4().hex}', usage or _usage())


def _receipt(**changes):
    value = dict(service=SERVICE, region='cn-beijing', model_id=MODEL, day='2026-11-26', calls=1, stage=0,
                 receipt_sha256='0' * 64, usage=_usage())
    value.update(changes)
    return value


def test_limits_match_the_authorization():
    assert (SERVICE, MODEL, DAILY_MENUS, CALLS_PER_MENU) == ('menu.1', 'qwen3.8-flash', 10, 2)
    assert SUBLIMIT == 100 * CNY_SCALE and menu_budget.cache_only_limit() == 80 * CNY_SCALE


def test_list_price_uses_the_m4_flash_token_rates():
    assert menu_price(_receipt()) == 1500 * MODEL_INPUT_PRICE + 2500 * MODEL_OUTPUT_PRICE
    # About ¥0.008 for a typical call; even two calls at the output cap stay under ¥0.04 a menu.
    assert menu_price(_receipt()) < CNY_SCALE // 100
    assert 2 * menu_price(_receipt(usage=_usage(2000, MAX_OUTPUT_TOKENS))) < 4 * CNY_SCALE // 100


@pytest.mark.parametrize('changes', [
    dict(service='roadbook.1'), dict(region='intl'), dict(model_id='qwen-plus'),
    dict(usage={'input_tokens': 10}), dict(usage=_usage(0, 10)), dict(usage=_usage(40_000, 10)),
    dict(usage=_usage(10, MAX_OUTPUT_TOKENS + 1)), dict(usage={'input_tokens': 10, 'output_tokens': 10, 'x': 1}),
    dict(usage=_usage(True, 10)),
])
def test_unpriceable_receipts_stay_held(changes):
    assert menu_price(_receipt(**changes)) is None


def test_settled_calls_are_priced_in_the_shared_model_totals(budget):
    operation = budget.operation('scope-a', uuid4(), 1)
    _call(budget, operation, 0)
    with budget.authorization.mutation() as db:
        counts, estimates, holds = authorization_usage(db)
        rows = db.execute('SELECT id,kind,state FROM attempt').fetchall()
    assert rows == [(operation.identifier(0), 'model', 'RECEIVED')]
    assert counts['model'] == 1
    assert estimates['model'] >= 1500 * MODEL_INPUT_PRICE + 2500 * MODEL_OUTPUT_PRICE


def test_a_menu_has_at_most_two_sequential_calls(budget):
    operation = budget.operation('scope-a', uuid4(), 2)
    with pytest.raises(BudgetUnknown):
        budget.begin(operation, 1)  # stage 0 has not settled
    _call(budget, operation, 0)
    with pytest.raises(MenuDuplicate):
        budget.begin(operation, 0)
    _call(budget, operation, 1)
    with pytest.raises(BudgetUnknown):
        budget.begin(operation, 2)


@pytest.mark.parametrize('calls', [0, 3, -1, True])
def test_a_menu_takes_one_or_two_calls(budget, calls):
    with pytest.raises(BudgetUnknown):
        budget.operation('scope-a', uuid4(), calls)


def test_ten_explained_menus_per_owner_and_day(budget):
    for _ in range(DAILY_MENUS):
        assert budget.admits('scope-a')
        _call(budget, budget.operation('scope-a', uuid4(), 1), 0)
    assert not budget.admits('scope-a')
    with pytest.raises(MenuLimit):
        budget.begin(budget.operation('scope-a', uuid4(), 1), 0)
    assert budget.admits('scope-b')
    _call(budget, budget.operation('scope-b', uuid4(), 1), 0)


def test_a_two_call_menu_counts_once(budget):
    operation = budget.operation('scope-a', uuid4(), 2)
    _call(budget, operation, 0)
    _call(budget, operation, 1)
    for _ in range(DAILY_MENUS - 1):
        _call(budget, budget.operation('scope-a', uuid4(), 1), 0)
    assert not budget.admits('scope-a')


def test_eighty_percent_of_the_sublimit_switches_to_cache_only(budget, monkeypatch):
    price = 1500 * MODEL_INPUT_PRICE + 2500 * MODEL_OUTPUT_PRICE
    reserve = 1 * CNY_SCALE
    monkeypatch.setattr(menu_budget, 'CACHE_ONLY_PERCENT', 100)
    monkeypatch.setattr(menu_budget, 'SUBLIMIT', 2 * price + reserve - 1)
    assert budget.admits('scope-a')
    operation = budget.operation('scope-a', uuid4(), 2)
    _call(budget, operation, 0)
    _call(budget, operation, 1)
    assert not budget.admits('scope-b')
    with pytest.raises(MenuLimit):
        budget.begin(budget.operation('scope-b', uuid4(), 1), 0)


def test_an_unknown_call_keeps_its_full_hold_against_the_sublimit(budget, monkeypatch):
    monkeypatch.setattr(menu_budget, 'CACHE_ONLY_PERCENT', 100)
    monkeypatch.setattr(menu_budget, 'SUBLIMIT', 2 * CNY_SCALE - 1)
    operation = budget.operation('scope-a', uuid4(), 1)
    budget.begin(operation, 0)  # never settled: the supplier result is unknown
    with pytest.raises(MenuLimit):
        budget.begin(budget.operation('scope-b', uuid4(), 1), 0)


def test_receipts_without_valid_usage_are_refused(budget):
    operation = budget.operation('scope-a', uuid4(), 1)
    budget.begin(operation, 0)
    with pytest.raises(BudgetUnknown):
        budget.finish(operation, 0, 'chatcmpl-1', {'input_tokens': 10})


def test_admits_reads_without_writing_and_follows_the_shared_stop_line(budget, monkeypatch):
    with budget.authorization.connect() as db:
        before = journal_state(db)
    assert budget.admits('scope-a')
    with budget.authorization.connect() as db:
        assert journal_state(db) == before
    monkeypatch.setattr(menu_budget, 'LIMITS', dict(LIMITS, model=(0, 1)))
    assert not budget.admits('scope-a')
    with pytest.raises(MenuLimit):
        budget.begin(budget.operation('scope-a', uuid4(), 1), 0)


def test_nothing_is_admitted_after_the_authorization_expires(tmp_path):
    expired = AuthorizationBudget(tmp_path / 'expired', clock=lambda: datetime(2027, 1, 2, tzinfo=BEIJING))
    with pytest.raises(BudgetUnknown):
        MenuBudget(expired).admits('scope-a')


def test_the_journal_holds_no_menu_text_or_user_data(budget):
    operation = budget.operation('scope-private', uuid4(), 1)
    _call(budget, operation, 0)
    with budget.authorization.connect() as db:
        dump = json.dumps(db.execute('SELECT * FROM attempt').fetchall(), ensure_ascii=False)
    assert 'scope-private' not in dump
    assert set(json.loads(db_receipt(budget, operation))) == {
        'service', 'region', 'day', 'calls', 'stage', 'model_id', 'receipt_sha256', 'usage'}


def db_receipt(budget, operation):
    with budget.authorization.connect() as db:
        return db.execute('SELECT receipt FROM attempt WHERE id=?', (operation.identifier(0),)).fetchone()[0]


def _menu_journal(budget):
    settled = budget.operation('scope-fixture', uuid4(), 1)
    _call(budget, settled, 0)
    pending = budget.operation('scope-other', uuid4(), 2)
    budget.begin(pending, 0)
    return settled.identifier(0), pending.identifier(0)


def test_hk_proof_accepts_menu_intents_and_receipts(budget):
    _menu_journal(budget)
    with budget.authorization.connect() as db:
        db.execute('UPDATE producer SET identity=?', (HK_PRODUCER,))
        original = db.execute('SELECT * FROM attempt ORDER BY id').fetchall()
        assert attempts(db) == journal_state(db)
        assert db.execute('SELECT * FROM attempt ORDER BY id').fetchall() == original
        _, estimates, holds = authorization_usage(db)
        assert estimates['model'] > 0 and holds['model'] == (M1_UNRESOLVED_CNY + 1) * CNY_SCALE


def test_mac_transfer_rejects_runtime_menu_attempts(budget):
    _menu_journal(budget)
    with budget.authorization.connect() as db:
        assert db.execute('SELECT identity FROM producer').fetchone() == (MAC_PRODUCER,)
        with pytest.raises(ValueError, match='original_attempt_history_invalid'):
            attempts(db)


@pytest.mark.parametrize('source,field,value', [
    ('pending', 'input_sha', '0' * 64),
    ('pending', 'receipt', None),
    ('pending', 'kind', 'place'),
    ('received', 'receipt', '{"unexpected":"metadata"}'),
    ('received', 'id', 'menu.0:'),
])
def test_hk_proof_rejects_tampered_menu_rows(budget, source, field, value):
    settled, pending = _menu_journal(budget)
    target = pending if source == 'pending' else settled
    with budget.authorization.connect() as db:
        db.execute('UPDATE producer SET identity=?', (HK_PRODUCER,))
        if field == 'id':
            value = target.replace('menu.1:', value)
        db.execute('UPDATE attempt SET ' + field + '=? WHERE id=?', (value, target))
        with pytest.raises(ValueError, match='original_attempt_history_invalid'):
            attempts(db)


@pytest.mark.parametrize('key,value', [('calls', 2), ('calls', 3), ('day', '2026-11-27'), ('stage', 1)])
def test_hk_proof_rejects_edited_menu_receipt_metadata(budget, key, value):
    settled, _ = _menu_journal(budget)
    with budget.authorization.connect() as db:
        db.execute('UPDATE producer SET identity=?', (HK_PRODUCER,))
        receipt = json.loads(db.execute('SELECT receipt FROM attempt WHERE id=?', (settled,)).fetchone()[0])
        receipt[key] = value
        db.execute('UPDATE attempt SET receipt=? WHERE id=?', (canonical(receipt).decode(), settled))
        with pytest.raises(ValueError, match='original_attempt_history_invalid'):
            attempts(db)


def _rows(budget):
    with budget.authorization.connect() as db:
        return db.execute('SELECT id,state FROM attempt ORDER BY id').fetchall()


def test_a_refused_call_leaves_no_intent(budget, monkeypatch):
    for _ in range(DAILY_MENUS):
        _call(budget, budget.operation('scope-a', uuid4(), 1), 0)
    before = _rows(budget)
    with pytest.raises(MenuLimit):
        budget.begin(budget.operation('scope-a', uuid4(), 1), 0)
    monkeypatch.setattr(menu_budget, 'SUBLIMIT', 0)
    with pytest.raises(MenuLimit):
        budget.begin(budget.operation('scope-b', uuid4(), 1), 0)
    assert _rows(budget) == before and all(state == 'RECEIVED' for _, state in before)


def test_other_model_rows_keep_their_prices():
    from cj_usage.authorization_budget import _price_receipt
    from cj_usage.roadbook_budget import roadbook_price
    from cj_usage.translation_budget import TEXT_MODEL, translation_price

    roadbook = dict(service='roadbook.1', region='cn-beijing', model_id='qwen3.8-flash', day='2026-11-26',
                    places=1, stage=0, receipt_sha256='0' * 64, usage=_usage(1200, 600))
    translation = dict(service='translation.1', region='cn-beijing', model_id=TEXT_MODEL, day='2026-11-26',
                       modality='text', units=1, stage=0, receipt_sha256='0' * 64, usage=_usage(100, 50))
    menu = _receipt()
    assert _price_receipt('model', canonical(roadbook).decode()) == roadbook_price(roadbook) is not None
    assert _price_receipt('model', canonical(translation).decode()) == translation_price(translation) is not None
    assert _price_receipt('model', canonical(menu).decode()) == menu_price(menu) is not None
    assert _price_receipt('model', canonical(dict(menu, model_id='qwen-plus')).decode()) is None
