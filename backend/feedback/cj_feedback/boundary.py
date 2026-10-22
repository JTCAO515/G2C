"""Consume canonical AUTH; synchronous operation owns final encoded publication."""
from contextvars import ContextVar
import inspect
import threading
from cj_auth.admission import AdmissionChecker
from cj_auth.interfaces import AdmissionStatus, TrustedPrincipal
from .domain import Action, InvalidInput, Unavailable, CommitUnknown
from .postgres import Repository

_active = ContextVar('feedback_operation', default=None)


class OperationWithheld(Unavailable):
    def __init__(self, commit_possible):
        super().__init__()
        self.commit_possible = commit_possible
        # Never implies an earlier attempt was absent, even if this attempt did not commit.
        self.recovery = 'reconcile_original'


class _Operation:
    def __init__(self, repository, guard):
        self.__repository, self.__guard = repository, guard
        self.active, self.blocked = True, False
        self.thread = threading.get_ident()
        self.commit_possible, self.write_attempted = False, False

    def check(self):
        if (not self.active or self.blocked or _active.get() is not self
                or self.thread != threading.get_ident()):
            self.blocked = True
            raise OperationWithheld(self.commit_possible)

    def _call(self, name, value):
        try:
            self.check()
            self.__guard('operation')
            if name == 'submit':
                if self.write_attempted: raise InvalidInput()
                self.write_attempted = True
            result = getattr(self.__repository, name)(value)
            if name == 'submit': self.commit_possible = True
            self.check()
            return result
        except BaseException as exc:
            self.blocked = True
            self.commit_possible |= isinstance(exc, CommitUnknown)
            raise

    def submit(self, action): return self._call('submit', action)
    def query_action(self, action_id): return self._call('query_action', action_id)


class Boundary:
    """Host passes an existing AdmissionChecker and trusted principal→(connect,scope).

    Resolver must use stable issuer/subject + environment, not JWT expiry or a body
    field. It must return a new idle connection factory. No membership source here.
    """
    def __init__(self, checker, resolve, *, sources=None):
        if not isinstance(checker, AdmissionChecker) or not callable(resolve): raise Unavailable()
        if sources is not None:
            from .sources import Sources
            if type(sources) is not Sources or sources.message.checker is not checker: raise Unavailable()
        self.checker, self.resolve, self.sources = checker, resolve, sources

    def with_operation(self, token, operation):
        op = None
        context_token = None
        try:
            checker, resolve, sources = self.checker, self.resolve, self.sources
            source_binding = (sources.message, sources.resolve_run, sources.message.checker, sources.message.resolve_repository) if sources is not None else None
            first = checker.check(token)
            if first.status is not AdmissionStatus.ALLOWED or not isinstance(first.principal, TrustedPrincipal):
                raise Unavailable()
            connect, scope = resolve(first.principal)
            repository = None

            def unchanged():
                if (self.checker is not checker or self.resolve is not resolve
                        or repository.connect is not connect or repository.scope != scope
                        or self.sources is not sources or repository.sources is not sources
                        or (sources is not None and (sources.message, sources.resolve_run, sources.message.checker, sources.message.resolve_repository) != source_binding)):
                    raise Unavailable()

            def guard(stage):
                try:
                    if op is not None: op.check()
                    unchanged()
                    current = checker.check(token)
                    unchanged()  # Slow/reentrant provider may mutate server composition.
                    if current.status is not AdmissionStatus.ALLOWED or current.principal != first.principal:
                        raise Unavailable()
                    if op is not None: op.check()
                except BaseException:
                    if op is not None: op.blocked = True
                    raise

            repository = Repository(connect, scope, guard, sources=sources, token=token, principal=first.principal)
            op = _Operation(repository, guard)
            context_token = _active.set(op)
            guard('entry')
            result = operation(op)
            if type(result) is not bytes:
                if inspect.iscoroutine(result): result.close()
                raise InvalidInput()
            result = repository.finish_projection(result)
            guard('serialized_return')  # After codec/projection; no deferred private values.
            return result
        except BaseException as exc:
            if op is not None:
                op.blocked = True
                op.commit_possible |= isinstance(exc, CommitUnknown)
            if ((op is not None and op.commit_possible)
                    or not isinstance(exc, Exception) or isinstance(exc, OperationWithheld)):
                raise OperationWithheld(op.commit_possible if op is not None else False) from None
            if isinstance(exc, (InvalidInput, Unavailable)):
                raise
            # Conflict is a safe domain result; driver/provider/codec text is not.
            from .domain import Conflict
            if isinstance(exc, Conflict): raise
            raise Unavailable() from None
        finally:
            if op is not None: op.active = False
            if context_token is not None: _active.reset(context_token)
