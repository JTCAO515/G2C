# MEMORY-STOP-USE@1 — local runtime only

C #270 implementation draft under JT2026-10-30 standing authorization. The
canonical writer has directed private-PG evidence; public API/generated binding,
latest-main migration numbering, full gates and independent review are pending.
Do not treat this draft or a historical receipt as activation/publication rights.

New exact body (32768 bytes maximum) adds a version to the original six-key
withdrawal candidate grammar, which stays unchanged:

```json
{"version":"MEMORY-STOP-USE@1","action_id":"stop-1","operation":"withdraw","item_id":"item-1","expected_version":3,"source_id":"edit-v1:server-derived","expected_source_version":1}
```

No owner, history, epoch, expiry or consent flags are accepted. The current server
binding supplies owner; expected IDs/versions are CAS inputs, not authorization.
The current canonical request guard checks real admission throughout the original
transaction/lifetime. An expired collection policy never grants new source data;
stop-use does not require new collection or renew any source.

One original MEMORY scope lock serializes capture/publication and lifecycle. The
server enumerates the complete connected edit-source chain and original action
bytes, locks every source in stable ID order, validates original source commands,
and checks reverse current-item and historical-management references. Shared,
disconnected, forked, cyclic, missing or >1000-source histories are refused. The
existing check_history validates the enumerated result, never a caller's claim
of completeness. Current source CAS also remains mandatory.

The same transaction sets all sources in that history inactive, marks this item
withdrawn and advances item version and scope epoch; its original management
ledger row records exact original bytes, server history, resulting version and
epoch. Old save/source/action bytes stay intact. This is stop-use only: no physical
delete, backup cleanup, account cleanup or declaration that #26 is complete.
Another item/owner is untouched; shared source history is refused rather than
silently stopping another item's source.

The original action namespace is shared with pause/resume/edit. Same exact bytes
replay only the original receipt, different bytes conflict, and queries do not
resend. After commit/return uncertainty keep original ID/bytes and reconcile under
fresh admission; absence is not retry authorization. No new provider attempt or
reset exposure follows an unknown write.

The additive MEMORY-lifecycle-adapter.2 accepts withdrawn receipts. V1 retains
active/disabled only. The future local withdrawal API and new receipt model/query
must be separate from the immutable old active/disabled receipt schema; legacy
query of a withdrawal ID fails closed. C only generates backend code; iOS is A.

Memory consumption uses the same original capture/require_current/held-lock lease.
If edit/pause/resume/withdrawal commits first, old new deltas/completed/proposals
are refused. If publication locks first, the writer waits until publication
commits; already published prefixes or already sent provider data cannot be
retracted. No new valid result may follow the later epoch/source invalidation.
Wall-clock expiry is checked even without an epoch change. Original RUN, attempts,
UNKNOWN, cancellation and meter rules remain B-owned and unchanged.

Old derived candidates/index results must use that same protected-current lease
before any effect, not a caller hash/epoch. Directed tests re-use an actual worker
capture after real lifecycle commits and prove the guarded late effect is never
entered. This is the shared producer/consumer protocol; CJ020/#23's actual future
job business is still that ticket's integration and is not claimed implemented.

New local-only migration (final number follows current main manifest) extends the
existing ledger's operation/status/shape and nullable withdrawal history/epoch.
Runtime only adds source UPDATE(active); original FORCE RLS, source-approval and
ledger immutability remain. No DELETE/TRUNCATE, new role, BYPASSRLS or SECURITY
DEFINER. Empty up/down/up works; nonempty stop-use semantics refuse down atomically
and retain history. Applied migrations and frozen versions are untouched.

Directed actual-private-PG tests live in stop_use_cases, loaded by memory_run:
complete original+two-edit history retained/stopped, replay/bytes conflict, other
owner/shared source refusal, real rollback and lost ACK, nonempty down refusal,
actual worker lifecycle-first matrix, actual PG lock wait and committed-prefix
ordering, actual draft lifecycle-first matrix, and source deadline during actual
draft materialization. NEEDS draft setup uses B's existing explicit local operator,
not a synthetic Context or C source-flag mutation. A target subset is not a full
CI/L0/L1 acceptance claim; all gates must finish on the eventual exact head.
