"""Versioned JT records used by the local workbench and recognition engine."""

from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import (
    UUID4,
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

Severity = Literal["P0", "P1", "P2", "P3", "P4"]
SignalType = Literal[
    "safety",
    "illness",
    "document_loss",
    "payment_issue",
    "itinerary_disruption",
    "change_request",
    "ai_failure_loop",
    "complaint",
]
_SIGNAL_SEVERITIES: dict[SignalType, Severity] = {
    "safety": "P0",
    "illness": "P0",
    "document_loss": "P1",
    "payment_issue": "P1",
    "itinerary_disruption": "P2",
    "change_request": "P3",
    "ai_failure_loop": "P4",
    "complaint": "P4",
}

Token = Annotated[str, StringConstraints(min_length=1, pattern=r"^\S+$")]
PositiveInteger = Annotated[int, Field(strict=True, gt=0)]
Confidence = Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]
EventType = Literal[
    "message_accepted",
    "tool_failed",
    "intent_unresolved",
    "trip_time_triggered",
    "order_status_changed",
]


def _to_utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


Timestamp = Annotated[AwareDatetime, AfterValidator(_to_utc)]


def _validate_classification(signal_type: SignalType | None, severity: Severity | None) -> None:
    expected = None if signal_type is None else _SIGNAL_SEVERITIES[signal_type]
    if expected != severity:
        raise ValueError("signal type and severity must match")


class _ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EmptyEventState(_ContractModel):
    pass


class CountEventState(_ContractModel):
    count: PositiveInteger


class TripTimeEventState(_ContractModel):
    trigger: Token


class OrderEventState(_ContractModel):
    status: Literal["confirmed", "failed", "changed"]


EventState = EmptyEventState | CountEventState | TripTimeEventState | OrderEventState
_EVENT_STATES: dict[EventType, type[_ContractModel]] = {
    "message_accepted": EmptyEventState,
    "tool_failed": CountEventState,
    "intent_unresolved": CountEventState,
    "trip_time_triggered": TripTimeEventState,
    "order_status_changed": OrderEventState,
}


class EventRef(_ContractModel):
    schema_version: Literal["jt-event-ref.v1"] = "jt-event-ref.v1"
    event_id: Token
    conversation_id: Token
    message_id: Token | None = None
    sequence: PositiveInteger | None = None
    travel_reference_version: PositiveInteger | None = None
    occurred_at: Timestamp
    event_type: EventType
    event_state: EventState

    @model_validator(mode="after")
    def check_event(self) -> "EventRef":
        if (self.message_id is None) != (self.sequence is None):
            raise ValueError("message ID and sequence must be given together")
        if self.event_type == "message_accepted" and self.message_id is None:
            raise ValueError("an accepted message requires a message ID and sequence")
        if not isinstance(self.event_state, _EVENT_STATES[self.event_type]):
            raise ValueError("event state must match the event type")
        return self


class SyntheticEvent(_ContractModel):
    schema_version: Literal["jt-synthetic-event.v1"] = "jt-synthetic-event.v1"
    ref: EventRef
    synthetic_fragment: str | None = None

    @model_validator(mode="after")
    def check_fragment(self) -> "SyntheticEvent":
        if self.synthetic_fragment is not None and self.ref.event_type != "message_accepted":
            raise ValueError("only a synthetic message can contain a conversation fragment")
        return self


class DecisionContext(_ContractModel):
    redacted_fragments: tuple[str, ...]
    events: tuple[EventRef, ...]


class DecisionOutput(_ContractModel):
    signal_type: SignalType | None
    severity: Severity | None
    confidence: Confidence

    @model_validator(mode="after")
    def check_classification(self) -> "DecisionOutput":
        _validate_classification(self.signal_type, self.severity)
        return self


class ModelObservation(_ContractModel):
    model_version: Token
    output: DecisionOutput


class Signal(_ContractModel):
    schema_version: Literal["jt-signal.v1"] = "jt-signal.v1"
    signal_id: Token
    source_events: Annotated[tuple[EventRef, ...], Field(min_length=1)]
    detected_at: Timestamp
    signal_type: SignalType
    severity: Severity
    redacted_fragments: tuple[str, ...] = ()
    rule_hits: tuple[Token, ...] = ()
    rules_version: Token
    redaction_version: Token
    model_outputs: tuple[ModelObservation, ...] = ()

    @model_validator(mode="after")
    def check_signal(self) -> "Signal":
        _validate_classification(self.signal_type, self.severity)
        if len({event.event_id for event in self.source_events}) != len(self.source_events):
            raise ValueError("source event IDs must be unique")
        return self


class PlaybookStep(_ContractModel):
    step_id: Token
    mode: Literal["ai_auto", "ai_draft_human_confirm", "human_only"]
    requires_customer_confirmation: bool = Field(strict=True)


class Case(_ContractModel):
    schema_version: Literal["jt-case.v1"] = "jt-case.v1"
    case_id: UUID4
    signal_ids: Annotated[tuple[Token, ...], Field(min_length=1)]
    severity: Severity
    created_at: Timestamp
    status: Literal["open", "in_progress", "closed"]
    playbook_id: Token
    playbook_version: Token
    steps: Annotated[tuple[PlaybookStep, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def check_references(self) -> "Case":
        if len(set(self.signal_ids)) != len(self.signal_ids):
            raise ValueError("case signal IDs must be unique")
        if len({step.step_id for step in self.steps}) != len(self.steps):
            raise ValueError("case step IDs must be unique")
        return self
