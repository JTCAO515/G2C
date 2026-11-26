"""Prepare and release a paced batch into an isolated in-memory workbench."""

import asyncio
import math
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import cycle
from uuid import UUID

from jt.common import Signal, SignalSink
from jt.engine.decision import MOCK_MODEL_VERSION, MockDecisionModel
from jt.engine.recognition import RecognitionEngine
from jt.eval.dataset import generate_eval_cases
from jt.playbook import CaseWorkflow
from jt.workbench.cases import CaseWorkspace, workbench_audit
from jt.workbench.queue import MemoryQueue
from jt.workbench.store import AuditAction, AuditResult, MemoryStore


DRILL_SEED = 1713
_SAMPLES = ("zh-lost", "en-document", "en-flight", "zh-hotel-change", "en-loop")
_SCRIPTED_CONSENTS = {"draft_itinerary_change", "simulate_paid_rebooking"}


@dataclass(frozen=True)
class Arrival:
    reference: str
    offset_seconds: float
    signal: Signal


class _CollectSignals:
    def __init__(self) -> None:
        self.signals: list[Signal] = []

    async def publish(self, signal: Signal) -> None:
        self.signals.append(signal)


class _PacedWorkspace(CaseWorkspace):
    """Keep the prepared synthetic cases out of staff views until their signal arrives."""

    def __init__(self, workflow: CaseWorkflow, case_ids: tuple[UUID, ...]) -> None:
        super().__init__(workflow, case_ids)
        self.released: set[UUID] = set()

    def listing(self, actor: str):
        return tuple(entry for entry in super().listing(actor) if entry[0].case.case_id in self.released)

    def unclaimed(self, case_id: UUID):
        if case_id in self.released:
            return super().unclaimed(case_id)
        return None


async def prepare_arrivals(count: int, minutes: float, p0_count: int, *, starts_at: datetime) -> tuple[Arrival, ...]:
    if not 1 <= p0_count <= count - 4 or not math.isfinite(minutes) or minutes < 0:
        raise ValueError("需要至少 5 单、至少 1 单 P0、每个其他级别至少 1 单，且分钟数有限并不小于 0。")

    cases = {case.case_id: case for case in generate_eval_cases(seed=DRILL_SEED)}
    urgent_slots = {(2 * i + 1) * count // (2 * p0_count) for i in range(p0_count)}
    usual = cycle(_SAMPLES[1:])
    collector = _CollectSignals()
    engine = RecognitionEngine(collector, model=(MOCK_MODEL_VERSION, MockDecisionModel()))
    arrivals = []

    for index in range(count):
        sample = cases[_SAMPLES[0] if index in urgent_slots else next(usual)]
        reference = f"drill-{DRILL_SEED}-{index + 1:03d}"
        offset = index * minutes * 60 / count
        scheduled_at = starts_at + timedelta(seconds=offset)
        events = tuple(
            event.model_copy(update={"ref": event.ref.model_copy(update={
                "event_id": f"{reference}-event-{number}",
                "conversation_id": reference,
                "message_id": f"{reference}-message-{number}" if event.ref.message_id else None,
                "occurred_at": scheduled_at,
            })})
            for number, event in enumerate(sample.events, 1)
        )
        result = await engine.recognize(events)
        signal = result.signal
        if signal is None or (signal.severity, signal.signal_type) != (sample.expected_severity, sample.expected_type):
            raise RuntimeError(f"{reference} ({sample.case_id}) 的识别结果不符合剧本。")
        arrivals.append(Arrival(reference, offset, signal))

    if collector.signals != [arrival.signal for arrival in arrivals]:
        raise RuntimeError("引擎未按剧本交付信号。")
    return tuple(arrivals)


class Drill:
    """One local session, with actual staff actions recorded by the workbench."""

    def __init__(self, arrivals: tuple[Arrival, ...], store: MemoryStore) -> None:
        self.arrivals = arrivals
        self.queue = MemoryQueue()
        self.store = store
        self.workspace = _PacedWorkspace.from_signals(tuple(arrival.signal for arrival in arrivals))
        self.injected: dict[str, float] = {}
        for arrival in arrivals:
            case = self.workspace.case_for_signal(arrival.signal.signal_id)
            if case is None and arrival.signal.severity != "P3":
                raise RuntimeError(f"{arrival.reference} 未匹配已交付的 playbook。")

    async def inject(self, arrival: Arrival) -> None:
        sink: SignalSink = self.queue
        with self.workspace.lock:
            await sink.publish(arrival.signal)
            self.injected[arrival.reference] = time.time()
            case = self.workspace.case_for_signal(arrival.signal.signal_id)
            if case is not None:
                self.workspace.released.add(UUID(case))

    async def release(self, start_delay: float) -> None:
        start = time.monotonic() + start_delay
        for arrival in self.arrivals:
            await asyncio.sleep(max(0, start + arrival.offset_seconds - time.monotonic()))
            await self.inject(arrival)

    def respond_to_synthetic_consent_requests(self) -> None:
        """The scripted customer responds only after a genuine staff action was denied."""
        with self.workspace.lock, self.store.locked():
            for event in self.store.audit_events():
                detail = event.case_detail
                if (event.action != AuditAction.DECIDE or event.result != AuditResult.DENIED
                        or event.case_id is None or detail is None or detail.reason != "customer_consent_required"
                        or detail.step_id not in _SCRIPTED_CONSENTS):
                    continue
                current = self.workspace.workflow.get(UUID(event.case_id))
                if current is None or current.revision != detail.revision or current.active_step is None:
                    continue
                result = self.workspace.workflow.record_synthetic_customer_consent(
                    current.case.case_id, expected_revision=current.revision, step_id=current.active_step.step_id,
                )
                self.store.append_audit(workbench_audit(result.audit))
                if result.audit.outcome != "applied":
                    raise RuntimeError(f"合成客户同意未录入：{result.audit.reason}")
