from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest

from jt.playbook import CaseWorkflow
from jt.playbook.reveal import (
    REVEAL_TTL, RevealActor, RevealField, RevealReason, RevealWorkflow, masked_value,
)
from jt.synthetic import generate_dataset

OPERATOR = RevealActor("demo-staff-01", "operator", "demo-staff-01")
SYNTHETIC_VALUE = "DEMO_CONTACT_NON_DIALABLE"
REASON = RevealReason.LOCATE_TRAVELER


def advance(workflow, current):
    return workflow.advance(
        current.case.case_id, expected_revision=current.revision, actor_id=OPERATOR.actor_id,
    ).execution


@pytest.fixture
def scenario():
    workflow = CaseWorkflow()
    signal = next(signal for signal in generate_dataset().signals if signal.signal_type == "safety")
    opened = workflow.ingest(signal).execution
    active = advance(workflow, opened)
    now = [datetime(2026, 11, 26, 2, tzinfo=UTC)]
    return workflow, active, now, RevealWorkflow(workflow, clock=lambda: now[0])


def request(rule, case, field=RevealField.CONTACT_PHONE, actor=OPERATOR, reason=REASON):
    return rule.request(case.case.case_id, actor=actor, field_name=field, reason=reason)


def reveal(rule, case, grant_id, lookup, actor=OPERATOR):
    return rule.reveal(case.case.case_id, actor=actor, grant_id=grant_id, lookup=lookup)


def test_default_mask_and_successful_request_then_reveal_return_audit(scenario):
    _, case, now, rule = scenario
    assert masked_value(RevealField.CONTACT_PHONE) == "<PHONE_1>"
    assert masked_value(RevealField.PASSPORT_NUMBER) == "<PASSPORT_1>"
    approved = request(rule, case)
    assert approved.audit.action == "request_reveal"
    assert approved.audit.outcome == "applied"
    assert approved.value is None
    assert approved.grant.expires_at == now[0] + REVEAL_TTL

    lookup = Mock(return_value=SYNTHETIC_VALUE)
    result = reveal(rule, case, approved.grant.grant_id, lookup)
    lookup.assert_called_once_with(case.case.case_id, RevealField.CONTACT_PHONE)
    assert result.value == SYNTHETIC_VALUE
    assert result.audit.action == "reveal"
    assert result.audit.outcome == "applied"
    assert result.audit.field_name is RevealField.CONTACT_PHONE
    assert result.audit.reason is REASON
    assert SYNTHETIC_VALUE not in repr(result) and SYNTHETIC_VALUE not in repr(result.audit)
    assert str(approved.grant.grant_id) not in repr(result.audit)


@pytest.mark.parametrize("field", [RevealField.TRAVELER_NAME, RevealField.PASSPORT_NUMBER, "unknown"])
def test_non_whitelisted_and_passport_fields_are_denied(scenario, field):
    _, case, _, rule = scenario
    rejected = request(rule, case, field=field)
    assert rejected.grant is None and rejected.value is None
    assert rejected.audit.outcome == "denied"
    assert rejected.audit.denial == "field_not_allowed"


@pytest.mark.parametrize("reason", ["", "   ", "PRIVATE_TEXT_MUST_NOT_ENTER_AUDIT"])
def test_missing_or_unrecognized_reason_cannot_issue_grant(scenario, reason):
    _, case, _, rule = scenario
    result = request(rule, case, reason=reason)
    assert result.grant is None
    assert result.audit.denial == "reason_required"
    assert result.audit.reason is None


@pytest.mark.parametrize("actor", [
    RevealActor("demo-staff-01", "reviewer", "demo-staff-01"),
    RevealActor("demo-staff-01", "admin", "demo-staff-01"),
    RevealActor("demo-staff-02", "operator", "demo-staff-01"),
    RevealActor("demo-staff-01", "operator", None),
])
def test_cross_role_and_unassigned_staff_are_rejected_before_read(scenario, actor):
    _, case, _, rule = scenario
    approved = request(rule, case)
    assert request(rule, case, actor=actor).audit.denial == "forbidden"
    lookup = Mock(return_value=SYNTHETIC_VALUE)
    rejected = reveal(rule, case, approved.grant.grant_id, lookup, actor)
    assert rejected.audit.denial == "forbidden"
    assert rejected.value is None
    lookup.assert_not_called()


def test_grant_cannot_follow_case_reassignment_or_another_case(scenario):
    workflow, case, _, rule = scenario
    approved = request(rule, case)
    lookup = Mock(return_value=SYNTHETIC_VALUE)
    new_owner = RevealActor("demo-staff-02", "operator", "demo-staff-02")
    assert reveal(rule, case, approved.grant.grant_id, lookup, new_owner).audit.denial == "grant_not_found"

    fresh_signal = next(signal for signal in generate_dataset().signals if signal.signal_type == "illness")
    other = advance(workflow, workflow.ingest(fresh_signal).execution)
    assert reveal(rule, other, approved.grant.grant_id, lookup).audit.denial == "grant_not_found"
    lookup.assert_not_called()


def test_expired_grant_never_invokes_value_lookup(scenario):
    _, case, now, rule = scenario
    approved = request(rule, case)
    now[0] = approved.grant.expires_at
    lookup = Mock(return_value=SYNTHETIC_VALUE)
    result = reveal(rule, case, approved.grant.grant_id, lookup)
    assert result.audit.denial == "grant_expired"
    assert result.value is None
    lookup.assert_not_called()


def test_grant_expiring_during_lookup_returns_no_value(scenario):
    _, case, now, rule = scenario
    approved = request(rule, case)

    def lookup(_, __):
        now[0] = approved.grant.expires_at
        return SYNTHETIC_VALUE

    result = reveal(rule, case, approved.grant.grant_id, lookup)
    assert result.audit.denial == "grant_expired"
    assert result.value is None


def test_step_shift_and_case_closure_invalidate_existing_grant(scenario):
    workflow, case, _, rule = scenario
    approved = request(rule, case)
    advanced = advance(workflow, case)
    lookup = Mock(return_value=SYNTHETIC_VALUE)
    assert reveal(rule, case, approved.grant.grant_id, lookup).audit.denial == "case_changed"
    assert request(rule, advanced).audit.denial == "field_not_allowed"

    draft = advance(workflow, advanced)
    closed = workflow.confirm(
        draft.case.case_id, actor_id=OPERATOR.actor_id, expected_revision=draft.revision,
    ).execution
    assert closed.case.status == "closed"
    assert request(rule, case).audit.denial == "case_closed"
    result = reveal(rule, case, approved.grant.grant_id, lookup)
    assert result.audit.denial == "case_closed"
    assert result.value is None
    lookup.assert_not_called()


def test_read_without_a_server_recorded_grant_returns_no_value(scenario):
    _, case, _, rule = scenario
    lookup = Mock(return_value=SYNTHETIC_VALUE)
    result = reveal(rule, case, uuid4(), lookup)
    assert result.audit.denial == "grant_not_found"
    assert result.value is None
    lookup.assert_not_called()
