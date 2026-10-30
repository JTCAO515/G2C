"""Narrow read projection using canonical AUTH, original NEEDS readers and objects."""
from dataclasses import dataclass
import threading
from .boundary import Metadata, Operation, _active
from .domain import Denied, identifier
from .postgres import Repository

VERSION = 'CJ-NEEDS-PROTECTED-READ@0.1.0-rc.2'


@dataclass(frozen=True)
class ReadConfiguration:
    environment: str
    issuer: str
    audience: str
    max_response_bytes: int

    def __post_init__(self):
        identifier(self.environment)
        if any(type(x) is not str or not x or len(x) > 2048 for x in (self.issuer, self.audience)):
            raise ValueError('explicit host identity profile required')
        if type(self.max_response_bytes) is not int or self.max_response_bytes <= 0:
            raise ValueError('explicit positive output bound required')


class ProtectedReader:
    """Trusted host composition only. Request supplies token and record selector.

    resolve(principal, environment) -> (fresh_connect, opaque_scope). Configuration
    is the sole host environment selector; no caller owner/configuration allowed.
    project(operation, canonical_auth_context) -> complete bounded bytes, synchronously.
    Only original detail/revision readers are usable in this operation lifetime.
    Fresh AUTH before and after the projection is enforced by the canonical AUTH
    boundary; host composition is trusted and not re-checked during the read.
    """
    def __init__(self, auth, resolve, *, configuration, repository_factory=Repository):
        self.auth, self.resolve, self.configuration = auth, resolve, configuration
        self.repository_factory = repository_factory

    def read(self, token, project):
        config = self.configuration

        def run(context):
            principal = context.principal
            if principal.issuer != config.issuer or principal.audience != config.audience:
                raise Denied('NEEDS read identity profile changed')
            state = dict(active=True, blocked=False, action_id=None, commit_possible=False,
                         write_started=False, read_only=True, thread=threading.get_ident())
            context_token = None

            def guard(stage=None):
                if state['blocked'] or not state['active']:
                    state['blocked'] = True
                    context.invalidate()
                    raise Denied('NEEDS read lifetime unavailable')

            try:
                connect, scope = self.resolve(principal, config.environment)
                repository = self.repository_factory(connect, scope, guard, strict_close=True)
                operation = Operation(repository, Metadata(principal, scope), state)
                context_token = _active.set(operation)
                result = project(operation, context)
                if state['blocked']: raise Denied('NEEDS read invalidated')
                if type(result) is not bytes: raise Denied('fully encoded NEEDS read bytes required')
                if len(result) > config.max_response_bytes: raise Denied('NEEDS read output bound exceeded')
                return result
            except BaseException:
                state['blocked'] = True
                context.invalidate()
                raise
            finally:
                state['active'] = False
                if context_token is not None: _active.reset(context_token)

        return self.auth.with_read_context(token, run)
