"""Synthetic staff operations data. Web rendering depends on OperationsSource."""

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from threading import RLock
from typing import Protocol

from .store import OperationsAuditDetail


TRANSITIONS = {
    "submitted": ("accepted", "unavailable", "user_cancelled"),
    "accepted": ("quoted", "unavailable", "user_cancelled"),
    "quoted": ("quoted", "arranged", "unavailable", "user_cancelled"),
    "arranged": ("in_progress", "unavailable", "user_cancelled", "outcome_unknown"),
    "in_progress": ("completed", "outcome_unknown"),
    "outcome_unknown": ("completed", "unavailable"),
}
EVIDENCE_KINDS = {
    "accepted": "staff_accept", "quoted": "quote", "arranged": "arrangement", "in_progress": "arrival",
    "completed": "completion_summary", "user_cancelled": "cancellation",
    "unavailable": "unavailable_reason", "outcome_unknown": "unknown_reason",
}
LEAD_TRANSITIONS = {"pending": ("contacted", "converted", "closed"), "contacted": ("converted", "closed")}
SERVICE_TYPE = "gz_business_escort_zh_en"
STAFF_AUDIT = Callable[[OperationsAuditDetail], None]


class OperationMissing(ValueError):
    pass


class OperationConflict(ValueError):
    pass


class EvidenceRequired(ValueError):
    pass


@dataclass(frozen=True)
class Details:
    service_date: str
    time_window: str
    venue: str
    customer_name: str
    contact_phone: str
    meeting_purpose: str


@dataclass(frozen=True)
class History:
    seq: int
    from_state: str | None
    to: str
    at: datetime
    actor_kind: str
    evidence_kind: str
    evidence_ref: str
    evidence: str


@dataclass(frozen=True)
class Quote:
    amount_minor: int
    currency: str = "CNY"
    payment: str = "outside_app"


@dataclass(frozen=True)
class Arrival:
    local_time: str
    place: str


@dataclass(frozen=True)
class HumanService:
    provided_by_human: bool = True
    escort_display_name: str | None = None
    arrival: Arrival | None = None


@dataclass(frozen=True)
class ServiceRequest:
    request_id: str
    client_request_id: str
    service_type: str
    state: str
    details: Details
    history: tuple[History, ...]
    quote: Quote | None = None
    human_service: HumanService = HumanService()

    @property
    def actions(self) -> tuple[str, ...]:
        return TRANSITIONS.get(self.state, ())


@dataclass(frozen=True)
class Lead:
    client_request_id: str
    state: str
    details: Details

    @property
    def actions(self) -> tuple[str, ...]:
        return LEAD_TRANSITIONS.get(self.state, ())


class OperationsSource(Protocol):
    def requests(self) -> tuple[ServiceRequest, ...]: ...
    def request(self, request_id: str) -> ServiceRequest | None: ...
    def leads(self) -> tuple[Lead, ...]: ...
    def change_request(self, request_id: str, target: str, seq: int, evidence: str, amount: str,
                       audit: STAFF_AUDIT) -> None: ...
    def change_lead(self, client_request_id: str, target: str, audit: STAFF_AUDIT) -> None: ...


def _details(number: int) -> Details:
    return Details("2026-12-02", "half_day_am", "虚构展馆 A 门", f"演示访客 {number:02}",
                   f"+100000000{number:02}", "演示商务陪同")


def _submitted(request_id: str, client_request_id: str, details: Details, now: datetime) -> ServiceRequest:
    history = (
        History(1, None, "user_confirmed", now, "user", "consent", f"ev_{request_id}_1", "合成演练确认"),
        History(2, "user_confirmed", "submitted", now, "system", "receipt", f"ev_{request_id}_2", "演示收件"),
    )
    return ServiceRequest(request_id, client_request_id, SERVICE_TYPE, "submitted", details, history)


def _advance(item: ServiceRequest, target: str, evidence: str, amount: str, now: datetime) -> ServiceRequest:
    if target not in item.actions:
        raise OperationConflict
    if not evidence.strip() or len(evidence) > 300:
        raise EvidenceRequired
    if target == "quoted":
        if not amount.isascii() or not amount.isdecimal() or len(amount) > 9 or int(amount) <= 0:
            raise EvidenceRequired
        quote = Quote(int(amount))
    else:
        if amount:
            raise EvidenceRequired
        quote = item.quote
    seq = len(item.history) + 1
    event = History(seq, item.state, target, now, "staff", EVIDENCE_KINDS[target], f"ev_{item.request_id}_{seq}", evidence)
    service = item.human_service
    if target == "arranged":
        service = HumanService(escort_display_name="演示陪同",
                               arrival=Arrival(f"{item.details.service_date}T09:00", item.details.venue))
    return replace(item, state=target, history=(*item.history, event), quote=quote, human_service=service)


class DemoOperations:
    def __init__(self) -> None:
        self._lock = RLock()
        now = datetime(2026, 11, 26, 5, tzinfo=UTC)
        paths = (
            (), ("accepted",), ("accepted", "quoted"), ("accepted", "quoted", "arranged"),
            ("accepted", "quoted", "arranged", "in_progress"),
            ("accepted", "quoted", "arranged", "in_progress", "completed"),
            ("user_cancelled",), ("unavailable",), ("accepted", "quoted", "arranged", "outcome_unknown"),
        )
        self._requests = {}
        for number, path in enumerate(paths, 1):
            item = _submitted(f"sr_demo_{number:02}", f"demo_request_{number:02}", _details(number), now)
            for target in path:
                item = _advance(item, target, "合成凭据 · 员工演练", "48000" if target == "quoted" else "", now)
            self._requests[item.request_id] = item
        self._leads = {key: Lead(key, state, _details(10 + number))
                       for number, state in enumerate(("pending", "pending", "contacted"), 1)
                       for key in (f"demo_lead_{number:02}",)}

    def requests(self) -> tuple[ServiceRequest, ...]:
        with self._lock:
            return tuple(self._requests.values())

    def request(self, request_id: str) -> ServiceRequest | None:
        with self._lock:
            return self._requests.get(request_id)

    def leads(self) -> tuple[Lead, ...]:
        with self._lock:
            return tuple(self._leads.values())

    def change_request(self, request_id: str, target: str, seq: int, evidence: str, amount: str,
                       audit: STAFF_AUDIT) -> None:
        with self._lock:
            item = self._requests.get(request_id)
            if item is None:
                raise OperationMissing
            if seq != len(item.history):
                raise OperationConflict
            updated = _advance(item, target, evidence, amount, datetime.now(UTC))
            audit(OperationsAuditDetail(f"request:{target}", request_id))
            self._requests[request_id] = updated

    def change_lead(self, client_request_id: str, target: str, audit: STAFF_AUDIT) -> None:
        with self._lock:
            lead = self._leads.get(client_request_id)
            if lead is None:
                raise OperationMissing
            if target not in lead.actions:
                raise OperationConflict
            audit(OperationsAuditDetail(f"lead:{target}", client_request_id))
            self._leads[client_request_id] = replace(lead, state=target)
            if target == "converted":
                request_id = f"sr_{client_request_id}"
                self._requests[request_id] = _submitted(request_id, client_request_id, lead.details, datetime.now(UTC))
