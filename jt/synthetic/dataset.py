"""Repeatable, authored synthetic events and seed signals for JT development."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from random import Random

from jt.common import (
    CountEventState,
    DecisionOutput,
    EmptyEventState,
    EventRef,
    EventState,
    EventType,
    ModelObservation,
    OrderEventState,
    Severity,
    Signal,
    SignalType,
    SyntheticEvent,
    TripTimeEventState,
)

DEFAULT_SEED = 1706
_START = datetime(2026, 1, 1, tzinfo=UTC)
_VERSION = "synthetic.1"


@dataclass(frozen=True)
class SyntheticDataset:
    events: tuple[SyntheticEvent, ...]
    signals: tuple[Signal, ...]


@dataclass(frozen=True)
class _Scenario:
    signal_type: SignalType
    severity: Severity
    fragments: tuple[str, str]
    rule_id: str | None = None
    related_events: tuple[tuple[EventType, EventState], ...] = ()


_SCENARIOS = (
    _Scenario(
        "safety", "P0",
        ("我现在有危险，请帮我拨打 110。", "I am in danger. Please call 110."),
        "p0_safety",
    ),
    _Scenario(
        "illness", "P0",
        ("请叫救护车。", "I need an ambulance. Please call 120."),
        "p0_medical",
    ),
    _Scenario(
        "document_loss", "P1",
        ("我的演练护照丢了。", "I lost my practice passport."),
    ),
    _Scenario(
        "payment_issue", "P1",
        ("这笔演练订单支付失败。", "The test order payment failed."),
        "order_failed",
        (("order_status_changed", OrderEventState(status="failed")),),
    ),
    _Scenario(
        "itinerary_disruption", "P2",
        ("该到入住时间了，酒店说订单变了。", "It's check-in time, and the hotel says my booking changed."),
        "check_in_order_changed",
        (
            ("trip_time_triggered", TripTimeEventState(trigger="check_in_due")),
            ("order_status_changed", OrderEventState(status="changed")),
        ),
    ),
    _Scenario(
        "change_request", "P3",
        ("可以把演练行程改到明天吗？", "Can you move the practice itinerary to tomorrow?"),
    ),
    _Scenario(
        "ai_failure_loop", "P4",
        ("同一个请求还是没解决，工具又失败了。", "The same request is unresolved. The tool failed again."),
        "repeated_failure",
        (
            ("tool_failed", CountEventState(count=3)),
            ("intent_unresolved", CountEventState(count=2)),
        ),
    ),
    _Scenario(
        "complaint", "P4",
        ("我对这次演练的服务很不满意。", "I'm unhappy with this practice service."),
    ),
)


def generate_dataset(seed: int = DEFAULT_SEED) -> SyntheticDataset:
    """Generate both languages for each signal type, with IDs and order stable for a seed."""
    examples = [
        (scenario, fragment)
        for scenario in _SCENARIOS
        for fragment in scenario.fragments
    ]
    Random(seed).shuffle(examples)
    events = []
    signals = []
    for index, (scenario, fragment) in enumerate(examples, start=1):
        sample_id = f"{seed}-{index:03d}"
        occurred_at = _START + timedelta(minutes=index)
        conversation_id = f"conv-syn-{sample_id}"
        refs = [
            EventRef(
                event_id=f"evt-syn-{sample_id}-1",
                conversation_id=conversation_id,
                message_id=f"msg-syn-{sample_id}",
                sequence=1,
                occurred_at=occurred_at,
                event_type="message_accepted",
                event_state=EmptyEventState(),
            )
        ]
        events.append(SyntheticEvent(ref=refs[0], synthetic_fragment=fragment))
        for offset, (event_type, event_state) in enumerate(scenario.related_events, start=2):
            ref = EventRef(
                event_id=f"evt-syn-{sample_id}-{offset}",
                conversation_id=conversation_id,
                occurred_at=occurred_at + timedelta(seconds=offset - 1),
                event_type=event_type,
                event_state=event_state,
            )
            refs.append(ref)
            events.append(SyntheticEvent(ref=ref))
        rule_hits: tuple[str, ...] = ()
        model_outputs: tuple[ModelObservation, ...] = ()
        if scenario.rule_id is not None:
            rule_hits = (scenario.rule_id,)
        else:
            # This authored observation supplies a model row for workbench fixtures.
            model_outputs = (
                ModelObservation(
                    model_version=_VERSION,
                    output=DecisionOutput(
                        signal_type=scenario.signal_type,
                        severity=scenario.severity,
                        confidence=0.9,
                    ),
                ),
            )
        signals.append(Signal(
            signal_id=f"sig-syn-{sample_id}",
            source_events=tuple(refs),
            detected_at=refs[-1].occurred_at + timedelta(seconds=1),
            signal_type=scenario.signal_type,
            severity=scenario.severity,
            redacted_fragments=(fragment,),
            rule_hits=rule_hits,
            rules_version=_VERSION,
            redaction_version=_VERSION,
            model_outputs=model_outputs,
        ))
    return SyntheticDataset(events=tuple(events), signals=tuple(signals))
