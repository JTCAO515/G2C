"""Turn one local synthetic conversation snapshot into a workbench signal."""

from dataclasses import dataclass
from hashlib import sha256
from json import dumps
from typing import cast

from jt.common import (
    DecisionContext, DecisionModel, EventRef, ModelObservation, Severity,
    Signal, SignalSink, SignalType, SyntheticEvent,
)

from .redaction import REDACTION_VERSION, ConversationRedactor
from .rules import RULES_VERSION, match_rules


@dataclass(frozen=True)
class Recognition:
    signal: Signal | None
    observation: ModelObservation | None = None


class RecognitionEngine:
    def __init__(self, sink: SignalSink, *, model: tuple[str, DecisionModel] | None = None) -> None:
        self._sink = sink
        self._model = model

    async def recognize(self, events: tuple[SyntheticEvent, ...]) -> Recognition:
        """Recognize and publish from one ordered snapshot of a synthetic conversation."""
        if not events:
            raise ValueError("recognition needs at least one event")
        refs = tuple(event.ref for event in events)
        if len({ref.conversation_id for ref in refs}) != 1:
            raise ValueError("recognition accepts one conversation at a time")

        raw = tuple(event.synthetic_fragment for event in events if event.synthetic_fragment is not None)
        redactor = ConversationRedactor()
        redacted = tuple(redactor.redact(fragment) for fragment in raw)
        hits = match_rules(raw, redacted, refs)
        if hits:
            primary = hits[0]
            signal = _make_signal(
                refs, redacted, primary.signal_type, primary.severity, tuple(hit.rule_id for hit in hits)
            )
            await self._sink.publish(signal)
            return Recognition(signal)

        if self._model is None:
            return Recognition(None)

        version, model = self._model
        output = await model.decide(DecisionContext(redacted_fragments=redacted, events=refs))
        observation = ModelObservation(model_version=version, output=output)
        severity = output.severity
        if severity is None or severity == "P0":
            # Only deterministic P0 rules can cause the workbench's urgent alert.
            return Recognition(None, observation)

        # The shared DecisionOutput contract pairs a severity with a non-null type.
        signal = _make_signal(
            refs, redacted, cast(SignalType, output.signal_type), severity, (), (observation,)
        )
        await self._sink.publish(signal)
        return Recognition(signal, observation)


def _make_signal(
    refs: tuple[EventRef, ...],
    redacted: tuple[str, ...],
    signal_type: SignalType,
    severity: Severity,
    rule_hits: tuple[str, ...],
    observations: tuple[ModelObservation, ...] = (),
) -> Signal:
    key = dumps([signal_type, [ref.event_id for ref in refs]], separators=(",", ":"))
    return Signal(
        schema_version="jt-signal.v1",
        signal_id=f"sig-jt-{sha256(key.encode()).hexdigest()}",
        source_events=refs,
        # Synthetic event time is the local observation clock, so replays have the same content.
        detected_at=max(ref.occurred_at for ref in refs),
        signal_type=signal_type,
        severity=severity,
        redacted_fragments=redacted,
        rule_hits=rule_hits,
        rules_version=RULES_VERSION,
        redaction_version=REDACTION_VERSION,
        model_outputs=observations,
    )
