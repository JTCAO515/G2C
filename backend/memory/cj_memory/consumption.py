"""Held-lock synchronous consumption, available only inside with_operation."""
import inspect
import threading
from .domain import InvalidInput, current_context

_FACTORY = object()


class CurrentMemory:
    """Read-only request/callback-lifetime view; never a reusable publication permit."""
    def __init__(self, snapshot, state, *, _factory=None):
        if _factory is not _FACTORY:
            raise TypeError('current memory is issued only by consume_current')
        self._snapshot, self._state = snapshot, state
        self._active = True

    def _check(self):
        if (not self._active or not self._state['active'] or self._state['blocked']
                or not self._state.get('consuming', False)
                or threading.get_ident() != self._state['thread']):
            raise RuntimeError('current memory view expired or outside callback thread')

    @property
    def items(self):
        self._check()
        return self._snapshot.items

    @property
    def epoch(self):
        self._check()
        return self._snapshot.epoch

    def close(self):
        self._check()
        self._active = False


def consume_current(service, state, subject, context_id, consumer, *, max_result_bytes):
    # No Context argument: caller cannot supply/reuse a previously detached snapshot.
    if (type(subject) is not str or not subject.strip()
            or (context_id is not None and (type(context_id) is not str or not context_id.strip()))
            or type(max_result_bytes) is not int or max_result_bytes < 1
            or not callable(consumer)):
        state['blocked'] = True
        raise InvalidInput('explicit subject/context, synchronous consumer and byte bound required')
    view = None
    state['consuming'] = True
    try:
        with service.repository.transaction() as tx:
            snapshot = current_context(tx, subject, context_id)
            tx.require_current(snapshot, subject, context_id)
            view = CurrentMemory(snapshot, state, _factory=_FACTORY)

            def validate(original_tx):
                if original_tx is not tx:
                    raise RuntimeError('consumption transaction changed')
                tx.require_current(snapshot, subject, context_id)

            # GuardedRepository runs this after AUTH precommit while holding the SAME tx.
            state['consumption_fence'] = validate
            try:
                result = consumer(view)
                view._check()  # Explicit close cannot be treated as completed consumption.
            finally:
                view._active = False  # Expires at callback exit, before AUTH/precommit guards.
            if type(result) is not bytes or len(result) > max_result_bytes:
                # Close synchronous deferred results safely; rejection remains sticky if
                # close itself raises, including cancellation/KeyboardInterrupt.
                if inspect.iscoroutine(result) or inspect.isgenerator(result):
                    result.close()
                raise InvalidInput('consumer must return bounded materialized bytes')
            tx.require_current(snapshot, subject, context_id)
        return result
    except BaseException:
        # A trusted outer callback catching this failure cannot turn it into success.
        state['blocked'] = True
        raise
    finally:
        if view is not None:
            view._active = False
        state.pop('consumption_fence', None)
        state['consuming'] = False
