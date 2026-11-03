"""MEMORY-ERASURE-COMPOSITION@2: wait before dispatch, reconcile read only."""
from cj_memory.domain import Unavailable
from cj_memory_jobs.postgres import encode
from .erasure_service import ErasureService,BACKEND_TARGETS,ORDER

VERSION='MEMORY-ERASURE-COMPOSITION@2'


class ErasureServiceV2(ErasureService):
    def __init__(self,*args,hold_payloads,**kwargs):
        if hold_payloads is None:raise ValueError('explicit B payload barrier required')
        super().__init__(*args,**kwargs)
        self.hold_payloads=hold_payloads

    def _clean(self,store,scope,coordinator,operation,plan,selection,association,guard):
        while True:
            progress=coordinator.query(operation)
            if progress['status'] in ('blocked','failed'):return
            by_target={s['target']:s for s in progress['steps']}
            first=next((t for t in BACKEND_TARGETS if by_target[t]['state']!='confirmed'),None)
            if first is None:break
            if by_target[first]['state']!='pending':
                # Only the original read is allowed after dispatch. If it
                # confirms, a following still-pending target needs a new barrier.
                if not self._advance_targets(coordinator,operation,plan,selection,association,(first,)):return
                continue
            if association is None:raise Unavailable('original preflight association unavailable')
            prototype=coordinator.request(operation,first,plan[first]['domain_scope'],selection)
            with self.hold_payloads(store,scope,encode(association),prototype) as ready:
                if ready is not True:return
                guard('item_payload_barrier')
                if not self._advance_targets(coordinator,operation,plan,selection,association,BACKEND_TARGETS):return
            break
        # The physical worker barrier is released before acquiring C Trip or
        # Memory rows. No MEMORY -> barrier inversion or hook retry queue.
        guard('item_payload_barrier_released')
        self._advance_targets(coordinator,operation,plan,selection,association,ORDER[len(BACKEND_TARGETS):])
