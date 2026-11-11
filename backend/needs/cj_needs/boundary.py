"""Existing AUTH checker + trusted resolver; synchronous response lifetime fence.

Follows the fixed TRIP operation pattern. No caller-owned principal, allow flag,
MESSAGE/RUN assertion, or additional authorization policy is accepted.
"""
from contextvars import ContextVar
from dataclasses import dataclass
from cj_auth.interfaces import AdmissionStatus, TrustedPrincipal
from cj_auth.operation_fence import FencedOperation, new_state, run_fenced
from .domain import Command, CommitUnknown, Denied, identifier
from .postgres import Repository

_active = ContextVar('needs_operation', default=None)


class OperationWithheld(Exception):
    def __init__(self, action_id, commit_possible):
        super().__init__('needs operation unavailable')
        self.action_id, self.commit_possible = action_id, commit_possible
        self.recovery = 'reconcile_original' if action_id is not None else 'withhold'


@dataclass(frozen=True, repr=False)
class Metadata:
    principal: TrustedPrincipal
    scope: str


class Operation(FencedOperation):
    active, withheld, commit_unknown = _active, OperationWithheld, CommitUnknown

    def _admit(self, s, method, args):
        if s.get('read_only', False) and method not in ('detail', 'revision'):
            raise Denied('protected projection is read-only')
        if method == 'act':
            if s['write_started']: raise ValueError('one action per operation')
            if type(args[0]) is not Command: raise ValueError('validated command required')
            aid = args[0].action_id
            if s['action_id'] not in (None, aid): raise ValueError('original action changed')
            s['write_started'] = True
            s['action_id'] = aid
            return True
        if method == 'query_action':
            aid = identifier(args[0])
            if s['action_id'] not in (None, aid): raise ValueError('original action changed')
            s['action_id'] = aid
        return False

    def act(self, command): return self._call('act', command)
    def query_action(self, action_id): return self._call('query_action', action_id)
    def detail(self, needs_id): return self._call('detail', needs_id)
    def revision(self, needs_id, version): return self._call('revision', needs_id, version)


class Boundary:
    def __init__(self, checker=None, resolve=None, *, repository_factory=Repository):
        self.checker, self.resolve = checker, resolve
        self.repository_factory = repository_factory

    def with_operation(self, token, callback):
        state = new_state(write_started=False)

        def bind():
            checker, resolve = self.checker, self.resolve
            if checker is None or resolve is None: raise Denied('AUTH unconfigured')
            first = checker.check(token)
            if first.status is not AdmissionStatus.ALLOWED or not isinstance(first.principal, TrustedPrincipal):
                raise Denied('AUTH denied or unknown')
            connect, scope = resolve(first.principal)

            def guard(stage):
                def stable():
                    if (state['blocked'] or self.checker is not checker or self.resolve is not resolve
                            or repository.connect is not connect or repository.scope != scope
                            or repository.guard is not guard):
                        raise Denied('NEEDS binding changed')
                try:
                    stable()
                    current = checker.check(token)
                    stable()
                    if current.status is not AdmissionStatus.ALLOWED or current.principal != first.principal:
                        raise Denied('AUTH changed')
                except BaseException:
                    state['blocked'] = True
                    raise

            repository = self.repository_factory(connect, scope, guard)
            return Operation(repository, Metadata(first.principal, scope), state), guard

        return run_fenced(Operation, state, bind, callback)
