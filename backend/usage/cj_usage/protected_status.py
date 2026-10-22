"""Domain consumer of fixed AUTH read context; no JWT, route or dispatch path."""
from dataclasses import dataclass
import inspect
from cj_auth.read_context import (READ_CONTEXT_VERSION, ProtectedReadBoundary,
                                  ProtectedReadContext)
from .core import integer, label
from .postgres import PostgresRepository
from .read_status import ReadUnavailable

EXPECTED_AUTH_READ = 'CJ-AUTH-READ-CONTEXT@0.1.0-rc.1'


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


class AttemptStatusReader:
    def __init__(self, boundary, resolve_repository, *, configuration):
        if (READ_CONTEXT_VERSION != EXPECTED_AUTH_READ or
                type(boundary) is not ProtectedReadBoundary or
                not callable(resolve_repository) or
                type(configuration) is not StatusReadConfiguration):
            raise ReadUnavailable('fixed AUTH boundary, resolver and configuration required')
        self.boundary, self.resolve_repository = boundary, resolve_repository
        self.configuration = configuration

    def read(self, token, attempt_id, *, project=None):
        """Only token + original attempt ID are request inputs.

        project is trusted host final bytes-to-bytes encoding, not request code.
        Host resolves (principal, environment, period_start, period_end) to its
        existing scope. No caller owner/unit/budget/period is accepted here.
        """
        label(attempt_id)
        if project is not None and not callable(project):
            raise ReadUnavailable('synchronous final projection required')
        boundary, resolver, configuration = self.boundary, self.resolve_repository, self.configuration

        completed_binding = None

        def operation(ctx):
            nonlocal completed_binding
            if type(ctx) is not ProtectedReadContext:
                raise ReadUnavailable('canonical read context required')
            principal = ctx.principal

            def current():
                ctx.guard()
                if (ctx.principal != principal or self.boundary is not boundary or
                        self.resolve_repository is not resolver or self.configuration is not configuration or
                        principal.issuer != configuration.issuer or principal.audience != configuration.audience):
                    raise ReadUnavailable('status read host binding changed')

            current()
            repository = resolver(principal, configuration.environment,
                                  configuration.period_start, configuration.period_end)
            current()  # Resolver cannot revoke/swap this lifetime and still select.
            if type(repository) is not PostgresRepository:
                if inspect.iscoroutine(repository):
                    repository.close()
                raise ReadUnavailable('canonical read repository required')
            scope, connect = repository.scope, repository.connect
            completed_binding = (repository, scope, connect)

            def guard():
                current()
                if repository.scope != scope or repository.connect is not connect:
                    raise ReadUnavailable('original repository scope changed')

            result = repository.read_status(attempt_id, guard=guard,
                max_response_bytes=configuration.max_response_bytes,
                expected_period=(configuration.period_start, configuration.period_end),
                project=project)
            guard()  # storage already closed; final domain binding before outer AUTH.
            return result

        result = boundary.with_read_context(token, operation)
        # AUTH's final provider callback follows operation's last domain guard.
        # Validate its effects AFTER the boundary returns using only captured
        # canonical object fields: no further checker/resolver/project/IO call.
        # AUTH has already checked the original context/principal and retired it;
        # do not revive the closed context or create another authorization check.
        if completed_binding is None:
            raise ReadUnavailable('original read binding unavailable')
        repository, scope, connect = completed_binding
        if (self.boundary is not boundary or self.resolve_repository is not resolver or
                self.configuration is not configuration or repository.scope != scope or
                repository.connect is not connect):
            raise ReadUnavailable('final status binding changed')
        return result
