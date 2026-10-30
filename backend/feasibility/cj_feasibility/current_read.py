"""NEEDS current-record projection inside canonical NEEDS + AUTH read lifetimes.

This is a real consumer projector, NOT a token entry/factory or close guarantee.
The fixed NEEDS boundary lacks strict close/current-environment settlement; see
CURRENT-READ-SEAM.md. Root publication remains closed pending that owner seam.
"""
from dataclasses import dataclass
from hashlib import sha256
import json

from cj_auth.read_context import ProtectedReadContext
from cj_needs.boundary import Operation
from cj_needs.domain import identifier
from .validator import evaluate

VERSION = 'CJ-FEASIBILITY-CURRENT-READ@0.1.0-candidate.1'


class ReadWithheld(RuntimeError):
    """Safe local refusal; does not reveal owner, resource existence or private data."""
    def __init__(self, code):
        super().__init__('current NEEDS evaluation unavailable')
        self.code = code


@dataclass(frozen=True)
class ReadLimits:
    max_revisions: int
    max_input_bytes: int
    max_output_bytes: int

    def __post_init__(self):
        if any(type(x) is not int or x <= 0 for x in
               (self.max_revisions, self.max_input_bytes, self.max_output_bytes)):
            raise ValueError('explicit positive read bounds required')


def project_current(operation: Operation, context: ProtectedReadContext, needs_id: str, *, limits: ReadLimits) -> bytes:
    """Only caller-selected input is needs_id; no snapshot, owner, scope or callback.

    Return stays INSIDE the canonical contexts. Fresh AUTH before and after this
    projection is the caller's ProtectedReadBoundary; it is not repeated per read.
    Never publish these bytes outside a future owner-provided strict read seam.
    """
    return _project_current(operation, context, needs_id, limits=limits,
                            evaluate_report=evaluate, wire_version=VERSION)


def _project_current(operation, context, needs_id, *, limits, evaluate_report,
                     wire_version, facade_version=None, input_profile=None):
    """Fixed C projectors share one bounded history/output/currentness lifetime."""
    try:
        identifier(needs_id)
        # Two separately valid lifetimes are not proof of one user: bind them.
        if operation.metadata.principal != context.principal:
            raise ReadWithheld('PRINCIPAL_BINDING_MISMATCH')
        first = operation.detail(needs_id)
        if first is None:
            raise ReadWithheld('RECORD_UNAVAILABLE')
        if not 1 <= first.version <= limits.max_revisions:
            raise ReadWithheld('REVISION_BOUND_EXCEEDED')
        if len(first.content) > limits.max_input_bytes:
            raise ReadWithheld('INPUT_BOUND_EXCEEDED')
        consumed = len(first.content)
        revisions = []
        for version in range(1, first.version + 1):
            revision = operation.revision(needs_id, version)
            if revision is None:
                raise ReadWithheld('REVISION_CHAIN_UNAVAILABLE')
            consumed += len(revision.content) + len(revision.original_input)
            if consumed > limits.max_input_bytes:
                raise ReadWithheld('INPUT_BOUND_EXCEEDED')
            revisions.append(revision)
        # Reuse the existing fixed evaluator; do not replay history a second way.
        report = evaluate_report(first, tuple(revisions))
        if report.status == 'INVALID':
            raise ReadWithheld('EVALUATION_INPUT_INVALID')
        if report.status not in ('CONFLICT', 'UNKNOWN'):
            raise ReadWithheld('UNSUPPORTED_EVALUATION_VERDICT')
        # Compact immutable projection. Original source bytes remain in memory
        # and their authorized declaration JSON is included, never lossy coerced.
        checks = []
        for check in report.checks:
            checks.append(dict(code=check.code, status=check.status, missing=check.missing,
                               zh=check.zh, en=check.en, details=check.details,
                               evidence=[dict(path=e.path, declaration=json.loads(e.declaration),
                                              revision=e.revision, action_id=e.action_id,
                                              original_input_sha256=sha256(e.original_input).hexdigest()
                                              if e.original_input is not None else None)
                                         for e in check.evidence]))
        body = dict(version=wire_version, evaluator_version=report.version if facade_version is None else facade_version, status=report.status,
                    needs_id=first.needs_id, revision=first.version, content_sha256=report.content_sha256,
                    overall='UNKNOWN', checks=checks,
                    sources=[dict(revision=r.version, action_id=r.action_id,
                                  original_input_utf8=r.original_input.decode('utf-8'),
                                  original_input_sha256=sha256(r.original_input).hexdigest())
                             for r in revisions])
        if input_profile is not None: body['input_profile'] = input_profile
        # Iterative encoding enforces the output bound during projection, rather
        # than allocating an unbounded serialized result before checking length.
        output = bytearray()
        for chunk in json.JSONEncoder(ensure_ascii=False, separators=(',', ':'), allow_nan=False).iterencode(body):
            encoded = chunk.encode('utf-8')
            if len(output) + len(encoded) > limits.max_output_bytes:
                raise ReadWithheld('OUTPUT_BOUND_EXCEEDED')
            output.extend(encoded)
        frozen = bytes(output)
        # Independent transactions: the record must not have advanced while reading history.
        if operation.detail(needs_id) != first:
            raise ReadWithheld('CURRENT_RECORD_OR_BINDING_CHANGED')
        return frozen
    except ReadWithheld:
        context.invalidate()
        raise
    except Exception:
        context.invalidate()
        raise ReadWithheld('READ_OR_LIFETIME_UNAVAILABLE') from None
