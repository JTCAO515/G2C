"""Fixed-seed bilingual evaluation cases, labeled independently of the engine."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from random import Random

from jt.common import EmptyEventState, EventRef, Severity, SignalType, SyntheticEvent
from jt.synthetic import generate_dataset


EVAL_SEED = 1710
_SHARED_SEED = 1706
_START = datetime(2026, 2, 1, tzinfo=UTC)


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    events: tuple[SyntheticEvent, ...]
    expected_type: SignalType | None
    expected_severity: Severity | None


# Include varied emergency phrasing and ordinary uses of similar words or numbers.
_EXAMPLES: tuple[tuple[str, SignalType | None, Severity | None, str], ...] = (
    ("zh-lost", "safety", "P0", "我叫顾演宁和自己的家人走散了。"),
    ("zh-fire", "safety", "P0", "楼道起火了，请派人！"),
    ("zh-threat", "safety", "P0", "有人跟蹤我，走不掉。"),
    ("zh-dial", "safety", "P0", "请拨１１９！"),
    ("en-missing", "safety", "P0", "My daughter went missing in the station."),
    ("en-trapped", "safety", "P0", "We're trapped inside the lift."),
    ("en-police", "safety", "P0", "Please dial 110 now."),
    ("en-police-punctuated", "safety", "P0", "Dial: 110!"),
    ("en-standalone", "safety", "P0", "119!"),
    ("zh-air", "illness", "P0", "在房号：三零五，有人不能呼吸。"),
    ("zh-carbon", "illness", "P0", "房间：一氧化碳报警器响了。"),
    ("zh-medical-number", "illness", "P0", "請撥１２０。"),
    ("zh-injury", "illness", "P0", "我的同伴受傷了，快帮帮她。"),
    ("zh-ambulance-alone", "illness", "P0", "救護車！"),
    ("en-faint", "illness", "P0", "My friend passed out just now."),
    ("en-breath", "illness", "P0", "He's having trouble breathing."),
    ("en-medical-number", "illness", "P0", "Dial (120), please."),
    ("en-medical-short", "illness", "P0", "120, please!"),
    ("en-poisoning", "illness", "P0", "We think we have carbon monoxide poisoning."),
    ("en-injury", "illness", "P0", "I am injured and cannot get up."),
    ("zh-document", "document_loss", "P1", "我的护照被偷了。"),
    ("en-document", "document_loss", "P1", "I can't find my passport anywhere."),
    ("zh-card", "payment_issue", "P1", "我的信用卡被冻结了。"),
    ("en-card", "payment_issue", "P1", "My card was declined twice."),
    ("zh-service-suspended", "itinerary_disruption", "P2", "我订的车次停运了。"),
    ("en-flight", "itinerary_disruption", "P2", "My flight was canceled while I was at the airport."),
    ("zh-hotel-change", "change_request", "P3", "麻烦把酒店换一下。"),
    ("en-booking-change", "change_request", "P3", "Can you reschedule the booking to Friday?"),
    ("zh-loop", "ai_failure_loop", "P4", "同一个问题还是没解决。"),
    ("en-loop", "ai_failure_loop", "P4", "The tool is still failing after the last attempt."),
    ("zh-room", None, None, "我在旅馆登记，房号：一二零。"),
    ("zh-bus", None, None, "请问 110 路公交几点开始运营？"),
    ("zh-number-prefix", None, None, "客服号码请拨打 1200。"),
    ("zh-hotel-timing", None, None, "酒店几点开始办理入住？"),
    ("zh-ambulance-info", None, None, "救护车的费用可以报销吗？"),
    ("en-exit", None, None, "Where is the fire exit on this floor plan?"),
    ("en-flight-code", None, None, "The flight number is CA119 and the boarding time is 11:00."),
    ("en-room", None, None, "The room number is 120 and breakfast is on floor 2."),
    ("en-reservation-code", None, None, "The reservation code is 119, please record it."),
    ("en-info", None, None, "What is the emergency number in China?"),
    ("en-ambulance-info", None, None, "What does insurance cover for an ambulance?"),
)


def generate_eval_cases(seed: int = EVAL_SEED) -> tuple[EvalCase, ...]:
    shared = generate_dataset(seed=_SHARED_SEED)
    event_index = {event.ref.event_id: event for event in shared.events}
    cases = [
        EvalCase(
            case_id=signal.signal_id,
            events=tuple(event_index[ref.event_id] for ref in signal.source_events),
            expected_type=signal.signal_type,
            expected_severity=signal.severity,
        )
        for signal in shared.signals
    ]
    for offset, (case_id, signal_type, severity, text) in enumerate(_EXAMPLES):
        ref = EventRef(
            schema_version="jt-event-ref.v1",
            event_id=f"evt-eval-{case_id}",
            conversation_id=f"conv-eval-{case_id}",
            message_id=f"msg-eval-{case_id}",
            sequence=1,
            occurred_at=_START + timedelta(minutes=offset),
            event_type="message_accepted",
            event_state=EmptyEventState(),
        )
        event = SyntheticEvent(schema_version="jt-synthetic-event.v1", ref=ref, synthetic_fragment=text)
        cases.append(EvalCase(case_id, (event,), signal_type, severity))

    Random(seed).shuffle(cases)
    return tuple(cases)
