import asyncio
from datetime import UTC, datetime

import pytest

from jt.common import (
    CountEventState, DecisionContext, DecisionOutput, EmptyEventState, EventRef, EventState,
    EventType, OrderEventState, Signal, SyntheticEvent, TripTimeEventState,
)
from jt.engine.decision import MOCK_MODEL_VERSION, MockDecisionModel
from jt.engine.recognition import RecognitionEngine
from jt.engine.redaction import REDACTION_VERSION
from jt.engine.rules import RULES_VERSION


_TIMESTAMP = datetime(2026, 2, 1, 8, tzinfo=UTC)


class RecordingSink:
    def __init__(self) -> None:
        self.signals: list[Signal] = []

    async def publish(self, signal: Signal) -> None:
        self.signals.append(signal)


def make_event(
    event_id: str, event_type: EventType, state: EventState, *,
    text: str | None = None, sequence: int = 1, conversation_id: str = "conv-syn-test",
) -> SyntheticEvent:
    is_message = event_type == "message_accepted"
    return SyntheticEvent(
        schema_version="jt-synthetic-event.v1",
        ref=EventRef(
            schema_version="jt-event-ref.v1",
            event_id=event_id,
            conversation_id=conversation_id,
            message_id=f"msg-{event_id}" if is_message else None,
            sequence=sequence if is_message else None,
            occurred_at=_TIMESTAMP,
            event_type=event_type,
            event_state=state,
        ),
        synthetic_fragment=text,
    )


@pytest.mark.parametrize(
    ("text", "expected_type", "expected_hit"),
    [
        ("紧急电话：１１０！", "safety", "p0_emergency_110"),
        ("Please call 119 now.", "safety", "p0_emergency_119"),
        ("請撥１２０。", "illness", "p0_emergency_120"),
        ("我叫顾演宁和朋友在机场走散了。", "safety", "p0_safety"),
        ("Mira is injured and cannot stand up.", "illness", "p0_medical"),
    ],
)
def test_p0_rules_publish_without_consulting_model(text, expected_type, expected_hit):
    class ModelMustNotRun:
        async def decide(self, context):
            raise AssertionError("P0 must publish independently of the model")

    sink = RecordingSink()
    engine = RecognitionEngine(sink, model=("mock-failure.v1", ModelMustNotRun()))
    event = make_event("evt-p0", "message_accepted", EmptyEventState(), text=text)
    result = asyncio.run(engine.recognize((event,)))

    assert result.signal is sink.signals[0]
    assert result.signal.signal_type == expected_type
    assert result.signal.severity == "P0"
    assert expected_hit in result.signal.rule_hits
    assert result.signal.model_outputs == ()
    assert result.signal.rules_version == RULES_VERSION
    assert result.signal.redaction_version == REDACTION_VERSION
    assert result.signal.source_events == (event.ref,)
    assert "顾演宁" not in result.signal.redacted_fragments[0]


@pytest.mark.parametrize(
    ("event_type", "state", "expected_hit"),
    [
        ("intent_unresolved", CountEventState(count=1), None),
        ("intent_unresolved", CountEventState(count=2), "intent_repeated"),
        ("tool_failed", CountEventState(count=2), None),
        ("tool_failed", CountEventState(count=3), "tool_errors_repeated"),
        ("tool_failed", CountEventState(count=4), "tool_errors_repeated"),
        ("trip_time_triggered", TripTimeEventState(trigger="check_in_due"), "check_in_due"),
        ("trip_time_triggered", TripTimeEventState(trigger="fixture_other_trigger"), None),
        ("order_status_changed", OrderEventState(status="confirmed"), None),
        ("order_status_changed", OrderEventState(status="changed"), "order_changed"),
        ("order_status_changed", OrderEventState(status="failed"), "order_failed"),
    ],
)
def test_rules_consume_precomputed_state(event_type, state, expected_hit):
    sink = RecordingSink()
    engine = RecognitionEngine(sink)
    event = make_event("evt-state", event_type, state)
    result = asyncio.run(engine.recognize((event,)))

    if expected_hit is None:
        assert result.signal is None
        assert sink.signals == []
    else:
        assert result.signal is sink.signals[0]
        assert result.signal.rule_hits == (expected_hit,)


def test_repeated_below_threshold_events_are_not_counted_again():
    sink = RecordingSink()
    engine = RecognitionEngine(sink)
    events = tuple(make_event(f"evt-{i}", "tool_failed", CountEventState(count=2)) for i in range(4))
    assert asyncio.run(engine.recognize(events)).signal is None


def test_p0_wins_over_other_rules_and_replay_preserves_content():
    sink = RecordingSink()
    engine = RecognitionEngine(sink)
    events = (
        make_event("evt-card", "order_status_changed", OrderEventState(status="failed")),
        make_event("evt-help", "message_accepted", EmptyEventState(), text="I can't breathe."),
    )
    first = asyncio.run(engine.recognize(events))
    replay = asyncio.run(engine.recognize(events))

    assert first.signal.severity == "P0"
    assert first.signal.rule_hits == ("p0_medical", "order_failed")
    assert first.signal == replay.signal == sink.signals[0] == sink.signals[1]
    assert first.signal.detected_at == _TIMESTAMP


def test_model_and_sink_receive_redacted_content_and_model_evidence():
    class CaptureModel:
        async def decide(self, context: DecisionContext) -> DecisionOutput:
            assert context.redacted_fragments == (
                "My name is <NAME_1>. Email <EMAIL_1>.",
                "My name is <NAME_1>. My passport is missing.",
            )
            return await MockDecisionModel().decide(context)

    sink = RecordingSink()
    engine = RecognitionEngine(sink, model=(MOCK_MODEL_VERSION, CaptureModel()))
    events = (
        make_event("evt-first", "message_accepted", EmptyEventState(),
                   text="My name is Mira Quill. Email mira@example.invalid."),
        make_event("evt-second", "message_accepted", EmptyEventState(),
                   text="My name is Mira Quill. My passport is missing.", sequence=2),
    )
    result = asyncio.run(engine.recognize(events))

    assert result.signal is sink.signals[0]
    assert result.signal.severity == "P1"
    assert result.signal.signal_type == "document_loss"
    assert result.signal.redacted_fragments == (
        "My name is <NAME_1>. Email <EMAIL_1>.",
        "My name is <NAME_1>. My passport is missing.",
    )
    assert result.signal.model_outputs == (result.observation,)
    assert result.observation.model_version == MOCK_MODEL_VERSION


def test_p0_model_suggestion_is_observed_without_issuing_a_rule_alert():
    class ModelSuggestsP0:
        async def decide(self, context):
            return DecisionOutput(signal_type="safety", severity="P0", confidence=1.0)

    sink = RecordingSink()
    engine = RecognitionEngine(sink, model=("mock-advisory.v1", ModelSuggestsP0()))
    event = make_event("evt-neutral", "message_accepted", EmptyEventState(), text="Will the museum open?")
    result = asyncio.run(engine.recognize((event,)))

    assert result.signal is None
    assert not sink.signals
    assert result.observation.output.severity == "P0"


def test_mixed_conversations_fail_before_publishing():
    sink = RecordingSink()
    engine = RecognitionEngine(sink)
    events = (
        make_event("evt-one", "message_accepted", EmptyEventState(), text="请叫救护车。"),
        make_event("evt-two", "message_accepted", EmptyEventState(), text="I need help.",
                   conversation_id="conv-syn-other"),
    )

    with pytest.raises(ValueError, match="one conversation"):
        asyncio.run(engine.recognize(events))
    assert not sink.signals


def test_sink_failure_is_visible():
    class FailingSink:
        async def publish(self, signal):
            raise RuntimeError("synthetic sink rejected the signal")

    event = make_event("evt-failure", "message_accepted", EmptyEventState(), text="请叫救护车。")
    with pytest.raises(RuntimeError, match="synthetic sink rejected"):
        asyncio.run(RecognitionEngine(FailingSink()).recognize((event,)))
