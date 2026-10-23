"""Existing AUTH checker + trusted resolver; synchronous response lifetime fence.

Follows the fixed TRIP operation pattern. No caller-owned principal, allow flag,
MESSAGE/RUN assertion, or additional authorization policy is accepted.
"""
from contextvars import ContextVar
from dataclasses import dataclass
import inspect
import threading
from cj_auth.interfaces import AdmissionStatus, TrustedPrincipal
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


class Operation:
    def __init__(self, repository, metadata, state):
        self.__repository, self.__metadata, self.__state = repository, metadata, state

    def __check(self):
        s = self.__state
        if not s['active'] or s['blocked'] or _active.get() is not self or threading.get_ident() != s['thread']:
            s['blocked'] = True
            raise OperationWithheld(s['action_id'], s['commit_possible'])

    @property
    def metadata(self):
        self.__check()
        return self.__metadata

    def __call(self, method, *args):
        self.__check()
        s = self.__state
        try:
            if s.get('read_only', False) and method not in ('detail', 'revision'):
                raise Denied('protected projection is read-only')
            if method == 'act':
                if s['write_started']: raise ValueError('one action per operation')
                if type(args[0]) is not Command: raise ValueError('validated command required')
                aid = args[0].action_id
                if s['action_id'] not in (None, aid): raise ValueError('original action changed')
                s['write_started'] = True
                s['action_id'] = aid
            elif method == 'query_action':
                aid = identifier(args[0])
                if s['action_id'] not in (None, aid): raise ValueError('original action changed')
                s['action_id'] = aid
            result = getattr(self.__repository, method)(*args)
            if method == 'act': s['commit_possible'] = True
            return result
        except BaseException as exc:
            s['blocked'] = True
            s['commit_possible'] |= bool(getattr(exc, 'commit_possible', False)) or isinstance(exc, CommitUnknown)
            if s['commit_possible'] or not isinstance(exc, Exception):
                raise OperationWithheld(s['action_id'], s['commit_possible']) from None
            raise

    def act(self, command): return self.__call('act', command)
    def query_action(self, action_id): return self.__call('query_action', action_id)
    def detail(self, needs_id): return self.__call('detail', needs_id)
    def revision(self, needs_id, version): return self.__call('revision', needs_id, version)


class Boundary:
    def __init__(self, checker=None, resolve=None):
        self.checker, self.resolve = checker, resolve

    def with_operation(self, token, callback):
        state = dict(active=True, blocked=False, action_id=None, commit_possible=False, write_started=False,
                     thread=threading.get_ident())
        context_token = None
        try:
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

            repository = Repository(connect, scope, guard)
            operation = Operation(repository, Metadata(first.principal, scope), state)
            context_token = _active.set(operation)
            guard('entry')
            result = callback(operation)
            if type(result) is not bytes:
                if inspect.iscoroutine(result): result.close()
                raise TypeError('synchronous fully encoded bytes required')
            guard('serialized_return')
            return result
        except BaseException as exc:
            state['blocked'] = True
            state['commit_possible'] |= bool(getattr(exc, 'commit_possible', False)) or isinstance(exc, CommitUnknown)
            if isinstance(exc, OperationWithheld) or state['commit_possible'] or not isinstance(exc, Exception):
                raise OperationWithheld(state['action_id'], state['commit_possible']) from None
            raise
        finally:
            state['active'] = False
            if context_token is not None: _active.reset(context_token)
