# MEMORY-ERASURE-COMPOSITION@2

Added explicit driver/factory; HTTP MEMORY-ERASURE@1 and old composition remain
unchanged. A dispatched UNKNOWN hook may only reconcile by original read. A busy
worker must therefore be observed **before first dispatch**, not returned as an
UNKNOWN execute that later needs a forbidden retry to erase content.

`erasure_app.create_erasure_app_v2` takes the old factory's explicit arguments
plus mandatory `hold_payloads`. Its service is
`erasure_driver_v2.ErasureServiceV2(..., hold_payloads=...)`.

```python
@contextmanager
def hold_payloads(store, memory_scope, association_bytes, prototype_request):
    # B verifies the original root plan and observes/locks its physical workers.
    # No delete, first intent, account retirement or hook execution here.
    yield ready  # True only while the actual B payload/worker barrier is held
```

C commits stop/freeze, releases Memory, and creates the immutable original root
plan first. The prototype is the exact original request for the first pending B
target, with the original registry/selection/subject binding. Association bytes
are comparison data supplied by C; they are not an in-progress physical intent.
Preflight may use B's public original-plan observations/locks. Before intent,
AssociationReader correctly denies private physical-evidence access. Each actual
hook must subsequently call the original reader/require_intent normally.

If not ready, every undispatched target remains pending; a later exact original
POST may recheck readiness. No worker queue, operation rekey or automatic hook
retry is added. When ready, C retains the B barrier only around message/run/usage
steps. It releases that barrier before C Trip/Memory cleanup to preserve lock
order. A returned UNKNOWN/failed step stops this pass. Later calls reconcile that
same dispatched step read only; only a confirmed original result permits moving
to a following still-pending target, which needs a new preflight barrier.

The old explicit composition remains available for its original consumers and
C UNKNOWN observation component; it is not proof of this driver. Missing real B
barrier/hooks cannot install composition2 or report whole deletion complete.
Signed component tests prove busy -> zero execute/all pending, ready -> one
execute, then UNKNOWN -> original reconciliation without another dispatch.
