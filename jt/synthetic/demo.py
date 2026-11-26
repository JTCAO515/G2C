"""Opt-in, before-and-after case fixtures for the staff workbench demo."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import count
from random import Random
from types import MappingProxyType
from typing import Literal
from uuid import UUID, uuid4

from jt.common import (
    CaseExecution, CountEventState, DecisionOutput, EmptyEventState, EventRef,
    EventState, EventType, ModelObservation, OrderEventState, Severity, Signal,
    SignalType, SyntheticEvent,
)
from jt.playbook import CaseActionResult, CaseAuditEvent, CaseWorkflow
from jt.playbook.catalog import PLAYBOOKS_BY_SIGNAL, Playbook, Step

DEMO_SEED = 1887
_VERSION = "demo-1887.1"
_START = datetime(2026, 11, 26, 2, tzinfo=UTC)
_ACTOR = "demo-staff-01"
Target = Literal["draft", "confirmed", "rejected", "closed", "open"]

DEMO_PLAYBOOKS = MappingProxyType({
    **PLAYBOOKS_BY_SIGNAL,
    "change_request": Playbook("demo_itinerary_change", "1", (
        Step("prepare_change_options", "ai_auto"),
        Step("draft_guangzhou_adjustment", "ai_draft_human_confirm", ("change_itinerary",)),
    )),
})

_DRAFTS = {
    "draft_assistance_summary": "演示草稿：旅客已在<LOCATION_1>与工作人员会合，拟记录已确认安全，并继续核实同行者是否找到。",
    "draft_document_guidance": "演示草稿：拟整理补办所需材料，先核实失物记录，再由旅客通过官方渠道确认办理时段。",
    "draft_itinerary_change": "演示草稿：拟把接站安排顺延到航班实际抵达之后；住宿与接送仍待核实，未产生订票或扣款。",
    "draft_guangzhou_adjustment": "演示草稿：拟把广州商务陪同调整到下午，先核实人员与双方时间，再由旅客确认变更。",
    "draft_recovery_summary": "演示草稿：已整理三次查询失败记录，拟请人工核实能否安排中英陪同，再向旅客回报。",
}


@dataclass(frozen=True)
class DemoDataset:
    events: tuple[SyntheticEvent, ...]
    signals: tuple[Signal, ...]
    cases: tuple[CaseExecution, ...]
    history: tuple[CaseAuditEvent, ...]
    workflow: CaseWorkflow = field(compare=False, repr=False)


@dataclass(frozen=True)
class Scenario:
    name: str
    signal_type: SignalType
    severity: Severity
    fragments: tuple[str, str]
    target: Target
    rule: str | None = None
    related: tuple[tuple[EventType, EventState], ...] = ()


_SCENARIOS = (
    Scenario("safety", "safety", "P0", (
        "旅客：我叫<NAME_1>，在<LOCATION_1>和同行朋友走散了，可以帮我联系<PHONE_1>吗？",
        "CJ: I can help you find a staffed meeting point. Are you somewhere safe now?",
    ), "draft", "p0_safety"),
    Scenario("passport", "document_loss", "P1", (
        "Traveler: I cannot find passport <PASSPORT_1>. I last used it at <LOCATION_1>, and my train is tomorrow.",
        "CJ：先核实遗失地点和明天的乘车安排，再整理报失、补办和临时证件的步骤。",
    ), "rejected"),
    Scenario("flight", "itinerary_disruption", "P2", (
        "旅客：航司通知航班<FLIGHT_1>晚了三个小时，我在<LOCATION_1>的接站还能保留吗？",
        "CJ: I can check the impact on your pickup and hotel. Please review the revised plan before anything changes.",
    ), "confirmed", "flight_schedule_changed", (("order_status_changed", OrderEventState(status="changed")),)),
    Scenario("guangzhou", "change_request", "P3", (
        "Traveler: Can we move my Guangzhou bilingual business escort to the afternoon? The meeting at <LOCATION_1> changed.",
        "CJ：我先整理新的时间需求；需要你确认共享<NAME_1>和<PHONE_1>，并等陪同人员确认后才算已安排。",
    ), "open"),
    Scenario("retry", "ai_failure_loop", "P4", (
        "旅客：我问了两次广州展会的中英陪同，系统还是只给我路线，没回答能不能安排。",
        "CJ: The last checks timed out. I have kept your request for a human review; availability is still unconfirmed.",
    ), "closed", "repeated_failure", (
        ("intent_unresolved", CountEventState(count=2)),
        ("tool_failed", CountEventState(count=3)),
    )),
)


def _signal(scenario: Scenario, key: str, when: datetime) -> tuple[Signal, tuple[SyntheticEvent, ...]]:
    events = []
    for index, fragment in enumerate(scenario.fragments, start=1):
        ref = EventRef(
            schema_version="jt-event-ref.v1", event_id=f"{key}-event-{index}",
            conversation_id=f"{key}-conversation", message_id=f"{key}-message-{index}",
            sequence=index, occurred_at=when + timedelta(seconds=index),
            event_type="message_accepted", event_state=EmptyEventState(),
        )
        events.append(SyntheticEvent(
            schema_version="jt-synthetic-event.v1", ref=ref, synthetic_fragment=fragment,
        ))
    for index, (event_type, state) in enumerate(scenario.related, start=len(events) + 1):
        ref = EventRef(
            schema_version="jt-event-ref.v1", event_id=f"{key}-event-{index}",
            conversation_id=f"{key}-conversation", occurred_at=when + timedelta(seconds=index),
            event_type=event_type, event_state=state,
        )
        events.append(SyntheticEvent(schema_version="jt-synthetic-event.v1", ref=ref))
    return Signal(
        schema_version="jt-signal.v1", signal_id=f"{key}-signal",
        source_events=tuple(event.ref for event in events),
        detected_at=events[-1].ref.occurred_at + timedelta(seconds=1),
        signal_type=scenario.signal_type, severity=scenario.severity,
        redacted_fragments=scenario.fragments, rules_version=_VERSION, redaction_version=_VERSION,
        rule_hits=(scenario.rule,) if scenario.rule else (),
        model_outputs=() if scenario.rule else (ModelObservation(
            model_version=_VERSION, output=DecisionOutput(
                signal_type=scenario.signal_type, severity=scenario.severity, confidence=0.91,
            ),
        ),),
    ), tuple(events)


def _applied(result: CaseActionResult, history: list[CaseAuditEvent]) -> CaseExecution:
    if result.execution is None or result.audit.outcome != "applied":
        raise RuntimeError(f"invalid demo transition: {result.audit.reason}")
    history.append(result.audit)
    return result.execution


def _stage(
    workflow: CaseWorkflow, current: CaseExecution, target: Target, history: list[CaseAuditEvent],
) -> CaseExecution:
    case_id = current.case.case_id
    while target != "open" and (step := current.active_step) is not None:
        current = _applied(workflow.advance(
            case_id, expected_revision=current.revision, actor_id=_ACTOR,
        ), history)
        if step.mode != "ai_draft_human_confirm":
            continue
        if target == "draft":
            return current
        if target == "rejected":
            return _applied(workflow.reject(
                case_id, expected_revision=current.revision, actor_id=_ACTOR,
            ), history)
        if step.requires_customer_confirmation:
            current = _applied(workflow.record_synthetic_customer_consent(
                case_id, expected_revision=current.revision, step_id=step.step_id,
            ), history)
        current = _applied(workflow.confirm(
            case_id, expected_revision=current.revision, actor_id=_ACTOR,
        ), history)
        if target == "confirmed":
            return current
    return current


def generate_demo_dataset(seed: int = DEMO_SEED) -> DemoDataset:
    """Build a fresh opt-in queue, live case workspace and seeded audit history."""
    random = Random(seed)
    ticks = count()
    seeding = True

    def demo_clock() -> datetime:
        if seeding:
            return _START + timedelta(minutes=30, seconds=next(ticks))
        return datetime.now(UTC)

    def demo_case_id() -> UUID:
        if seeding:
            return UUID(int=random.getrandbits(128), version=4)
        return uuid4()

    workflow = CaseWorkflow(
        playbooks=DEMO_PLAYBOOKS, clock=demo_clock, case_id_factory=demo_case_id, drafts=_DRAFTS,
    )
    events, signals, cases, history = [], [], [], []
    for index, scenario in enumerate(_SCENARIOS):
        signal, source = _signal(
            scenario, f"jt-{_VERSION}-{seed}-{scenario.name}", _START + timedelta(minutes=index),
        )
        events.extend(source)
        signals.append(signal)
        opened = workflow.ingest(signal)
        if opened.audit is not None:
            history.append(opened.audit)
        cases.append(_stage(workflow, opened.execution, scenario.target, history))
    seeding = False
    return DemoDataset(tuple(events), tuple(signals), tuple(cases), tuple(history), workflow)
