"""FEASIBILITY@1.0 facade over the accepted checker, protection and solver.

No authority, IO, new constraint compiler or change to legacy candidate versions.
Formal PLACE@1.0/NEEDS@1.0 producers bind separately when their owners freeze.
"""
from dataclasses import dataclass, field
from threading import Event

from .validator import Candidate, Report, evaluate, protect
from .solver import Limits, Problem, SolveResult, solve

VERSION = 'FEASIBILITY@1.0'
INPUT_PROFILE = 'CJ-FEASIBILITY-PINNED-CANDIDATES@1'


@dataclass(frozen=True, repr=False)
class Result:
    """Private in-memory result; neither a publication lease nor a save token."""
    operation: str
    report: Report | SolveResult
    version: str = field(default=VERSION, init=False)
    input_profile: str = field(default=INPUT_PROFILE, init=False)

    @property
    def status(self):
        return self.report.status


def check_constraints(snapshot, revisions) -> Result:
    return Result('check', evaluate(snapshot, revisions))


def check_edit_scope(before, revisions, candidate: Candidate, *, selected_fields,
                     selected_item_ids) -> Result:
    return Result('protect', protect(before, revisions, candidate,
        selected_fields=selected_fields, selected_item_ids=selected_item_ids))


def solve_constraints(problem: Problem, limits: Limits, *, stop: Event) -> Result:
    return Result('solve', solve(problem, limits, stop=stop))
