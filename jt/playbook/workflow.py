"""In-process case workflow for stage 2 synthetic exercises."""

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from typing import Literal
from uuid import UUID, uuid4

from jt.common import Case, CaseExecution, PlaybookStep, Signal, SignalType

from .catalog import PLAYBOOKS_BY_SIGNAL

StaffAction = Literal["advance", "confirm", "reject"]
StepAction = StaffAction | Literal["record_customer_consent"]
AuditAction = StepAction | Literal["open", "merge"]
Denial = Literal[
    "case_not_found",
    "stale_revision",
    "case_closed",
    "step_mismatch",
    "draft_required",
    "draft_pending",
    "customer_consent_required",
    "customer_consent_not_required",
    "customer_consent_already_recorded",
]
CaseKey = tuple[str, SignalType, int | None]


class IntakeDenied(ValueError):
    """The signal cannot be used to create or merge a case."""


@dataclass(frozen=True)
class CaseAuditEvent:
    occurred_at: datetime
    action: AuditAction
    case_id: UUID
    actor_id: str | None
    step_id: str | None
    revision: int | None
    outcome: Literal["applied", "denied"]
    reason: Denial | None = None


@dataclass(frozen=True)
class CaseIntake:
    execution: CaseExecution
    audit: CaseAuditEvent | None


@dataclass(frozen=True)
class CaseActionResult:
    execution: CaseExecution | None
    audit: CaseAuditEvent


def _case_key(signal: Signal) -> CaseKey:
    conversations = {event.conversation_id for event in signal.source_events}
    versions = {
        event.travel_reference_version for event in signal.source_events
        if event.travel_reference_version is not None
    }
    if len(conversations) != 1 or len(versions) > 1:
        raise IntakeDenied("signal has mixed conversation or itinerary scope")
    return next(iter(conversations)), signal.signal_type, next(iter(versions), None)


def _update(
    current: CaseExecution,
    *,
    step_index: int,
    draft: str | None = None,
    customer_consent_recorded: bool = False,
) -> CaseExecution:
    status = "closed" if step_index == len(current.case.steps) else "in_progress"
    return CaseExecution(
        schema_version="jt-case-execution.v1",
        case=current.case.model_copy(update={"status": status}),
        revision=current.revision + 1,
        step_index=step_index,
        draft=draft,
        customer_consent_recorded=customer_consent_recorded,
    )


def _transition(
    current: CaseExecution,
    step: PlaybookStep,
    action: StepAction,
    consent_step_id: str | None,
) -> CaseExecution | Denial:
    if action == "record_customer_consent":
        if consent_step_id != step.step_id:
            return "step_mismatch"
        if not step.requires_customer_confirmation:
            return "customer_consent_not_required"
        if step.mode == "ai_draft_human_confirm" and current.draft is None:
            return "draft_required"
        if current.customer_consent_recorded:
            return "customer_consent_already_recorded"
        return _update(
            current, step_index=current.step_index, draft=current.draft, customer_consent_recorded=True
        )

    if action == "advance" and step.mode == "ai_draft_human_confirm":
        if current.draft is not None:
            return "draft_pending"
        return _update(current, step_index=current.step_index, draft=f"合成演练草稿 · {step.step_id}")
    if action in ("confirm", "reject") and current.draft is None:
        return "draft_required"
    if action == "reject":
        return _update(current, step_index=current.step_index)
    if step.requires_customer_confirmation and not current.customer_consent_recorded:
        return "customer_consent_required"
    return _update(current, step_index=current.step_index + 1)


class CaseWorkflow:
    """Own case creation and transitions. Consumers own identity checks and the audit store."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._cases: dict[UUID, CaseExecution] = {}
        self._signal_cases: dict[str, tuple[Signal, UUID]] = {}
        self._latest_by_key: dict[CaseKey, UUID] = {}

    def ingest(self, signal: Signal) -> CaseIntake:
        with self._lock:
            previous = self._signal_cases.get(signal.signal_id)
            if previous is not None:
                accepted, case_id = previous
                if accepted != signal:
                    raise IntakeDenied("conflicting content for an accepted signal ID")
                return CaseIntake(self._cases[case_id], audit=None)

            playbook = PLAYBOOKS_BY_SIGNAL.get(signal.signal_type)
            if playbook is None:
                raise IntakeDenied("no playbook for this signal type")
            key = _case_key(signal)
            case_id = self._latest_by_key.get(key)
            now = datetime.now(UTC)
            if case_id is not None and self._cases[case_id].case.status != "closed":
                current = self._cases[case_id]
                linked_case = current.case.model_copy(
                    update={"signal_ids": (*current.case.signal_ids, signal.signal_id)}
                )
                execution = current.model_copy(
                    update={"case": linked_case, "revision": current.revision + 1}
                )
                action = "merge"
            else:
                case_id = uuid4()
                case = Case(
                    schema_version="jt-case.v1",
                    case_id=case_id,
                    signal_ids=(signal.signal_id,),
                    severity=signal.severity,
                    created_at=now,
                    status="open",
                    playbook_id=playbook.playbook_id,
                    playbook_version=playbook.version,
                    steps=tuple(step.to_case_step() for step in playbook.steps),
                )
                execution = CaseExecution(
                    schema_version="jt-case-execution.v1",
                    case=case,
                    revision=0,
                    step_index=0,
                    draft=None,
                    customer_consent_recorded=False,
                )
                action = "open"
            self._cases[case_id] = execution
            self._signal_cases[signal.signal_id] = (signal, case_id)
            self._latest_by_key[key] = case_id
            audit = CaseAuditEvent(now, action, case_id, None, None, execution.revision, "applied")
            return CaseIntake(execution, audit)

    def get(self, case_id: UUID) -> CaseExecution | None:
        with self._lock:
            return self._cases.get(case_id)

    def advance(self, case_id: UUID, *, expected_revision: int, actor_id: str) -> CaseActionResult:
        return self._apply(case_id, expected_revision, "advance", actor_id)

    def confirm(self, case_id: UUID, *, expected_revision: int, actor_id: str) -> CaseActionResult:
        return self._apply(case_id, expected_revision, "confirm", actor_id)

    def reject(self, case_id: UUID, *, expected_revision: int, actor_id: str) -> CaseActionResult:
        return self._apply(case_id, expected_revision, "reject", actor_id)

    def record_synthetic_customer_consent(
        self, case_id: UUID, *, expected_revision: int, step_id: str
    ) -> CaseActionResult:
        """Record the synthetic customer's choice from the exercise harness, never a staff action."""
        return self._apply(case_id, expected_revision, "record_customer_consent", None, step_id)

    def _apply(
        self,
        case_id: UUID,
        expected_revision: int,
        action: StepAction,
        actor_id: str | None,
        consent_step_id: str | None = None,
    ) -> CaseActionResult:
        with self._lock:
            current = self._cases.get(case_id)
            step = current.active_step if current is not None else None
            reason: Denial | None = None
            if current is None:
                reason = "case_not_found"
            elif current.revision != expected_revision:
                reason = "stale_revision"
            elif step is None:
                reason = "case_closed"
            else:
                result = _transition(current, step, action, consent_step_id)
                if isinstance(result, CaseExecution):
                    current = result
                    self._cases[case_id] = current
                else:
                    reason = result
            audit = CaseAuditEvent(
                occurred_at=datetime.now(UTC),
                action=action,
                case_id=case_id,
                actor_id=actor_id,
                step_id=step.step_id if step is not None else None,
                revision=current.revision if current is not None else None,
                outcome="applied" if reason is None else "denied",
                reason=reason,
            )
            return CaseActionResult(current, audit)
