"""Restricted management context on canonical MEMORY-lifecycle-adapter.1.

No AUTH types, decisions, request state or transaction lifetime are implemented
here. Those remain the original MEMORY Service's responsibility.
"""
from cj_memory.domain import Service as MemoryService
from cj_memory.lifecycle import INTERFACE_VERSION, LifecycleAdapter
from .domain import Action
from .service import apply_in_transaction, query_in_transaction

if INTERFACE_VERSION != 'MEMORY-lifecycle-adapter.1':
    raise RuntimeError('unsupported canonical lifecycle interface')


def original_action_id(raw):
    return Action.parse(raw).action_id


def apply(transaction, raw):
    return apply_in_transaction(transaction, Action.parse(raw))


ADAPTER = LifecycleAdapter(original_action_id, apply, query_in_transaction)


class ManagementContext:
    """Only apply/query; original context enforces lifetime on every access."""
    def __init__(self, canonical_context):
        self.__canonical = canonical_context

    def apply(self, original_utf8):
        return self.__canonical.apply_lifecycle(original_utf8)

    def query(self, action_id):
        return self.__canonical.query_lifecycle(action_id)


class GuardedService(MemoryService):
    def __init__(self, repository, *, manual_policy=None, lifecycle_adapter=ADAPTER):
        if manual_policy is not None or lifecycle_adapter is not ADAPTER:
            raise ValueError('fixed management adapter required')
        super().__init__(repository, lifecycle_adapter=ADAPTER)

    def with_operation(self, guard, operation):
        return super().with_operation(
            guard, lambda canonical: operation(ManagementContext(canonical)))
