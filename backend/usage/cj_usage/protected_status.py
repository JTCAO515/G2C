"""Domain consumer of fixed AUTH read context; no JWT, route or dispatch path."""
from dataclasses import dataclass
from .core import integer, label
from .read_status import ReadUnavailable


@dataclass(frozen=True)
class StatusReadConfiguration:
    environment: str
    issuer: str
    audience: str
    period_start: int
    period_end: int
    max_response_bytes: int

    def __post_init__(self):
        for value in (self.environment, self.issuer, self.audience):
            label(value)
        integer(self.period_start)
        integer(self.period_end, self.period_start + 1)
        integer(self.max_response_bytes, 1)


def _no_stage_check():
    # Fresh AUTH at entry and before bytes escape is enforced by ProtectedReadBoundary.
    return None


class AttemptStatusReader:
    def __init__(self, boundary, resolve_repository, *, configuration):
        self.boundary, self.resolve_repository = boundary, resolve_repository
        self.configuration = configuration

    def read(self, token, attempt_id, *, project=None):
        """Only token + original attempt ID are request inputs.

        project is trusted host final bytes-to-bytes encoding, not request code.
        Host resolves (principal, environment, period_start, period_end) to its
        existing scope. No caller owner/unit/budget/period is accepted here.
        """
        label(attempt_id)
        configuration = self.configuration

        def operation(ctx):
            principal = ctx.principal
            if principal.issuer != configuration.issuer or principal.audience != configuration.audience:
                raise ReadUnavailable('status read identity profile mismatch')
            repository = self.resolve_repository(principal, configuration.environment,
                                                 configuration.period_start, configuration.period_end)
            if repository is None:
                raise ReadUnavailable('no accepted host mapping for this principal')
            return repository.read_status(attempt_id, guard=_no_stage_check,
                max_response_bytes=configuration.max_response_bytes,
                expected_period=(configuration.period_start, configuration.period_end),
                project=project)

        return self.boundary.with_read_context(token, operation)
