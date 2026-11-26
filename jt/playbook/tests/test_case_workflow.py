from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from jt.common import Case, CaseExecution, EmptyEventState, EventRef, Signal
from jt.playbook import CaseWorkflow, IntakeDenied

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def signal(signal_id, *, signal_type="document_loss", severity="P1", conversation="synthetic",
           itinerary=None, extra=()):
    source = EventRef(
        schema_version="jt-event-ref.v1",
        event_id=f"event-{signal_id}",
        conversation_id=conversation,
        message_id=f"message-{signal_id}",
        sequence=1,
        travel_reference_version=itinerary,
        occurred_at=NOW,
        event_type="message_accepted",
        event_state=EmptyEventState(),
    )
    return Signal(
        schema_version="jt-signal.v1",
        signal_id=signal_id,
        source_events=(source, *extra),
        detected_at=NOW,
        signal_type=signal_type,
        severity=severity,
        rules_version="synthetic.1",
        redaction_version="synthetic.1",
    )


def act(action, current):
    return action(current.case.case_id, expected_revision=current.revision, actor_id="staff-synthetic")


def consent(workflow, current, step_id):
    return workflow.record_synthetic_customer_consent(
        current.case.case_id, expected_revision=current.revision, step_id=step_id
    )


@pytest.mark.parametrize(("signal_type", "severity", "expected"), [
    ("safety", "P0", "p0_assistance"),
    ("illness", "P0", "p0_assistance"),
    ("document_loss", "P1", "document_loss"),
    ("itinerary_disruption", "P2", "flight_change"),
    ("ai_failure_loop", "P4", "ai_failure"),
])
def test_signal_creates_versioned_case_without_user_identity(signal_type, severity, expected):
    result = CaseWorkflow().ingest(signal("sig-1", signal_type=signal_type, severity=severity))
    current = result.execution
    assert result.audit.action == "open"
    assert current.case.case_id.version == 4
    assert current.case.playbook_id == expected and current.case.playbook_version == "1"
    assert current.case.signal_ids == ("sig-1",)
    assert current.case.severity == severity
    assert current.case.status == "open"
    assert current.step_index == current.revision == 0
    assert Case.model_validate_json(current.case.model_dump_json()) == current.case
    assert CaseExecution.model_validate_json(current.model_dump_json()) == current
    assert "user_uuid" not in current.model_dump_json()
    with pytest.raises(ValidationError, match="user_uuid"):
        CaseExecution.model_validate(current.model_dump() | {"user_uuid": "synthetic"})


def test_idempotent_ingest_merge_and_conflicting_id():
    workflow = CaseWorkflow()
    one = signal("one", itinerary=1)
    original = workflow.ingest(one)
    replay = workflow.ingest(one)
    assert replay.execution == original.execution and replay.audit is None
    merged = workflow.ingest(signal("two", itinerary=1))
    assert merged.execution.case.case_id == original.execution.case.case_id
    assert merged.execution.case.signal_ids == ("one", "two")
    assert merged.audit.action == "merge" and merged.execution.revision == 1
    assert workflow.ingest(one).execution == merged.execution
    with pytest.raises(IntakeDenied, match="conflicting"):
        workflow.ingest(signal("one", itinerary=2))
    assert workflow.get(merged.execution.case.case_id) == merged.execution


@pytest.mark.parametrize("changes", [
    {"conversation": "another"},
    {"itinerary": 2},
    {"itinerary": None},
    {"signal_type": "itinerary_disruption", "severity": "P2"},
])
def test_active_cases_only_merge_matching_scope_and_type(changes):
    workflow = CaseWorkflow()
    first = workflow.ingest(signal("one", itinerary=1))
    second = workflow.ingest(signal("two", **({"itinerary": 1} | changes)))
    assert first.execution.case.case_id != second.execution.case.case_id


@pytest.mark.parametrize("params", [{"conversation": "another"}, {"itinerary": 2}])
def test_mixed_event_scope_rejected(params):
    workflow = CaseWorkflow()
    other = signal("other", **({"itinerary": 1} | params)).source_events
    with pytest.raises(IntakeDenied, match="mixed"):
        workflow.ingest(signal("one", itinerary=1, extra=other))


def test_unmapped_signal_is_explicitly_rejected():
    with pytest.raises(IntakeDenied, match="no playbook"):
        CaseWorkflow().ingest(signal("one", signal_type="change_request", severity="P3"))


def test_advance_confirm_reject_and_audit_replay_after_close():
    workflow = CaseWorkflow()
    original = signal("one")
    opened = workflow.ingest(original).execution
    premature = act(workflow.confirm, opened)
    assert (premature.audit.outcome, premature.audit.reason) == ("denied", "draft_required")
    assert premature.execution == opened

    automatic = act(workflow.advance, opened)
    assert automatic.audit.action == "advance"
    assert automatic.audit.step_id == "prepare_replacement_checklist"
    assert automatic.audit.actor_id == "staff-synthetic"
    manual = act(workflow.advance, automatic.execution)
    assert manual.audit.step_id == "verify_document_situation"
    drafted = act(workflow.advance, manual.execution)
    assert drafted.execution.draft.startswith("合成演练草稿")
    assert act(workflow.advance, drafted.execution).audit.reason == "draft_pending"
    denied = act(workflow.reject, drafted.execution)
    assert denied.audit.action == "reject" and denied.audit.outcome == "applied"
    assert denied.execution.step_index == drafted.execution.step_index
    assert denied.execution.draft is None

    redrafted = act(workflow.advance, denied.execution)
    final = act(workflow.confirm, redrafted.execution)
    assert final.audit.action == "confirm" and final.audit.outcome == "applied"
    assert final.execution.case.status == "closed" and final.execution.active_step is None
    assert act(workflow.advance, final.execution).audit.reason == "case_closed"
    assert workflow.ingest(original).execution == final.execution
    assert workflow.ingest(signal("new")).execution.case.case_id != opened.case.case_id


def test_itinerary_and_money_steps_require_separate_customer_consent():
    workflow = CaseWorkflow()
    opened = workflow.ingest(signal("flight", signal_type="itinerary_disruption", severity="P2")).execution
    ready = act(workflow.advance, opened).execution
    assert ready.active_step.requires_customer_confirmation
    early = consent(workflow, ready, "draft_itinerary_change")
    assert early.audit.reason == "draft_required"
    drafted = act(workflow.advance, ready).execution
    staff_only = act(workflow.confirm, drafted)
    assert staff_only.audit.reason == "customer_consent_required" and staff_only.execution == drafted
    wrong_step = consent(workflow, drafted, "simulate_paid_rebooking")
    assert wrong_step.audit.reason == "step_mismatch"

    agreed = consent(workflow, drafted, "draft_itinerary_change").execution
    rejected = act(workflow.reject, agreed).execution
    assert rejected.draft is None and not rejected.customer_consent_recorded
    restored = act(workflow.advance, rejected).execution
    assert restored.active_step.step_id == "draft_itinerary_change"
    assert consent(workflow, drafted, "draft_itinerary_change").audit.reason == "stale_revision"
    assert act(workflow.confirm, restored).audit.reason == "customer_consent_required"

    recorded = consent(workflow, restored, "draft_itinerary_change")
    assert recorded.audit.action == "record_customer_consent" and recorded.audit.actor_id is None
    duplicate = consent(workflow, recorded.execution, "draft_itinerary_change")
    assert duplicate.audit.reason == "customer_consent_already_recorded"
    next_step = act(workflow.confirm, recorded.execution).execution
    assert next_step.active_step.step_id == "simulate_paid_rebooking"
    assert not next_step.customer_consent_recorded
    assert act(workflow.advance, next_step).audit.reason == "customer_consent_required"
    authorized = consent(workflow, next_step, "simulate_paid_rebooking").execution
    assert act(workflow.advance, authorized).execution.case.status == "closed"


def test_stale_actions_return_audit_and_cannot_skip_steps():
    workflow = CaseWorkflow()
    current = workflow.ingest(signal("one")).execution
    with ThreadPoolExecutor(max_workers=2) as pool:
        attempts = list(pool.map(lambda _: act(workflow.advance, current), range(2)))
    assert {result.audit.outcome for result in attempts} == {"applied", "denied"}
    assert {result.audit.reason for result in attempts} == {None, "stale_revision"}
    latest = workflow.get(current.case.case_id)
    assert latest.step_index == latest.revision == 1


def test_unknown_case_returns_denial_audit():
    workflow = CaseWorkflow()
    case_id = uuid4()
    result = workflow.reject(case_id, expected_revision=0, actor_id="staff-synthetic")
    assert result.execution is None
    assert result.audit.case_id == case_id
    assert (result.audit.outcome, result.audit.reason) == ("denied", "case_not_found")


@pytest.mark.parametrize("changes", [
    {"schema_version": "jt-case-execution.v2"},
    {"step_index": 4},
    {"step_index": 1},
    {"draft": "synthetic"},
    {"customer_consent_recorded": True},
])
def test_invalid_execution_snapshots_cannot_be_loaded(changes):
    current = CaseWorkflow().ingest(signal("one")).execution
    with pytest.raises(ValidationError):
        CaseExecution.model_validate(current.model_dump() | changes)


def test_case_execution_requires_explicit_version():
    current = CaseWorkflow().ingest(signal("one")).execution
    with pytest.raises(ValidationError, match="schema_version"):
        CaseExecution.model_validate_json(current.model_dump_json(exclude={"schema_version"}))
