"""FEASIBILITY-PROPOSED@1: actual source protection plus one shared checker.

Candidate declarations have no committed provenance. No fake Snapshot/Revision,
source approval, solver engine or write/currentness permission is manufactured.
"""
from .validator import protect,_evaluate_fields,_report
from cj_needs.domain import decode

VERSION='FEASIBILITY-PROPOSED@1'


def evaluate(before,revisions,candidate,*,selected_fields,selected_item_ids):
    scope=protect(before,revisions,candidate,selected_fields=selected_fields,
                  selected_item_ids=selected_item_ids)
    if not any(c.code=='PROTECTED_SCOPE_UNCHANGED' and c.status=='PASS' for c in scope.checks):
        return scope
    # Public protection validated these immutable bytes at the boundary. Proposed
    # fields have no new source revisions; original evidence remains in scope.
    checked=_evaluate_fields(candidate,decode(candidate.content),{})
    return _report(candidate,list(scope.checks)+list(checked.checks))
