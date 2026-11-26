from asyncio import run
from datetime import UTC, datetime, timedelta, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from jt.common import (
    Case,
    DecisionContext,
    DecisionModel,
    DecisionOutput,
    EventRef,
    PlaybookStep,
    Signal,
    SignalSink,
    SyntheticEvent,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def event_ref(**changes):
    fields = {
        "event_id": "evt-syn-001",
        "conversation_id": "conv-syn-001",
        "message_id": "msg-syn-001",
        "sequence": 1,
        "event_type": "message_accepted",
        "event_state": {},
        "occurred_at": NOW,
    }
    return EventRef.model_validate(fields | changes)


def signal(**changes):
    fields = {
        "signal_id": "sig-syn-001",
        "source_events": (event_ref(),),
        "signal_type": "illness",
        "severity": "P0",
        "detected_at": NOW,
        "redacted_fragments": ("请叫救护车",),
        "rule_hits": ("p0_medical",),
        "rules_version": "synthetic.1",
        "redaction_version": "synthetic.1",
    }
    return Signal.model_validate(fields | changes)


def case(**changes):
    fields = {
        "case_id": "7bd65b4c-79de-4cfb-a4ad-46d1b04f6210",
        "signal_ids": ("sig-syn-001",),
        "severity": "P0",
        "created_at": NOW,
        "status": "open",
        "playbook_id": "p0_assistance",
        "playbook_version": "1",
        "steps": (
            PlaybookStep(step_id="show_guidance", mode="ai_auto", requires_customer_confirmation=False),
            PlaybookStep(
                step_id="draft_resolution",
                mode="ai_draft_human_confirm",
                requires_customer_confirmation=True,
            ),
            PlaybookStep(step_id="verify", mode="human_only", requires_customer_confirmation=False),
        ),
    }
    return Case.model_validate(fields | changes)


def test_signal_and_case_round_trip_with_versioned_references():
    offset = timezone(timedelta(hours=8))
    accepted = event_ref(occurred_at=NOW.astimezone(offset), travel_reference_version=3)
    received = signal(source_events=(accepted,))
    opened = case(signal_ids=(received.signal_id,))

    assert Signal.model_validate_json(received.model_dump_json()) == received
    assert Case.model_validate_json(opened.model_dump_json()) == opened
    assert received.source_events[0].occurred_at.tzinfo is UTC
    assert received.source_events[0].travel_reference_version == 3
    assert opened.case_id.version == 4
    assert [step.mode for step in opened.steps] == ["ai_auto", "ai_draft_human_confirm", "human_only"]
    assert opened.steps[1].requires_customer_confirmation


@pytest.mark.parametrize("changes", [
    {"sequence": None},
    {"message_id": None, "sequence": None},
    {"message_id": "msg-syn-001", "sequence": True},
    {"travel_reference_version": 0},
    {"event_type": "trip_time_triggered", "event_state": {"count": 2}},
    {"event_type": "tool_failed", "event_state": {"count": -1}},
    {"event_type": "unknown"},
    {"occurred_at": datetime(2026, 1, 1)},
    {"raw_message": "synthetic original text"},
])
def test_event_ref_rejects_invalid_state_and_non_reference_fields(changes):
    with pytest.raises(ValidationError):
        event_ref(**changes)


def test_original_fragment_is_only_allowed_on_the_synthetic_message_envelope():
    message = SyntheticEvent(ref=event_ref(), synthetic_fragment="Synthetic text")
    assert SyntheticEvent.model_validate_json(message.model_dump_json()) == message
    assert "synthetic_fragment" not in message.ref.model_dump()

    failure = event_ref(
        message_id=None,
        sequence=None,
        event_type="tool_failed",
        event_state={"count": 2},
    )
    with pytest.raises(ValidationError):
        SyntheticEvent(ref=failure, synthetic_fragment="Synthetic text")


@pytest.mark.parametrize("changes", [
    {"schema_version": "jt-signal.v2"},
    {"source_events": ()},
    {"source_events": (event_ref(), event_ref())},
    {"severity": "P4"},
    {"signal_id": ""},
    {"rules_version": ""},
    {"user_uuid": "synthetic-user"},
])
def test_signal_rejects_invalid_or_unversioned_boundary_data(changes):
    with pytest.raises(ValidationError):
        signal(**changes)


@pytest.mark.parametrize("changes", [
    {"signal_ids": ()},
    {"signal_ids": ("sig-syn-001", "sig-syn-001")},
    {"steps": ()},
    {"steps": (case().steps[0], case().steps[0])},
    {"case_id": UUID("00000000-0000-1000-8000-000000000000")},
    {"user_uuid": "synthetic-user"},
])
def test_case_rejects_invalid_references_and_user_identity(changes):
    with pytest.raises(ValidationError):
        case(**changes)


@pytest.mark.parametrize("changes", [
    {"confidence": -0.1},
    {"confidence": 1.1},
    {"confidence": float("nan")},
    {"confidence": float("inf")},
    {"confidence": True},
    {"signal_type": None},
    {"severity": None},
    {"severity": "P4"},
    {"needs_human": True},
])
def test_decision_rejects_invalid_or_authoritative_output(changes):
    fields = {"signal_type": "illness", "severity": "P0", "confidence": 0.9}
    with pytest.raises(ValidationError):
        DecisionOutput.model_validate(fields | changes)


def test_decision_no_signal_and_minimum_confidence():
    result = DecisionOutput(signal_type=None, severity=None, confidence=0)
    assert result.model_dump() == {"signal_type": None, "severity": None, "confidence": 0.0}


def test_engine_protocols_transfer_only_the_typed_decision_and_signal():
    class LocalDecisionModel:
        async def decide(self, context: DecisionContext) -> DecisionOutput:
            assert context.redacted_fragments == ("<NAME_1> needs an ambulance.",)
            return DecisionOutput(signal_type="illness", severity="P0", confidence=1)

    class QueueProbe:
        def __init__(self):
            self.received = []

        async def publish(self, signal: Signal) -> None:
            self.received.append(signal)

    model: DecisionModel = LocalDecisionModel()
    context = DecisionContext(
        redacted_fragments=("<NAME_1> needs an ambulance.",), events=(event_ref(),)
    )
    assert run(model.decide(context)).severity == "P0"

    queue = QueueProbe()
    sink: SignalSink = queue
    value = signal()
    assert run(sink.publish(value)) is None
    assert queue.received == [value]
