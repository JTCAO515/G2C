# Protected original-message RUN display snapshot

Base: eeb9b9cdf11ff619494a7afd5cbef2833501df7d. Original eadda/25e source and
history retained; clean branch fast-forwarded to this accepted main before work.
MESSAGE dependency is bf79a948c36a7c5cecf40d840cb9623c2d2e9d7c, whose public
boundary source matches this base. No root pin, API, MESSAGE or UI source changed.

## Fixed source interface

```python
from cj_run.display_snapshot import DisplaySnapshotReader, DisplaySnapshotConfiguration
configuration = DisplaySnapshotConfiguration(max_text_bytes=EXPLICIT, max_response_bytes=EXPLICIT)
reader = DisplaySnapshotReader(message_boundary, resolve_run_repository, configuration=configuration)
body: bytes = reader.read(token, message_id)  # compatible nine-field body
final_body: bytes = reader.read_projected(token, message_id, project)
# project(verified_nine_field_bytes: bytes) -> final_encoded_bytes: bytes
```

`message_boundary` must be the actual fixed `cj_message.auth_boundary.Boundary`.
The trusted host resolver signature is `(trusted_principal, trusted_scope) -> repository`.
It is configured server-side for an approved environment, uses the same stable
identity/environment partition as MESSAGE, and returns a repository exposing the
existing `.scope` and `.recover(binding)` interface. Request inputs cannot supply
a resolver, scope, principal, run ID, permission boolean or repository.

The reader calls the real `Boundary.with_history_context`, then the public
`ctx.query_message(message_id)`. Its original Receipt provides conversation_id,
generation, message_id, run_id and sequence; ctx.scope supplies the internal
partition. receipt.sequence maps to Binding.message_sequence. Original raw input
and receipt hash remain internal and are compared during source rechecks, not
copied into the output. No second JWT decoder or AUTH provider is introduced.

## Exact materialized JSON body

The method returns UTF-8 JSON bytes with exactly these nine fields:

| Field | Source / meaning |
|---|---|
| conversation_id, generation, message_id, run_id | Original receipt references |
| message_sequence | Original receipt sequence, NOT event sequence |
| status | Read-time persisted RUN status |
| event_highwater | Last contiguous persisted event sequence in this snapshot |
| text | Persisted display text, validated against the committed event projection |
| text_state | `complete` only when status is `completed`; otherwise `partial` |

Queued with no text returns the actual empty string, not an invented answer.
Running/failed/cancelled/context_invalid/unknown keep their status and partial-text
semantics; failed/cancelled is never converted to a completed answer. The body has
no scope, principal, raw user message, events/event values, effects, USAGE object,
outbound bytes, attempt/operation/digest, model version, timestamp or failure stage.
A complete display projection does not independently prove model/provider success.

All snapshot shape/integrity validation, text UTF-8 byte bound, allowlist projection,
JSON encoding and final response byte bound occur within the same synchronous
protected callback. Output is already materialized before the MESSAGE final
identity guard. CJ005 must not decode/rebuild/wrap this body outside that guard and
call it the same protected result. If formal wire requires an extra envelope or
request_id, its fixed design must be materialized and size-checked inside the
protected callback through the now-public read_projected seam described below.
This is a source contract for consumption, not an already registered/frozen
OpenAPI endpoint.

## Freshness, failure and recovery

After the trusted resolver returns, the reader rechecks original MESSAGE bytes /
receipt and same captured principal/scope. It reads actual public RUN recover,
validates full Binding, cursor epoch/highwater, status and event projection, then
encodes. A second recover must match the first State and Cursor; original MESSAGE
source and repository scope are checked again before callback return. The owner
Boundary then performs its final same-identity/current-admission guard.

Missing message is SnapshotUnavailable, never a valid null source. Missing RUN,
foreign refs, inactive/expired repositories, corrupt/future state, data/epoch
changes, guard failures, I/O errors, CommitUnknown and read cancellation withhold
all bytes. No failure is converted to empty/successful output and no read retries,
RUN creation, dispatch, cancellation, quota operation or synthetic answer occur.
`SnapshotChanged` and `SnapshotTooLarge` subclass `SnapshotUnavailable`; existing
domain/guard errors propagate. CJ005 maps them to accepted BASE categories without
leaking private references/exception data; this source invents no public codes.

Both byte limits are mandatory positive non-bool integers, with no production
values selected. Exceeding either limit fails; text is never silently truncated.
Limits bound the response, not the database adapter's full-log reconstruction
memory/query work. Public paginated recovery remains a separate source contract.

Status is at a read instant, not a claimed historical moment or guaranteed latest
state at network delivery. Event highwater is not a model version. EOF/connection
closure is not completion. This one-body read is not SSE, a listener or a worker
restart mechanism. Message receipt proves original linkage, not RUN creation.

Existing scope/chat-generation, RUN active/expiry and epoch checks remain enforced;
reads do not bypass prior-message ordering or USAGE claim fences because they never
start work. These sequential domain guards are not a new cross-database transaction
or atomic distributed revocation guarantee. Real account/provider/worker facts,
claim/cancel fencing, protected cursors, dispatcher and cancel ACK semantics remain
outside this slice. The original dispatch prohibition is unchanged.

## Author evidence

`backend/run/evidence/display-snapshot-tests.txt`: 12 groups PASS using actual
fixed AUTH AdmissionChecker, MESSAGE Boundary/query_message, RUN Service/recover
and synthetic verifier/access facts/repositories. Python 3.14.7, local offline
existing runtime; no actual model/account/database/network calls.

Coverage includes queued/running/completed/failed/cancelled/unknown/context_invalid;
exact Unicode display text and refs; private sentinels excluded; foreign identity,
all Binding mismatches, missing message/RUN, old generation, inactive/expired;
resolver and encoding callbacks changing identity/source/epoch/state; final owner
guard failure; corrupt projection; explicit/byte-exact limits; I/O, read cancellation
and unknown transaction exit. The retained original core/USAGE/PG checks are not
rerun: those source implementations are unchanged. Real HTTP/DB/account/worker /
client and independent Review/Testing remain UNRUN/pending for this increment.

```sh
PYTHONPATH=backend/run:backend/message:backend/auth uv run --offline --no-project --with psycopg==3.3.4 python -B backend/run/tests/display_snapshot_checks.py
```

The cached environment includes psycopg but this script opens no database. No
private cluster was restarted, no new resource/table/permission created, no push
or merge performed. Source consumption hashes are in display-snapshot-inputs.json.
Issue11's complete real streaming/stopping/recovery/device acceptance remains open.

## Host envelope projection increment (parent c12a255)

`read_projected(token, message_id, project) -> bytes` preserves the same protected
read lifetime. `read` delegates with an identity projection, preserving its exact
nine-field bytes. The trusted synchronous project receives only those validated
encoded bytes; no State, context, repository, effects or USAGE object is supplied.

CJ005 may decode those bytes INSIDE project, validate its official generated model,
and encode `{request_id, snapshot}` there. request_id must come from the trusted
server trace context. The final HTTP body is the exact returned bytes; do not
decode/re-wrap it after this call. X-Request-ID must match that server trace and
Cache-Control no-store remains the root HTTP adapter's responsibility. This module
imports no root models and does not manufacture request IDs or HTTP headers.

The project function owns its final envelope schema/JSON validation; this generic
seam enforces strict materialized bytes and byte size, not a second copy of the
root schema. Nonbytes (including dict/str/bytearray/memoryview), awaitables and
generators are rejected. A returned coroutine is closed without awaiting it;
deferred results are never iterated/executed. Project exceptions and cancellation
propagate; there is no successful fallback. No trust is granted to request-supplied
project functions: this hook is host code only.

Ordering: verify original snapshot -> bounded nine-field encoding -> project /
final encoding -> strict bytes check -> final max_response_bytes check -> second
RUN recover/state+epoch check -> original source/scope recheck -> MESSAGE final
identity guard -> return final bytes. The read captures its immutable configuration
before callbacks so project cannot enlarge that invocation's limit. Original
max_text_bytes is unchanged; neither body nor envelope is silently truncated.

Evidence: display-projected-tests.txt has 8 targeted groups PASS on Python3.14.7:
normal envelope and legacy byte equality; final-envelope exact/over bound; callback
cannot enlarge captured bounds; invalid/deferred returns; exception/cancellation;
projection changes identity/source/epoch/RUN; nested context refusal and expired
context; final owner guard withholds envelope. display-projected-legacy.txt records
12 prior reader tests PASS after introducing the delegated read path. After the
additional bound-capture hardening only its affected 8-group suite was rerun.
Original unrelated core/PG/USAGE evidence remains reused, not rerun.

```sh
PYTHONPATH=backend/run:backend/message:backend/auth uv run --offline --no-project --with psycopg==3.3.4 python -B backend/run/tests/display_projected_checks.py
```

No PG/Keychain/provider, root API/schema/pins, AUTH policy, tables or dispatcher
changed. Actual generated-model envelope/trace/header integration belongs to
CJ005's fixed consumer validation and is UNRUN here. Independent review pending.
