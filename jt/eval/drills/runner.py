"""Batch synthetic cases through the real local recognition and playbook interfaces."""

from dataclasses import dataclass
from functools import partial
from typing import Literal

from jt.common import CaseExecution, Severity, Signal, SignalType
from jt.engine.decision import MOCK_MODEL_VERSION, MockDecisionModel
from jt.engine.recognition import RecognitionEngine
from jt.eval.dataset import generate_eval_cases
from jt.playbook import CaseActionResult, CaseAuditEvent, CaseIntake, CaseWorkflow, IntakeDenied


DRILL_SEED = 1713
_ACTOR = "staff-synthetic-drill"


@dataclass(frozen=True)
class Scenario:
    sample_id: str
    severity: Severity
    signal_type: SignalType
    playbook_id: str | None
    minimum_consent_checks: int = 0


_SCENARIOS = (
    Scenario("zh-lost", "P0", "safety", "p0_assistance"),
    Scenario("en-document", "P1", "document_loss", "document_loss"),
    Scenario("en-flight", "P2", "itinerary_disruption", "flight_change", minimum_consent_checks=2),
    Scenario("zh-hotel-change", "P3", "change_request", None, minimum_consent_checks=1),
    Scenario("en-loop", "P4", "ai_failure_loop", "ai_failure"),
)


@dataclass(frozen=True)
class ActionEvidence:
    action: str
    step_id: str | None
    revision: int | None
    outcome: str
    reason: str | None


@dataclass(frozen=True)
class DrillResult:
    sample_id: str
    severity: Severity
    signal_type: SignalType
    status: Literal["PASS", "FAIL"]
    playbook_id: str | None
    playbook_version: str | None
    actions: tuple[ActionEvidence, ...]
    error: str | None = None


class DrillFailure(RuntimeError):
    """The local workflow did not produce the expected drill evidence."""


class _CaseSink:
    def __init__(self, workflow: CaseWorkflow, scenario: Scenario) -> None:
        self.workflow = workflow
        self.scenario = scenario
        self.intake: CaseIntake | None = None

    async def publish(self, signal: Signal) -> None:
        if (signal.severity, signal.signal_type) != (self.scenario.severity, self.scenario.signal_type):
            raise DrillFailure(f"unexpected signal {signal.severity}/{signal.signal_type}")
        self.intake = self.workflow.ingest(signal)


def _record(audit: CaseAuditEvent, actions: list[ActionEvidence]) -> None:
    actions.append(ActionEvidence(audit.action, audit.step_id, audit.revision, audit.outcome, audit.reason))


def _checked(
    result: CaseActionResult, actions: list[ActionEvidence], *, denied_for: str | None = None,
) -> CaseExecution:
    audit = result.audit
    _record(audit, actions)
    expected_outcome = "applied" if denied_for is None else "denied"
    if audit.outcome != expected_outcome or audit.reason != denied_for or result.execution is None:
        raise DrillFailure(f"{audit.action} at {audit.step_id}: {audit.outcome}, reason {audit.reason}")
    return result.execution


def _execute(
    workflow: CaseWorkflow,
    current: CaseExecution,
    scenario: Scenario,
    actions: list[ActionEvidence],
) -> CaseExecution:
    case_id = current.case.case_id
    advance = partial(workflow.advance, case_id, actor_id=_ACTOR)
    confirm = partial(workflow.confirm, case_id, actor_id=_ACTOR)
    reject = partial(workflow.reject, case_id, actor_id=_ACTOR)
    consent = partial(workflow.record_synthetic_customer_consent, case_id)
    if sum(step.requires_customer_confirmation for step in current.case.steps) < scenario.minimum_consent_checks:
        raise DrillFailure("playbook lacks the required customer consent steps")

    for step in current.case.steps:
        finish = advance
        if step.mode == "ai_draft_human_confirm":
            current = _checked(advance(expected_revision=current.revision), actions)
            if scenario.severity == "P0":
                current = _checked(reject(expected_revision=current.revision), actions)
                current = _checked(advance(expected_revision=current.revision), actions)
            finish = confirm

        if step.requires_customer_confirmation:
            unchanged = _checked(
                finish(expected_revision=current.revision), actions, denied_for="customer_consent_required",
            )
            if unchanged != current:
                raise DrillFailure(f"denied action changed execution at {step.step_id}")
            current = _checked(consent(expected_revision=current.revision, step_id=step.step_id), actions)

        current = _checked(finish(expected_revision=current.revision), actions)

    if current.case.status != "closed":
        raise DrillFailure("case did not close after completing its playbook")
    return current


async def run_drills() -> tuple[DrillResult, ...]:
    cases = {case.case_id: case for case in generate_eval_cases(seed=DRILL_SEED)}
    workflow = CaseWorkflow()
    model = (MOCK_MODEL_VERSION, MockDecisionModel())
    results = []

    for scenario in _SCENARIOS:
        sink = _CaseSink(workflow, scenario)
        engine = RecognitionEngine(sink, model=model)
        actions: list[ActionEvidence] = []
        playbook_id = playbook_version = None
        error = None
        try:
            recognized = await engine.recognize(cases[scenario.sample_id].events)
            if recognized.signal is None or sink.intake is None:
                raise DrillFailure("the engine did not publish a signal to the case workflow")
            intake = sink.intake
            current = intake.execution
            playbook_id = current.case.playbook_id
            playbook_version = current.case.playbook_version
            if scenario.playbook_id is not None and playbook_id != scenario.playbook_id:
                raise DrillFailure(f"unexpected playbook {playbook_id}")
            if intake.audit is None or intake.audit.action != "open" or intake.audit.outcome != "applied":
                raise DrillFailure("initial case intake did not record an applied open audit")
            _record(intake.audit, actions)
            closed = _execute(workflow, current, scenario, actions)
            replay = workflow.ingest(recognized.signal)
            if replay.audit is not None or replay.execution != closed:
                raise DrillFailure("signal replay changed the case or produced an audit")
        except (DrillFailure, IntakeDenied) as exc:
            error = str(exc)

        results.append(DrillResult(
            sample_id=scenario.sample_id,
            severity=scenario.severity,
            signal_type=scenario.signal_type,
            status="FAIL" if error is not None else "PASS",
            playbook_id=playbook_id,
            playbook_version=playbook_version,
            actions=tuple(actions),
            error=error,
        ))

    return tuple(results)
