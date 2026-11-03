# MESSAGE-ERASURE-HEADERS@1

Additive protected Python metadata capability for the actual merged C467/C471
consumer blocked by #472/#403: deleting a manually saved Memory without an origin
message permits old authorized chat to be extracted again. SOURCE1/2, source
status1, all HTTP/wire versions and existing payload/cleanup ABIs are unchanged.
This first capability replaces no active version; ordinary/Travel/decision source
and history readers still have their merged consumers. It is not SOURCE3.

## Entry and types

Inside the actual canonical `Boundary.with_history_context(token, callback)`:

```python
context.with_erasure_headers(project, max_refs=1000, max_result_bytes=1_000_000)
# project(snapshot: HeaderSnapshot) -> fully materialized bytes
```

The bound context, canonical runtime repository, fresh verified principal and
trusted owner mapping are mandatory. No caller owner, scope, conversation list,
SourcePermit, cached allowed flag, initializer or cleanup connection is accepted.
The current runtime role and actual current account are checked in the same
MESSAGE transaction before collection, before callback and after callback;
the original fresh identity/admission guards additionally bracket callback,
commit/physical close and final return. The existing canonical ACCOUNT2 host
must issue the context, as used by C's merged collection/erasure host.

Pure metadata reading supports the existing message scope families without a C
editing producer or publisher. Internally the B reader temporarily declares the
already-implemented edit-result shared-table compatibility while it SELECTs the
scope/headers. Owner/account RLS remains active. The original transaction-local
ABI setting is restored **before any caller callback**; the row lock remains.
No connection/cursor or publisher configuration is exposed, no DML is performed,
and the unconfigured host's ordinary reads/writes/dispatch still refuse. A SQL
failure before restoration propagates unchanged and outer rollback/close clears
LOCAL settings; no restore query is attempted on an aborted transaction.

`HeaderSnapshot` exposes:

| Property/method | Meaning |
|---|---|
| version | Constant `MESSAGE-ERASURE-HEADERS@1`, compatibility only |
| principal / scope | Original verified context identity / actual owner partition |
| references | Tuple of immutable `MessageReference` values |
| complete | True only for the actual full bounded owned snapshot, including zero rows |
| check() | Same-thread, still-active callback/context lifetime check |

Each `MessageReference` has exactly `conversation_id`, `generation`, `sequence`,
`message_id`, `input_sha256`; `to_dict()` copies precisely those five fields.
These are comparison/fence data, not execution or collection authority. Copies
may be frozen into C's original private operation; no live handle or later
permission follows the copied data.

Snapshot properties/check reject after the callback or on another thread. The
version label and immutable copied reference values grant nothing by themselves.
No raw chat/source/model body, run text, provider information or keys are returned.

## Completeness and lock window

The actual canonical MESSAGE scope row remains FOR UPDATE locked through the
callback and its returned bytes. All owned original receipts are included,
including inactive/ended conversations, not just current collection-enabled
pages. SQL computes `sha256(raw_input)` without transferring raw bytes and must
match the persisted input SHA. Per-conversation generation and contiguous
sequences 1..last_sequence must account for the complete receipt set. Missing
head/receipt, a gap, unsupported conversation kind or bad hash fails before the
callback; no truncation or absence-to-success conversion.

`max_refs` is an explicit integer 1..10000; output bytes an explicit integer
1..8388608. Oversized inventory fails before callback. A genuine zero-reference
scope is complete, provided its actual scope/account exists and no nonempty
head contradicts it. No empty array, caller flag or not-installed state can
manufacture that proof.

C may hold its own canonical Memory transaction inside this synchronous window
to stop/freeze the original deletion and store minimum hash fences. Required
order is **MESSAGE -> Memory**; C completes its commit before returning bytes.
No provider/network wait, await, deferred generator, second MESSAGE lock, cleanup
role or B payload barrier may be introduced in the callback. The separate
COMPOSITION2 physical barrier remains after C stop/freeze and is released before
C Trip/Memory cleanup holders, with its existing semantics unchanged.

This capability itself performs only SELECT/row locks, no new state, consent,
history enablement, model call, cleanup dispatch, retry or permission grant. C
owns the deletion scope, user confirmation, association and fences; it must not
infer links by matching manual text or turn metadata into a collection permit.

## Failure and validation

Deferred/non-byte results and output beyond the byte limit are rejected. A C
transaction may already have committed before a size/identity/close/ACK failure:
the caller reconciles the same original C operation and reports UNKNOWN as
appropriate, never recreates its association or automatically repeats a write.
This metadata reader cannot roll back another connection's committed operation.

Actual private PG/signed API probes cover the complete/zero/inactive snapshots,
SQL hash corruption/gaps/bounds, callback/thread/escape/deferred lifetime,
withdrawal/no leaked bytes and unchanged B rows/xmin. A real signed C typed
runtime write commits within the callback while a competing signed MESSAGE
writer waits and resumes only after release. C's #472 old-job/header freeze and
final no-resurrection combination are separately required; this seam alone is
not a PASS for #26 or its physical cleanup. Real accounts/cloud/models/devices/
backups remain outside this local proof.
