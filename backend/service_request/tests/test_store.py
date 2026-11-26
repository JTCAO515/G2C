"""Offline SERVICE-REQUEST@1 store checks (#1769); PostgreSQL behaviour runs in store_pg.py."""
import pytest

from cj_service_request.contract import InvalidInput
from cj_service_request import store
from cj_service_request.lifecycle import ServiceRequestHook, TABLES

POLICY = {'cancellation_policy': {'text_en': 'a', 'text_zh': '甲'}, 'refund_by': {'text_en': 'b', 'text_zh': '乙'}}


def test_flag_defaults_off_and_only_exact_one_enables():
    assert store.enabled({}) is False
    for value in ('0', 'true', 'yes', ' 1', ''):
        assert store.enabled({store.FLAG: value}) is False
    assert store.enabled({store.FLAG: '1'}) is True


def test_repository_requires_explicit_scope_and_policy():
    for scope in ('', None, 1):
        with pytest.raises(store.Unavailable):
            store.Repository(lambda: None, scope, policy=POLICY)
    with pytest.raises(store.Unavailable):
        store.Repository(lambda: None, 's', policy={})
    with pytest.raises(InvalidInput):
        store.Repository(lambda: None, 's', policy={**POLICY, 'refund_by': {'text_en': ' ', 'text_zh': '乙'}})


def test_disabled_submit_never_opens_storage_for_new_but_parses_first():
    calls = []
    repo = store.Repository(lambda: calls.append(1), 's', policy=POLICY, flag=lambda: False)
    with pytest.raises(InvalidInput):
        repo.submit(b'{}')
    assert calls == []


def test_disabled_flag_blocks_only_non_terminal_progress_before_storage():
    calls = []
    repo = store.Repository(lambda: calls.append(1), 's', policy=POLICY, flag=lambda: False)
    with pytest.raises(store.FeatureDisabled):
        repo.transition('sr_' + '0' * 32, 'accepted', actor='staff', staff_ref='x',
                        evidence_kind='staff_accept', evidence_body='ok')
    assert calls == []


@pytest.mark.parametrize('quote', [
    None, {}, {'amount_minor': 0, 'currency': 'CNY', 'payment': 'outside_app', 'instructions_en': 'a', 'instructions_zh': 'b'},
    {'amount_minor': 1.5, 'currency': 'CNY', 'payment': 'outside_app', 'instructions_en': 'a', 'instructions_zh': 'b'},
    {'amount_minor': 100, 'currency': 'USD', 'payment': 'outside_app', 'instructions_en': 'a', 'instructions_zh': 'b'},
    {'amount_minor': 100, 'currency': 'CNY', 'payment': 'link', 'instructions_en': 'a', 'instructions_zh': 'b'},
])
def test_quote_shape(quote):
    with pytest.raises(InvalidInput):
        store._quote(quote)


def test_escort_shape():
    good = {'escort_display_name': 'A', 'arrival': {'local_time': '2026-12-10T09:00', 'place': 'Gate'}}
    assert store._escort(good) == good
    for bad in (None, {**good, 'arrival': None}, {**good, 'arrival': {'local_time': '9:00', 'place': 'Gate'}},
                {**good, 'escort_display_name': ' '}):
        with pytest.raises(InvalidInput):
            store._escort(bad)


def test_staff_ref_only_for_staff_and_payload_only_for_its_state():
    repo = store.Repository(lambda: None, 's', policy=POLICY, flag=lambda: True)
    rid = 'sr_' + '0' * 32
    with pytest.raises(InvalidInput):
        repo.transition(rid, 'user_cancelled', actor='user', staff_ref='x', evidence_kind='cancellation', evidence_body='x')
    with pytest.raises(InvalidInput):
        repo.transition(rid, 'accepted', actor='staff', evidence_kind='staff_accept', evidence_body='x')
    with pytest.raises(InvalidInput):
        repo.transition(rid, 'accepted', actor='staff', staff_ref='x', evidence_kind='staff_accept', evidence_body='x',
                        quote={'amount_minor': 1})


def test_shared_with_escort_matches_contract_rules():
    base = {'meeting_purpose': '', 'counterpart': None}
    assert store.shared_with_escort(base) == ['customer_name', 'language', 'service_date', 'time_window', 'venue',
                                              'contact_phone']
    assert 'note' not in store.shared_with_escort({'meeting_purpose': 'x', 'counterpart': {'company': 'c', 'name': ''}})


def test_hook_rejects_foreign_or_non_account_requests():
    from cj_cleanup.core import Denied

    class Req:
        subject_digest, domain_scope = 'a' * 64, 'scope'

        class selection:
            kind = 'items'

    class St:
        subject_digest = 'a' * 64
    with pytest.raises(Denied):
        ServiceRequestHook(St, 'scope').execute(Req)
    assert TABLES[-1] == 'cj_service_request'
