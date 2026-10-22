"""Synchronous request-lifetime seam; AUTH decisions remain trusted host policy."""
from contextlib import contextmanager
import inspect
import threading
from .domain import Command, CommitUnknown


class OperationWithheld(Exception):
    """No private result may be published. Metadata is for trusted composition only."""
    def __init__(self, stage, operation_id=None, commit_possible=False):
        super().__init__('memory operation unavailable')
        self.stage = stage
        self.operation_id = operation_id
        self.commit_possible = commit_possible
        self.recovery = 'reconcile_original' if commit_possible else 'withhold'


class OperationContext:
    """Issued only inside with_operation; no raw repository or authorization mutator."""
    def __init__(self, service, state):
        self._service, self._state = service, state

    def _check(self):
        s = self._state
        if not s['active'] or s['blocked'] or threading.get_ident() != s['thread']:
            raise RuntimeError('memory context expired or used outside request thread')

    def save(self, raw):
        self._check()
        # One write per request preserves an unambiguous original reconcile identity.
        if self._state['operation_id'] is not None:
            raise RuntimeError('one save per operation context')
        c = Command.parse(raw)
        self._state['operation_id'] = c.operation_id
        self._state['writing'] = True
        try:
            return self._service.save(raw)
        finally:
            self._state['writing'] = False

    def query(self, operation_id):
        self._check()
        return self._service.query(operation_id)

    def groups(self):
        self._check()
        return self._service.groups()

    def list_items(self, after=None, limit=50):
        self._check()
        return self._service.list_items(after, limit)

    def detail(self, item_id):
        self._check()
        return self._service.detail(item_id)

    def effective(self, subject, context_id=None):
        self._check()
        return self._service.effective(subject, context_id)


def with_operation(service, guard, operation):
    """guard(stage) -> (existing TrustedPrincipal, server scope), freshly checked.

    Only CJ005 trusted composition supplies either callable. operation(ctx) must
    synchronously return fully encoded JSON bytes; it must not send/stream/store a
    private projection itself. No coroutine, generator or deferred response escapes.
    """
    from cj_auth.interfaces import TrustedPrincipal
    state = dict(active=True, thread=threading.get_ident(), operation_id=None,
                 commit_possible=False, writing=False, blocked=False)
    bound = None
    repository = service.repository

    def check(stage):
        nonlocal bound
        try:
            if state['blocked']:
                raise ValueError('request already withheld')
            current = guard(stage)
            if (type(current) is not tuple or len(current) != 2
                    or type(current[0]) is not TrustedPrincipal
                    or type(current[1]) is not str or not current[1]
                    or current[1] != repository.scope):
                raise ValueError('invalid trusted binding')
            if bound is None:
                bound = current
            elif current != bound:
                raise ValueError('binding changed')
        except Exception:
            state['blocked'] = True
            raise OperationWithheld(stage, state['operation_id'], state['commit_possible']) from None

    class GuardedRepository:
        @contextmanager
        def transaction(self):
            check('transaction')
            try:
                with repository.transaction() as tx:
                    check('transaction_ready')
                    yield tx
                    # Inside the DB transaction, after domain work and BEFORE commit.
                    check('precommit')
                    if state['writing']:
                        state['commit_possible'] = True
                check('private_return')
            except CommitUnknown:
                state['blocked'] = True
                raise

    try:
        check('entry')
        context = OperationContext(type(service)(GuardedRepository()), state)
        result = operation(context)
        if type(result) is not bytes:
            if inspect.iscoroutine(result): result.close()
            raise TypeError('operation must return fully encoded JSON bytes')
        # Serialize inside lifetime, then recheck the identical principal and scope.
        check('return')
        return result
    except OperationWithheld:
        raise
    except Exception as exc:
        if state['commit_possible'] or isinstance(exc, CommitUnknown):
            raise OperationWithheld('result_unavailable', state['operation_id'], True) from None
        raise
    finally:
        state['active'] = False
