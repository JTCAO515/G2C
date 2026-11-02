# MEMORY-HISTORY@1 / MEMORY-JOBS@1 / CJ020-internal.2

Additive M3 C local runtime contracts for #409. Old MEMORY, MESSAGE, SQLite
`CJ020-internal.1` and original receipts keep their existing bytes and semantics.
This version provides a durable queue and consent, not successful model extraction
or an active Memory receipt. Those remain #410/#411/#413.

## Canonical authority and consent

The host installs `cj_memory_jobs.local_app` explicitly over the existing local
app. It uses the original MESSAGE Boundary and canonical signed admission checker;
only its captured principal/scope selects C's MEMORY repository. A fresh check of
the same checker/principal occurs before C commit and the original Boundary checks
again before returning fully encoded private bytes. No owner, scope, source policy,
enabled boolean, module name or SQL can arrive from the client as authority.

History organization defaults **off for every conversation**. Saving one manual
Memory or saying "enable all history" in chat does not install consent. An explicit
history action addresses exactly one owned current conversation. Enable, disable
and re-enable each advance `source_version`; exact original action replay only
returns its historical receipt. Querying a receipt or a task never renews a source,
starts work or interprets absence as permission to resend.

`POST /v3/memory-history-actions`, octet-stream UTF8 JSON, ≤32768 bytes, exactly:

```json
{"version":"MEMORY-HISTORY@1","action_id":"enable-1","operation":"enable","conversation_id":"chat","expected_generation":"generation","expected_epoch":0,"expected_source_version":0}
```

`operation` is `enable` or `disable`. IDs are exact nonblank UTF8, no NUL or
normalization: action ID ≤4096 bytes, conversation ID ≤256 bytes, generation
≤1024 bytes. Epoch and expected source version are non-bool signed-int64 integers
≥0. Source version 0 means no prior consent row. The current MESSAGE head is read
under its public protected context; conflicting versions require user review.
Unknown keys, duplicate keys, invalid Unicode and invalid versions fail.

`GET /v3/memory-history-settings?conversation_id=...` returns current effective
enablement plus generation/epoch/source version/withdrawal epoch. An owned chat
with no consent has enabled=false, source_version=0, withdrawal_epoch=1. A missing
schema, failed query, revoked account or erased domain never becomes default off.
Generation/epoch drift makes the old grant ineffective; it does not reset its
version. The read creates no scope, consent or action.

`GET /v3/memory-history-receipts?action_id=...` reads the original action only.
Responses are `{version:"MEMORY-HISTORY-result@1",request_id,result}`. Settings
result has the fields above. Action result additionally has action_id and the
SHA256 of the **exact original action bytes**. A receipt is historical data, not
an execution capability. The original action ID/bytes must survive UNKNOWN.

## Protected source and queue

Each enqueue/start/complete reenters the fixed `MESSAGE-SOURCE@1` public seam.
Lock order is MESSAGE scope → canonical MEMORY scope → C history fence/consent.
C SourcePolicy holds those C locks through the bounded callback, rechecks the
current consent/source/withdrawal versions, then checks admission before commit.
The source cursor and serialized snapshots alone confer no permission.

`POST /internal/v1/memory-history/jobs`, same content type/byte cap, exactly:

```json
{"version":"MEMORY-JOBS@1","job_id":"job-1","attempt_id":"attempt-1","source":{"conversation_id":"chat","generation":"generation","epoch":0,"after":0,"through":1,"source_version":1,"withdrawal_epoch":1,"mode":"incremental"}}
```

SourceQuery is B's fixed shape: initial MESSAGE epoch may be **0**; source and
withdrawal versions start at 1; continuous `(after,through]` contains 1–100
committed messages. Mode is incremental or conversation_end. End mode requires
the actual immutable B end signal at that exact current head, independent of Trip.
There is no fabricated inactivity/end signal or silent tail truncation. Long
conversation summary composition is #411; unsupported intervals are rejected.

Queue job/attempt IDs are exact nonblank strings ≤256 characters. Same original
IDs/bytes/source return the same stored result. A different ID or payload cannot
avoid the same-source uniqueness check. Source byte digest and stream-key columns
are checked when rows are read. A unique unresolved stream and persisted processing
cursor reject gaps/overlap; completion and cursor advance share one transaction.
Old completed replay cannot move the cursor backwards. No capacity/age eviction
is used as a Memory retention policy.

Each task also records the canonical MEMORY scope epoch at enqueue. A later manual
save/edit/pause/withdrawal that changes that epoch rejects the old task's start or
candidate completion. Read-only original status/recovery remains available. This
is not an expiry-only publication permit; actual model/Memory publication still
uses the current canonical Memory selection/fences when #410/#413 are connected.

`GET /internal/v1/memory-history/jobs?job_id=...&attempt_id=...` is a current-account
original-status read, independent of old consent enablement/version. It returns
no raw source/candidate and grants no extraction/dispatch permission. Response:
`{version:"MEMORY-JOBS-result@1",request_id,result}`; result contains job_id,
attempt_id,state,processed_through,input_sha256 of the exact original enqueue bytes.

States are pending, inflight, unknown, completed, cancelled, failed. A begun
attempt cannot begin again. Recovery marks/queries the same original attempt;
unknown is never requeued automatically. Cancel/failed metadata cannot publish
new candidates. Start/complete require a fresh source lease. A completed candidate
is bounded immutable UTF8 ≤16384 bytes and is still derived data, never "remembered".
COMMIT ACK loss or postcommit admission failure reports UNKNOWN and reconciles the
original task/action. Precommit denial rolls back that attempt. It is not proof
that a previous unknown attempt with the same ID never committed.

## Batch/provenance version

`CJ020-internal.2` preserves original MESSAGE draft.1/send.1/.2/.3/.4 UTF8, receipt
IDs, generation, sequence and digest in a bounded ≤262144-byte canonical batch.
Its SourceV2 contains cursor/source_version/**withdrawal_epoch**, not V1's
memory_epoch. Mode chooses source_kind committed_message or conversation_summary.
Versioned decoders reject each other's bytes; no failed-parse fallback exists.
The existing V1 codec does not start accepting new message versions or epoch 0.

SourceKind reserves exactly manual, committed_message, conversation_summary,
**staff_proposed**. Staff submission is not implemented; a batch cannot select
manual/staff provenance, and neither source kind nor model text is approval.
Existing candidate→active states are sufficient for ADR-0009; a new reviewed
confirmation action is still required by #410. Candidate data never enters current
Memory reads, drafts or planning. Unprocessed/refused candidates remain ineffective.

## Storage, cleanup and boundaries

Append-only local migration M33 provides history_fence, history_consent, history_action, history_job,
history_cursor under the `cj_memory_` prefix. Runtime uses forced scoped RLS and
only SELECT/INSERT/necessary column UPDATE. It has no DELETE/TRUNCATE or cleanup
role membership. The old isolated SQLite path remains a test candidate until its
consumers/data/rollback are separately verified; `production_queue()` stays closed.

Same-PR registry entry `memory-derived` lists the provided tables and owner hook.
The hook consumes `CLEANUP@1.1`, B's dedicated cleanup Store and original result
helpers; actual erasure and the original result commit together. It validates the
persisted original intent before deletion, and binds RLS to the frozen plan's
domain_scope. An irreversible fence also covers an empty domain and stores only
SHA256(scope)/erased, with no retained account-scope plaintext.
ACK loss is unknown until original result query; it never re-executes deletion.
Only #26/#27 cleanup paths use this role. The organizer cannot acquire it.

This queue stage supports account cleanup. Item mapping/cleanup is completed with
the actual item producer in #410/#26; unsupported item selection returns failed,
never a fabricated success or deletion of the entire account. No precise Memory
item association is claimed before that producer exists. Backup recovery must
replay fences before reads/writes; real backups remain #30.

All content remains until user deletion/account closure; expiry limits use, not
physical retention. Real model quality/cost, cloud, actual users and device/App
acceptance remain UNRUN. Positive/negative examples are executable in
`backend/memory_jobs/tests/test_pg_contract.py`; signed API/role/queue/fence evidence
is in `queue_pg.py`, with independent review and exact-head CI required to publish.
