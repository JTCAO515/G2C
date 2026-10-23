"""Narrow read projection using canonical AUTH, original NEEDS readers and objects."""
from dataclasses import dataclass
import inspect
import threading
from cj_auth.read_context import (READ_CONTEXT_VERSION, ProtectedReadBoundary,
                                  ProtectedReadContext)
from .boundary import Metadata, Operation, _active
from .domain import Denied, identifier
from .postgres import Repository

VERSION = 'CJ-NEEDS-PROTECTED-READ@0.1.0-rc.1'
AUTH_VERSION = 'CJ-AUTH-READ-CONTEXT@0.1.0-rc.1'


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


def _values(config):
    return config.environment, config.issuer, config.audience, config.max_response_bytes


class ProtectedReader:
    """Trusted host composition only. Request supplies token and record selector.

    resolve(principal, environment) -> (fresh_connect, opaque_scope). Configuration
    is the sole host environment selector; no caller owner/configuration allowed.
    project(operation, canonical_auth_context) -> complete bounded bytes, synchronously.
    Only original detail/revision readers are usable in this operation lifetime.
    """
    def __init__(self, auth, resolve, *, configuration):
        if (READ_CONTEXT_VERSION != AUTH_VERSION or type(auth) is not ProtectedReadBoundary
                or not callable(resolve) or type(configuration) is not ReadConfiguration):
            raise ValueError('canonical AUTH and explicit host configuration required')
        self.auth, self.resolve, self.configuration = auth, resolve, configuration

    def read(self, token, project):
        if not callable(project) or inspect.iscoroutinefunction(project):
            raise Denied('synchronous NEEDS projection required')
        auth, resolve, config = self.auth, self.resolve, self.configuration
        config_values = _values(config)
        completed = None

        def frozen_binding():
            # Deliberately no resolver, AUTH/provider, property, IO or user callback.
            if (self.auth is not auth or self.resolve is not resolve or self.configuration is not config
                    or _values(config) != config_values):
                raise Denied('NEEDS read host configuration changed')
            if completed is not None:
                repo, connect, scope, guard = completed
                if (repo.connect is not connect or repo.scope != scope or repo.guard is not guard
                        or repo.strict_close is not True):
                    raise Denied('NEEDS read repository changed')

        def run(context):
            nonlocal completed
            if type(context) is not ProtectedReadContext: raise Denied('canonical AUTH context required')
            principal = context.principal
            if principal.issuer != config.issuer or principal.audience != config.audience:
                raise Denied('NEEDS read identity profile changed')
            state = dict(active=True, blocked=False, action_id=None, commit_possible=False,
                         write_started=False, read_only=True, thread=threading.get_ident())
            context_token = None
            checking = False

            def current_binding():
                # Every resolver callback is surrounded by canonical fresh AUTH.
                context.require_current()
                frozen_binding()
                binding = resolve(principal, config.environment)
                context.require_current()
                frozen_binding()
                if type(binding) is not tuple or len(binding) != 2 or not callable(binding[0]):
                    raise Denied('NEEDS read storage unavailable')
                identifier(binding[1])
                return binding

            def guard(stage=None):
                nonlocal checking
                if checking or state['blocked'] or not state['active']:
                    state['blocked'] = True
                    context.invalidate()
                    raise Denied('NEEDS read lifetime unavailable')
                checking = True
                try:
                    current_connect, current_scope = current_binding()
                    if current_connect is not connect or current_scope != scope:
                        raise Denied('NEEDS read current environment binding changed')
                    frozen_binding()
                except BaseException:
                    state['blocked'] = True
                    context.invalidate()
                    raise
                finally:
                    checking = False

            try:
                connect, scope = current_binding()
                repository = Repository(connect, scope, guard, strict_close=True)
                completed = repository, connect, scope, guard
                operation = Operation(repository, Metadata(principal, scope), state)
                context_token = _active.set(operation)
                guard('entry')
                result = project(operation, context)
                if state['blocked']: raise Denied('NEEDS read invalidated')
                if type(result) is not bytes:
                    if inspect.iscoroutine(result): result.close()
                    raise Denied('fully encoded NEEDS read bytes required')
                if len(result) > config.max_response_bytes: raise Denied('NEEDS read output bound exceeded')
                # All original readers have closed storage before returning. Project
                # has fully encoded its envelope; re-resolve hostenv, then fresh AUTH.
                guard('serialized_return')
                return result
            except BaseException:
                state['blocked'] = True
                context.invalidate()
                raise
            finally:
                state['active'] = False
                if context_token is not None: _active.reset(context_token)

        result = auth.with_read_context(token, run)
        # Canonical AUTH's final provider callback has now completed. Its retired
        # context is not touched; no callbacks follow these original field checks.
        if completed is None: raise Denied('NEEDS read binding unavailable')
        frozen_binding()
        return result
