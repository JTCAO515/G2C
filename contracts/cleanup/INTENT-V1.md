# CLEANUP-INTENT@1

Additive owner seam for #402. It changes neither CLEANUP@1.0 nor @1.1 wire.

```python
from cj_cleanup.store import original_result, require_intent, record_result

# Same dedicated-role transaction and canonical domain locks as actual erasure:
result = original_result(cursor, request)
if result is None:
    require_intent(cursor, request)
    # Owner verifies its fence and performs the exact selected physical erasure.
    result = record_result(cursor, request, "confirmed")
# Commit first. Return the original result only after known commit success.
```

`require_intent(cursor, request) -> None` performs only SELECTs and holds SHARE
locks on the original operation and step through the caller's transaction. It
does not set GUCs, create an intent, mutate state, dispatch, retry or infer success.
The trusted host must already have bound the original subject/operation and its
dedicated local cleanup connection. A cursor/dataclass is not new AUTH authority.

At the persisted-data boundary it requires the unblocked frozen registry/inventory,
exact target and selection plan, protocol, original invocation, request digest and
exact request bytes. Only a persisted `in_progress` step permits a new hook body.
Missing/foreign/mismatched, UNKNOWN, terminal or redacted intents reject. Reconcile
only reads the original result and does not use UNKNOWN as execution permission.

The caller need not read B's private tables or `_load`. `original_result` is a
read of the actual atomic result, not an authorization to rerun an absent result.
The owner still establishes its canonical withdrawal/account fence and verifies
physical erasure before recording confirmed; B does not implement C's domain hook.

Positive/negative executable examples are in `backend/cleanup/tests/foundation_pg.py`:
exact persisted intent reads without changing progress; absent intent remains absent;
wrong selection, UNKNOWN and registry-blocked intent reject before domain deletion.
