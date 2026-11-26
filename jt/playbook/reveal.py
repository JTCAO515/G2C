"""Step-scoped reveal rules for synthetic case data."""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from jt.common import CaseExecution

from .workflow import CaseWorkflow


class RevealField(StrEnum):
    TRAVELER_NAME = "traveler_name"
    CONTACT_PHONE = "contact_phone"
    MEETING_LOCATION = "meeting_location"
    PASSPORT_NUMBER = "passport_number"


class RevealReason(StrEnum):
    LOCATE_TRAVELER = "locate_traveler"
    VERIFY_LOST_DOCUMENT_REPORT = "verify_lost_document_report"


_MASKS = {
    RevealField.TRAVELER_NAME: "<NAME_1>",
    RevealField.CONTACT_PHONE: "<PHONE_1>",
    RevealField.MEETING_LOCATION: "<LOCATION_1>",
    RevealField.PASSPORT_NUMBER: "<PASSPORT_1>",
}
_FIELDS = {item.value: item for item in RevealField}
_REASONS = {item.value: item for item in RevealReason}
_STEP_FIELDS: dict[tuple[str, str, str], frozenset[RevealField]] = {
    ("p0_assistance", "1", "verify_assistance"): frozenset({
        RevealField.CONTACT_PHONE, RevealField.MEETING_LOCATION,
    }),
    ("document_loss", "1", "verify_document_situation"): frozenset({
        RevealField.TRAVELER_NAME,
    }),
}
REVEAL_TTL = timedelta(minutes=5)

Denial = Literal[
    "forbidden", "case_not_found", "case_closed", "field_not_allowed", "reason_required",
    "grant_not_found", "grant_expired", "case_changed", "value_unavailable",
]


def masked_value(field_name: RevealField) -> str:
    """The default view does not need access to the stored value."""
    return _MASKS[field_name]


@dataclass(frozen=True)
class RevealActor:
    """Staff identity, role and assignment supplied by the authenticated server."""

    actor_id: str
    role: str
    assigned_actor_id: str | None


@dataclass(frozen=True)
class RevealGrant:
    grant_id: UUID = field(repr=False)
    case_id: UUID
    actor_id: str
    step_id: str
    revision: int
    field_name: RevealField
    reason: RevealReason
    expires_at: datetime


@dataclass(frozen=True)
class RevealAudit:
    occurred_at: datetime
    action: Literal["request_reveal", "reveal"]
    case_id: UUID
    actor_id: str
    step_id: str | None
    field_name: RevealField | None
    reason: RevealReason | None
    outcome: Literal["applied", "denied"]
    denial: Denial | None


@dataclass(frozen=True)
class RevealResult:
    audit: RevealAudit
    grant: RevealGrant | None = None
    value: str | None = field(default=None, repr=False)


def _access_denial(actor: RevealActor, current: CaseExecution | None) -> Denial | None:
    if not actor.actor_id or actor.role != "operator" or actor.actor_id != actor.assigned_actor_id:
        return "forbidden"
    if current is None:
        return "case_not_found"
    if current.case.status == "closed":
        return "case_closed"
    return None


def _field_allowed(current: CaseExecution, step_id: str, field_name: RevealField) -> bool:
    scope = current.case.playbook_id, current.case.playbook_version, step_id
    return (
        field_name is not RevealField.PASSPORT_NUMBER
        and field_name in _STEP_FIELDS.get(scope, ())
    )


class RevealWorkflow:
    """Issue and redeem in-memory grants against the same live case workflow."""

    def __init__(
        self, workflow: CaseWorkflow, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._workflow = workflow
        self._clock = clock
        self._grants: dict[UUID, RevealGrant] = {}

    def request(
        self, case_id: UUID, *, actor: RevealActor, field_name: str, reason: str,
    ) -> RevealResult:
        candidate = _FIELDS.get(field_name)
        required_reason = _REASONS.get(reason.strip())
        with self._workflow.locked_case(case_id) as current:
            now = self._clock()
            step = current.active_step if current is not None else None
            denial = _access_denial(actor, current)
            grant = None
            if denial is None and current is not None and step is not None:
                if candidate is None or not _field_allowed(current, step.step_id, candidate):
                    denial = "field_not_allowed"
                elif required_reason is None:
                    denial = "reason_required"
                else:
                    grant = RevealGrant(
                        uuid4(), case_id, actor.actor_id, step.step_id, current.revision,
                        candidate, required_reason, now + REVEAL_TTL,
                    )
                    self._grants[grant.grant_id] = grant
            audit = RevealAudit(
                now, "request_reveal", case_id, actor.actor_id, step.step_id if step else None,
                candidate, required_reason, "applied" if grant else "denied", denial,
            )
            return RevealResult(audit, grant=grant)

    def reveal(
        self,
        case_id: UUID,
        *,
        actor: RevealActor,
        grant_id: UUID,
        lookup: Callable[[UUID, RevealField], str | None],
    ) -> RevealResult:
        with self._workflow.locked_case(case_id) as current:
            now = self._clock()
            step = current.active_step if current is not None else None
            denial = _access_denial(actor, current)
            grant = self._grants.get(grant_id)
            if grant is not None and (grant.case_id != case_id or grant.actor_id != actor.actor_id):
                grant = None
            value = None
            if denial is None and current is not None and step is not None:
                if grant is None:
                    denial = "grant_not_found"
                elif now >= grant.expires_at:
                    denial = "grant_expired"
                elif current.revision != grant.revision or step.step_id != grant.step_id:
                    denial = "case_changed"
                elif not _field_allowed(current, step.step_id, grant.field_name):
                    denial = "field_not_allowed"
                else:
                    value = lookup(case_id, grant.field_name)
                    now = self._clock()
                    if now >= grant.expires_at:
                        value = None
                        denial = "grant_expired"
                    elif value is None:
                        denial = "value_unavailable"
            audit = RevealAudit(
                now, "reveal", case_id, actor.actor_id, step.step_id if step else None,
                grant.field_name if grant else None, grant.reason if grant else None,
                "applied" if value is not None else "denied", denial,
            )
            return RevealResult(audit, value=value)
