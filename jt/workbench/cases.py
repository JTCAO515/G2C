"""Staff assignments around JT1's in-process synthetic playbook workflow."""

from threading import RLock
from uuid import UUID

from jt.common import CaseExecution, Signal
from jt.playbook import CaseActionResult, CaseAuditEvent, CaseWorkflow
from jt.playbook.catalog import PLAYBOOKS_BY_SIGNAL
from jt.playbook.workflow import StaffAction

from .store import AuditAction, AuditEvent, AuditResult, CaseAuditDetail


class CaseWorkspace:
    def __init__(self, workflow: CaseWorkflow, case_ids: tuple[UUID, ...]) -> None:
        self.workflow = workflow
        self._assignments = dict.fromkeys(case_ids)
        self.lock = RLock()
        self.failed = False

    @classmethod
    def from_signals(cls, signals: tuple[Signal, ...]) -> "CaseWorkspace":
        workflow = CaseWorkflow()
        case_ids = dict.fromkeys(workflow.ingest(signal).execution.case.case_id
                                  for signal in signals if signal.signal_type in PLAYBOOKS_BY_SIGNAL)
        return cls(workflow, tuple(case_ids))

    def listing(self, actor: str) -> tuple[tuple[CaseExecution, bool], ...]:
        cases = []
        for case_id, owner in self._assignments.items():
            if owner is None or owner == actor:
                execution = self.workflow.get(case_id)
                if execution is not None:
                    cases.append((execution, owner == actor))
        return tuple(sorted(cases, key=lambda item: (item[0].case.severity, item[0].case.created_at)))

    def unclaimed(self, case_id: UUID) -> CaseExecution | None:
        if case_id in self._assignments and self._assignments[case_id] is None:
            return self.workflow.get(case_id)
        return None

    def assign(self, case_id: UUID, actor: str) -> None:
        self._assignments[case_id] = actor

    def owned(self, case_id: UUID, actor: str) -> CaseExecution | None:
        return self.workflow.get(case_id) if self._assignments.get(case_id) == actor else None

    def act(self, case_id: UUID, actor: str, action: StaffAction, revision: int) -> CaseActionResult:
        transitions = {"advance": self.workflow.advance, "confirm": self.workflow.confirm,
                       "reject": self.workflow.reject}
        return transitions[action](case_id, expected_revision=revision, actor_id=actor)


def workbench_audit(event: CaseAuditEvent) -> AuditEvent:
    return AuditEvent(event.occurred_at.timestamp(), AuditAction.DECIDE, event.actor_id, str(event.case_id),
                      AuditResult.SUCCESS if event.outcome == "applied" else AuditResult.DENIED,
                      case_detail=CaseAuditDetail(event.action, event.step_id, event.revision, event.reason))
