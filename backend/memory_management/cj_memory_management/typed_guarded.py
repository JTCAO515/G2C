"""Typed lifecycle uses B M/T before MEMORY and the existing original ledger."""
from contextlib import nullcontext
from cj_memory.domain import Unavailable
from cj_memory.lifecycle import LifecycleAdapterV2
from .guarded import GuardedService
from .service import apply_in_transaction,query_in_transaction
from .typed import parse_action,TypedEdit


def execute(repository,policy,guard,authority,raw,project):
    action=parse_action(raw)
    if authority.repository.scope!=repository.scope:
        raise Unavailable('typed lifecycle owner binding mismatch')
    probe=GuardedService(repository,manual_policy=policy)
    exists=probe.with_operation(guard,lambda context:b'1' if context.query(action.action_id) is not None else b'0')==b'1'
    held=(authority.hold_current(action.context)
          if isinstance(action,TypedEdit) and action.context is not None and not exists else nullcontext(None))
    with held as lease:
        def check(current):
            if isinstance(current,TypedEdit) and current.context is not None:
                if lease is None or lease.context!=current.context:
                    raise Unavailable('original current-context lease required for typed edit')
                lease.check()
        adapter=LifecycleAdapterV2(lambda value:parse_action(value).action_id,
            lambda transaction,value:apply_in_transaction(transaction,parse_action(value),policy,check),
            query_in_transaction)
        service=GuardedService(repository,manual_policy=policy,lifecycle_adapter=adapter)
        return service.with_operation(guard,lambda context:project(context.apply(raw)))


def query(repository,policy,guard,action_id,project):
    return GuardedService(repository,manual_policy=policy).with_operation(
        guard,lambda context:project(context.query(action_id)))
