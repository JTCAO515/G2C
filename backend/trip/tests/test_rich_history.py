"""Pure rich undo protection controls; no DTO supplies current source authority."""
from contextlib import contextmanager
from copy import copy, deepcopy
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
import threading

import pytest

from cj_trip.domain import Conflict, Denied, Trip, packed
from cj_trip.postgres import Repository
from cj_trip.rich_history import protect_fixed
from cj_trip import rich_history
from cj_auth.interfaces import AdmissionDecision, AdmissionReason, AdmissionStatus, TrustedPrincipal
from cj_trip.auth_boundary import Boundary
from cj_api.local_app import scope_for
from cj_trip.rich_undo import RichUndo
from cj_trip.structured_v4 import calendar_validation_view

CASES = json.loads((Path(__file__).resolve().parents[3]/'contracts/trip/structured-examples.4.json').read_bytes())['cases']


def no_connection():
    raise AssertionError('unconfigured capability must refuse before database access')


def trip(document, version=1): return Trip('original-trip', version, packed(document))


def test_rich_fixed_original_metadata_is_complete_and_unlocked_changes_can_be_undone():
    value = deepcopy(CASES['protected_fixed']['content'])
    protect_fixed(trip(value, 2), trip(value))
    unlocked = next(i for i in value['items'] if i['fixed'] != {'state': 'known', 'value': True})
    unlocked['text'] = 'An explicitly different proposed stop'
    protect_fixed(trip(CASES['protected_fixed']['content'], 2), trip(value))


@pytest.mark.parametrize('change', [
    lambda i: i.update(text='Changed fixed commitment'),
    lambda i: i.update(note='Changed fixed note'),
    lambda i: i['place'].update(name_en='Changed fixed place'),
    lambda i: i.update(fixed={'state': 'known', 'value': False}),
])
def test_rich_fixed_base_or_metadata_cannot_change(change):
    before = deepcopy(CASES['protected_fixed']['content'])
    after = deepcopy(before)
    fixed = next(i for i in after['items'] if i['fixed'] == {'state': 'known', 'value': True})
    change(fixed)
    with pytest.raises(Conflict): protect_fixed(trip(before, 2), trip(after))


def test_explicit_rich_calendar_history_keeps_the_same_original_base():
    rich = deepcopy(CASES['protected_fixed']['content'])
    calendar = calendar_validation_view(rich)
    protect_fixed(trip(rich, 2), trip(calendar))
    fixed = next(i for i in calendar['items'] if i['fixed'] == {'state': 'known', 'value': True})
    fixed['text'] = 'A different commitment'
    with pytest.raises(Conflict): protect_fixed(trip(rich, 2), trip(calendar))


def test_bare_rich_or_legacy_repository_does_not_enable_undo_or_undo_receipts():
    raw = packed(dict(version='TRIP-lio-undo.3', action_id='undo-original', trip_id='original-trip',
        expected_version=2, original_hash='a'*64, content_version='structured.4'))
    request = RichUndo.parse(raw)
    assert request.raw == raw
    for flags in ({}, {'structured': True}, {'structured': True, 'calendar': True}):
        repository = Repository(no_connection, 'owner', **flags)
        with pytest.raises(Denied): repository.undo_rich(request)
        with pytest.raises(Denied): repository.rich_undo_receipt(request)
    rich = Repository(no_connection, 'owner', structured=True, calendar=True, rich=True)
    assert rich.rich_undo_sources is None
    with pytest.raises(Denied): rich.undo_rich(request)
    principal = TrustedPrincipal('issuer', 'subject', 'audience', 1, 1, 9999999999)
    class Checker:
        def check(self, token):
            return AdmissionDecision(AdmissionStatus.ALLOWED, AdmissionReason.ACCEPTED, principal)
    boundary = Boundary(Checker(), lambda _: (no_connection, 'owner'), structured=True, calendar=True, rich=True)
    for invoke in (lambda context: context.undo_lio(request), lambda context: context.undo_calendar(request)):
        with pytest.raises(ValueError, match='validated original action'):
            boundary.with_operation('synthetic', invoke)


def history_fixture(monkeypatch):
    principal = TrustedPrincipal('issuer', 'subject', 'audience', 1, 1, 9999999999)
    owner = scope_for(principal.issuer, principal.subject)
    raw = packed(dict(text='Fixture original bytes'))
    reference = dict(conversation_id='fixture-chat', generation='fixture-generation', message_id='fixture-message',
        run_id='fixture-run', sequence=1, input_sha256=sha256(raw).hexdigest(), message_version='MESSAGE-send.2',
        lio_protocol='LIO-message.4')
    original = dict(protocol='LIO-message.4', message_id='fixture-message', run_id='fixture-run',
        input_sha256=reference['input_sha256'], question_day='2026-11-14')
    value = dict(version='TRIP-RICH-PLAN-SOURCE.1', planning_profile=dict(original=original, profile=dict(factors=[])),
        rich_source=dict(original=original), calendar_basis=dict(fixed_bindings=dict(
            reference=reference, needs_id='fixture-needs', needs_version=1, bindings=[])))
    origin = dict(message_scope=owner, needs_id='fixture-needs', needs_version=1, source=packed(value))
    state = dict(principal=principal, entered=0)
    class Database:
        def message_repository(self, scope):
            assert scope == owner
            return object()
        @contextmanager
        def connect(self, scope):
            assert scope == owner
            yield SimpleNamespace(cursor=lambda: object())
    class Authority:
        def __init__(self, repository, admit): pass
        @contextmanager
        def hold_for_effect(self, binding):
            state['entered'] += 1
            def earlier(mid):
                if mid != 'fixture-message' or state.get('missing_anchor'):
                    raise Denied('fixture original unavailable')
                return SimpleNamespace(stored=SimpleNamespace(raw=raw, receipt=SimpleNamespace(sequence=1)))
            yield SimpleNamespace(reference=SimpleNamespace(public_value=lambda: reference),
                original_message=lambda: SimpleNamespace(raw=raw), check=lambda b: None, source_original=earlier)
    monkeypatch.setattr(rich_history, 'MessageContextAuthority', Authority)
    monkeypatch.setattr(rich_history, 'exploration_original_protocol', lambda c, b, s: 'LIO-message.4')
    return SimpleNamespace(database=Database(), admit=lambda: state['principal']), origin, state, principal, owner


def test_issued_history_frame_has_actual_bound_identity_and_copies_do_not_outlive_it(monkeypatch):
    source, origin, state, principal, owner = history_fixture(monkeypatch)
    with pytest.raises(Denied): rich_history.HeldHistory(principal, owner, lambda: None)
    with rich_history.history_sources(source, origin) as held:
        assert (held.principal, held.scope) == (principal, owner)
        held.check()
        copied = copy(held)
        errors = []
        def other_thread():
            try: held.check()
            except Denied: errors.append(True)
        thread = threading.Thread(target=other_thread)
        thread.start(); thread.join()
        assert errors == [True] and state['entered'] == 1
    for expired in (held, copied):
        with pytest.raises(Denied): expired.check()


def test_changed_history_principal_withholds_the_frame(monkeypatch):
    source, origin, state, principal, owner = history_fixture(monkeypatch)
    with pytest.raises(Denied):
        with rich_history.history_sources(source, origin) as held:
            state['principal'] = TrustedPrincipal('issuer', 'foreign', 'audience', 1, 1, 9999999999)
            held.check()


def test_history_owner_or_protocol_conflict_is_rejected_before_any_message_hold(monkeypatch):
    source, origin, state, principal, owner = history_fixture(monkeypatch)
    with pytest.raises(Denied):
        with rich_history.history_sources(source, dict(origin, message_scope='foreign-owner')): pass
    wrong = json.loads(origin['source'])
    wrong['calendar_basis']['fixed_bindings']['reference']['lio_protocol'] = 'LIO-message.3'
    with pytest.raises(Denied):
        with rich_history.history_sources(source, dict(origin, source=packed(wrong))): pass
    assert state['entered'] == 0


def test_historical_profile_uses_actual_quote_anchor_not_its_projection(monkeypatch):
    source, origin, state, principal, owner = history_fixture(monkeypatch)
    value = json.loads(origin['source'])
    anchor = dict(kind='message', message_id='fixture-message', sequence=1, quote='original', offset=8)
    value['planning_profile']['profile']['factors'] = [dict(factor_key='interests', sources=[anchor])]
    with rich_history.history_sources(source, dict(origin, source=packed(value))) as held: held.check()
    anchor['offset'] = 9
    with pytest.raises(Denied, match='quote original'):
        with rich_history.history_sources(source, dict(origin, source=packed(value))): pass
    anchor['offset'] = 8
    state['missing_anchor'] = True
    with pytest.raises(Denied, match='original unavailable'):
        with rich_history.history_sources(source, dict(origin, source=packed(value))): pass


def test_historical_default_anchor_needs_its_literal_original_trigger(monkeypatch):
    source, origin, state, principal, owner = history_fixture(monkeypatch)
    value = json.loads(origin['source'])
    value['planning_profile']['profile']['factors'] = [dict(factor_key='city', sources=[
        dict(kind='default', message_id='fixture-message', policy='fixture-policy')])]
    with pytest.raises(Denied, match='no actual plan trigger'):
        with rich_history.history_sources(source, dict(origin, source=packed(value))): pass


def test_new_selection_history_adds_grammar_without_replacing_original_holders(monkeypatch):
    from cj_trip.place_selection import VERSION, PLAN_SOURCE
    source, origin, state, principal, owner = history_fixture(monkeypatch)
    value=json.loads(origin['source'])
    value.update(version=PLAN_SOURCE,place_selection_version=VERSION,
                 provider_outcomes=[],provider_records=[],place_selections=[])
    with rich_history.history_sources(source,dict(origin,source=packed(value))) as held:
        held.check()
        assert held.scope==owner and state['entered']==1
    with pytest.raises(Denied):held.check()


@pytest.mark.parametrize('change',[
    lambda v:v.update(place_selections=[{'status':'model says unavailable'}]),
    lambda v:v.update(place_selection_version='unissued-policy'),
    lambda v:v.pop('provider_outcomes'),
])
def test_new_selection_history_rejects_bad_basis_before_message_holder(monkeypatch,change):
    from cj_trip.place_selection import VERSION, PLAN_SOURCE
    source, origin, state, _, _ = history_fixture(monkeypatch)
    value=json.loads(origin['source'])
    value.update(version=PLAN_SOURCE,place_selection_version=VERSION,
                 provider_outcomes=[],provider_records=[],place_selections=[])
    change(value)
    with pytest.raises(Denied,match='historical original place selection differs'):
        with rich_history.history_sources(source,dict(origin,source=packed(value))):pass
    assert state['entered']==0
