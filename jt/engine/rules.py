"""Deterministic recognition on synthetic text and CJ's precomputed event state."""

import re
from dataclasses import dataclass
from unicodedata import normalize

from jt.common import CountEventState, EventRef, OrderEventState, Severity, SignalType, TripTimeEventState


RULES_VERSION = "jt-rules.v1"
INTENT_REPEAT_THRESHOLD = 2
TOOL_ERROR_THRESHOLD = 3


@dataclass(frozen=True)
class RuleHit:
    rule_id: str
    signal_type: SignalType
    severity: Severity


_MEDICAL = re.compile(
    r"呼吸困难|呼吸困難|不能呼吸|喘不过气|喘不過氣|昏迷|昏倒|晕倒|暈倒|"
    r"受伤|受傷|大出血|剧烈胸痛|劇烈胸痛|一氧化碳|中毒|溺水|"
    r"\b(?:can(?:not|['’]t) breathe|trouble breathing|difficulty breathing|"
    r"shortness of breath|choking|unconscious|passed out|fainted|severe chest pain|"
    r"seriously injured|(?:i am|i['’]m|we are|we['’]re|is) injured|"
    r"bleeding (?:badly|heavily)|carbon monoxide|drowning)\b",
    re.IGNORECASE,
)
_AMBULANCE_REQUEST = re.compile(
    r"(?:叫|喊|找|派|要|需要)\s*救[护護][车車]|救[护護][车車](?:快来|快來)|"
    r"\b(?:(?:need|call|send|get|request)\s+(?:(?:an?|the|me|us)\s+)*ambulance|"
    r"ambulance (?:please|now|urgently|has(?:n['’]t| not) arrived))\b|"
    r"\A\s*(?:救[护護][车車]|ambulance)[\s.!?。！？]*\Z",
    re.IGNORECASE,
)
_SAFETY = re.compile(
    r"遇险|遇險|有危险|有危險|身处危险|身處危險|救命|求救|被困|走失|走散|失联|失聯|"
    r"迷路了|迷路在|(?:我|我们|我們|孩子|小孩|同伴)迷路|有人跟踪|有人跟蹤|被跟踪|被跟蹤|起火|着火|著火|火灾|火災|"
    r"\b(?:in (?:immediate )?danger|being (?:followed|attacked)|someone is following|"
    r"(?:i am|i['’]m|we are|we['’]re|they are|they['’]re) (?:lost|trapped)|"
    r"trapped (?:in|inside)|(?:child|kid|daughter|son) (?:is missing|went missing|is lost)|"
    r"(?:help|save) me now|on fire|fire broke out|there(?: is|['’]s) a fire)\b",
    re.IGNORECASE,
)
_DIAL_NUMBER = re.compile(
    r"(?:(?<![A-Za-z])(?:call|dial|ring|phone|contact)\s+(?:(?:the|number|emergency)\s+)*"
    r"|请?拨(?:打)?\s*|請?撥(?:打)?\s*|报警(?:电话)?\s*|報警(?:電話)?\s*|紧急电话\s*|緊急電話\s*)"
    r"[:#( ]*(110|119|120)(?![A-Za-z0-9]|[.-][0-9])",
    re.IGNORECASE,
)
_STANDALONE_NUMBER = re.compile(r"\s*(110|119|120)[\s.!?。！？]*\Z")
_EMERGENCY_HITS = {
    "110": RuleHit("p0_emergency_110", "safety", "P0"),
    "119": RuleHit("p0_emergency_119", "safety", "P0"),
    "120": RuleHit("p0_emergency_120", "illness", "P0"),
}


def match_rules(
    raw_fragments: tuple[str, ...],
    redacted_fragments: tuple[str, ...],
    events: tuple[EventRef, ...],
) -> tuple[RuleHit, ...]:
    """Use original words for safety cues and masked text for dialing-number cues."""
    hits: dict[str, RuleHit] = {}

    def record(hit: RuleHit) -> None:
        hits[hit.rule_id] = hit

    for fragment in raw_fragments:
        text = normalize("NFKC", fragment)
        if _MEDICAL.search(text) or _AMBULANCE_REQUEST.search(text):
            record(RuleHit("p0_medical", "illness", "P0"))
        if _SAFETY.search(text):
            record(RuleHit("p0_safety", "safety", "P0"))

    for fragment in redacted_fragments:
        text = normalize("NFKC", fragment)
        for number in _DIAL_NUMBER.findall(text):
            record(_EMERGENCY_HITS[number])
        standalone = _STANDALONE_NUMBER.fullmatch(text)
        if standalone:
            record(_EMERGENCY_HITS[standalone[1]])

    for event in events:
        match event:
            case EventRef(event_type="intent_unresolved", event_state=CountEventState(count=count)) if count >= INTENT_REPEAT_THRESHOLD:
                record(RuleHit("intent_repeated", "ai_failure_loop", "P4"))
            case EventRef(event_type="tool_failed", event_state=CountEventState(count=count)) if count >= TOOL_ERROR_THRESHOLD:
                record(RuleHit("tool_errors_repeated", "ai_failure_loop", "P4"))
            case EventRef(event_type="trip_time_triggered", event_state=TripTimeEventState(trigger="check_in_due")):
                record(RuleHit("check_in_due", "itinerary_disruption", "P2"))
            case EventRef(event_type="order_status_changed", event_state=OrderEventState(status="changed")):
                record(RuleHit("order_changed", "itinerary_disruption", "P2"))
            case EventRef(event_type="order_status_changed", event_state=OrderEventState(status="failed")):
                record(RuleHit("order_failed", "payment_issue", "P1"))

    return tuple(sorted(hits.values(), key=lambda hit: (hit.severity, hit.signal_type, hit.rule_id)))
