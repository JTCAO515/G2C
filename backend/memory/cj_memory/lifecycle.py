"""Narrow trusted CJ019 transaction adapter; no action parser, SQL or AUTH policy."""
from dataclasses import dataclass
import hashlib
import inspect
from typing import Callable
from .domain import InvalidInput, Receipt, Unavailable
from .postgres import Transaction

INTERFACE_VERSION = 'MEMORY-lifecycle-adapter.1'


@dataclass(frozen=True)
class LifecycleAdapter:
    """Register only at trusted host construction; never supplied by wire/callback.

    action_id(original_utf8) parses without side effects and returns the original ID.
    apply(tx, original_utf8) and query(tx, action_id) use the provided same tx only.
    CJ019 owns both implementations, original ledger and pause/resume semantics.
    """
    action_id: Callable[[bytes], str]
    apply: Callable[[Transaction, bytes], Receipt]
    query: Callable[[Transaction, str], Receipt | None]

    def __post_init__(self):
        for fn in (self.action_id, self.apply, self.query):
            if (not callable(fn) or inspect.iscoroutinefunction(fn)
                    or inspect.isgeneratorfunction(fn) or inspect.isasyncgenfunction(fn)):
                raise ValueError('synchronous fixed lifecycle adapter required')


def _materialized(value):
    if inspect.iscoroutine(value) or inspect.isgenerator(value):
        value.close()
    if inspect.isawaitable(value) or inspect.isgenerator(value) or inspect.isasyncgen(value):
        raise InvalidInput('lifecycle adapter must return materialized values')
    return value


def _id(value):
    if type(value) is not str or not value.strip() or len(value) > 4096:
        raise InvalidInput('original lifecycle action ID required')
    return value


def _receipt(value, action_id, *, allow_absent=False):
    value = _materialized(value)
    if value is None and allow_absent:
        return None
    if (type(value) is not Receipt or value.operation_id != action_id
            or type(value.item_id) is not str or not value.item_id.strip()
            or type(value.version) is not int or value.version < 1
            or value.status not in ('active', 'disabled')
            or type(value.input_sha256) is not str or len(value.input_sha256) != 64
            or any(c not in '0123456789abcdef' for c in value.input_sha256)):
        raise Unavailable('lifecycle receipt unavailable')
    return value


def _adapter(service):
    if type(service.lifecycle_adapter) is not LifecycleAdapter:
        raise Unavailable('lifecycle adapter unavailable')
    return service.lifecycle_adapter


def apply_lifecycle(service, state, raw):
    try:
        adapter = _adapter(service)
        if type(raw) is not bytes or len(raw) > 32768:
            raise InvalidInput('original lifecycle bytes required')
        if state['operation_id'] is not None:
            raise InvalidInput('one original write/action identity per request')
        state['lifecycle_busy'] = True
        action_id = _id(_materialized(adapter.action_id(raw)))
        state['operation_id'] = action_id
        state['action_namespace'] = 'lifecycle'
        state['writing'] = True
        with service.repository.transaction() as tx:
            tx.lock_scope()
            result = _receipt(adapter.apply(tx, raw), action_id)
            # Query the SAME domain ledger on the SAME transaction. Do not manufacture
            # a receipt from caller bytes; this hash is only a validation comparison.
            stored = _receipt(adapter.query(tx, action_id), action_id)
            if stored != result or stored.input_sha256 != hashlib.sha256(raw).hexdigest():
                raise Unavailable('original lifecycle receipt mismatch')
        return stored
    except BaseException:
        state['blocked'] = True
        raise
    finally:
        state['writing'] = False
        state['lifecycle_busy'] = False


def query_lifecycle(service, state, action_id):
    try:
        adapter = _adapter(service)
        action_id = _id(action_id)
        # Keep one unambiguous original reconcile ID; never mix save/action namespaces.
        if state['operation_id'] is not None and (
                state.get('action_namespace') != 'lifecycle' or state['operation_id'] != action_id):
            raise InvalidInput('one original write/action identity per request')
        state['operation_id'] = action_id
        state['action_namespace'] = 'lifecycle'
        state['lifecycle_busy'] = True
        with service.repository.transaction() as tx:
            tx.lock_scope()
            result = _receipt(adapter.query(tx, action_id), action_id, allow_absent=True)
        return result
    except BaseException:
        state['blocked'] = True
        raise
    finally:
        state['lifecycle_busy'] = False
