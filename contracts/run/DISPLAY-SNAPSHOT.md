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
body: bytes = reader.read(token, message_id)
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
protected callback in a subsequent accepted interface change. This is a source
contract for consumption, not an already registered/frozen OpenAPI endpoint.

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
