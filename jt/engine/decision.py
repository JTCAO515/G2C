"""Local mock of the shared DecisionModel interface."""

import re
from unicodedata import normalize

from jt.common import DecisionContext, DecisionOutput, Severity, SignalType


MOCK_MODEL_VERSION = "jt-mock.v1"

# The adapter contract also leaves room for future Qwen and TypeSafe Jev implementations.
_MOCK_CUES: tuple[tuple[SignalType, Severity, str, str], ...] = (
    ("document_loss", "P1", r"护照|護照|证件|證件|\bpassport\b",
     r"丢|遺失|遗失|不见|不見|被偷|\b(?:lost|missing|stolen|can['’]t find)\b"),
    ("payment_issue", "P1", r"支付|付款|扣款|信用卡|\b(?:payment|card|charge)\b",
     r"失败|失敗|异常|異常|冻结|凍結|重复|重複|\b(?:failed|declined|frozen|duplicate|twice)\b"),
    ("itinerary_disruption", "P2", r"航班|酒店|车次|車次|\b(?:flight|hotel|train|booking)\b",
     r"取消|延误|延誤|停运|停運|不认单|不認單|\b(?:delayed|cancelled|canceled|refused|changed)\b"),
    ("change_request", "P3", r"行程|酒店|日期|预订|預訂|\b(?:itinerary|hotel|dates?|booking|reservation)\b",
     r"改到|改期|更改|换|換|调整|調整|\b(?:move|reschedule|change|switch)\b"),
    ("ai_failure_loop", "P4", r"同一个|同一個|工具|\b(?:same request|tool)\b",
     r"没解决|沒解決|又失败|又失敗|\b(?:unresolved|failed again|still failing)\b"),
    ("complaint", "P4", r"服务|服務|体验|體驗|\b(?:service|experience|support)\b",
     r"不满意|不滿意|太差|投诉|投訴|\b(?:unhappy|disappointed|terrible|complaint)\b"),
)
_PATTERNS = tuple(
    (signal_type, severity, re.compile(subject, re.IGNORECASE), re.compile(predicate, re.IGNORECASE))
    for signal_type, severity, subject, predicate in _MOCK_CUES
)


class MockDecisionModel:
    """Return a repeatable, test-only suggestion from redacted text."""

    async def decide(self, context: DecisionContext) -> DecisionOutput:
        fragments = tuple(normalize("NFKC", fragment) for fragment in context.redacted_fragments)
        for signal_type, severity, subject, predicate in _PATTERNS:
            if any(subject.search(fragment) and predicate.search(fragment) for fragment in fragments):
                return DecisionOutput(signal_type=signal_type, severity=severity, confidence=0.8)

        return DecisionOutput(signal_type=None, severity=None, confidence=0.0)
