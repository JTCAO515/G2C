# CJ010 RUN internal core

Core uses the Python standard library. Unit checks ran on Python 3.9.6;
PostgreSQL adapter checks ran on Python 3.14.7 / psycopg 3.3.4 / PG 16.15.
These are observed versions, not a general compatibility promise. Future USAGE
composition must honor its declared >=3.12,<3.15 range. No root lock changes. Execute from repository root:

```sh
PYTHONPATH=backend/run python3 -B -m unittest discover -s backend/run/tests -v
```

`core.py` contains immutable state transitions, pagination and repository protocol.
`fixture.py` is a synthetic process-local transactional adapter, never a production
repository. Reconstructed Service tests reuse memory; they do NOT demonstrate
process restart, disk durability, DBOS execution, database isolation or RLS.

Contract and dependency gates: ../../contracts/run/README.md.
PostgreSQL adapter and candidate SQL are now present; see evidence/REPORT.md.
SQL was applied only to the explicitly authorized task-private empty test cluster,
which is stopped. No existing database or formal migration was touched.

Synthetic RUN→USAGE first-step checks and explicit production blockers are in
[USAGE composition](../../contracts/run/USAGE-COMPOSITION.md). The retained
missing-durable-binding counterexample remains as historical FAIL evidence;
[the association repair](../../contracts/run/USAGE-BINDING.md) now rejects the
replacement attempt. No real dispatcher is enabled.

[Internal diagnostic whitelist](../../contracts/run/DIAGNOSTIC-READ.md) exposes
only original Binding, read-time status and event highwater. It requires the
MESSAGE-owned protected server composition; it is not an authenticated API.

[Protected display snapshot](../../contracts/run/DISPLAY-SNAPSHOT.md) reads by
original message ID inside the actual MESSAGE context and returns bounded
allowlisted JSON bytes. It does not activate an HTTP route or dispatcher.

[Protected original usage reference read](../../contracts/run/ORIGINAL-USAGE-READ.md)
resolves only an original message ID to persisted attempt/operation/run references,
without exposing inputs, querying usage status, or granting dispatch.

## Original-run cancellation (M1 / RUN-CANCEL@1)

The explicit local streaming composition exposes `POST /v1/run-cancellations`.
A display-only composition remains unavailable for this write. The frozen shape
and positive/negative examples are in `contracts/api/openapi.json`:

```json
{"version":"RUN-cancel.1","message_id":"original-message-id"}
```

The body is at most 4096 bytes; the original ID is nonblank, has no NUL and is at
most 256 UTF-8 bytes. Unknown/duplicate fields and query parameters are rejected.
The stable business identity is the current principal + cancel + original MESSAGE
ID; JSON whitespace does not create another cancellation. Caller run IDs and scope
claims are never accepted. The original MESSAGE receipt supplies the entire RUN
binding under the existing owner context. Ownership/source are rechecked inside
the RUN transaction before mutation/commit and after response materialization.

Creating a not-yet-dispatched original RUN and appending cancellation share one
transaction. An existing terminal is returned unchanged. The response contains
only BASE request_id, original message_id/run_id, terminal status and event
highwater. Repeated calls do not append events. A 200 can therefore report an
already completed, failed, unknown or context-invalid run instead of claiming a
new cancellation. Committed text, effect references and candidate records remain
queryable; cancellation does not undo them or settle/refund provider usage.

The worker checks terminal state between stream reads and starts each model call
under the existing RUN scope fence. Draft publication and its RUN effect event
are likewise ordered against cancellation. Once cancellation commits, no later
model call or candidate publication starts; an already-started request can still
settle, but its late output cannot change the terminal. Owned generator streams
are closed when processing stops. `Service.dispatch` remains disabled; this does
not open a generic dispatcher or change the USAGE integration gates.

The first provider advance can hold the RUN fence while that request starts. A
concurrent stop that cannot acquire the existing lock within its configured
budget returns 503/unknown, never a false cancelled acknowledgement. Commit ACK,
cleanup or final-owner uncertainty likewise requires reading the original RUN.
No retry of a model/tool is authorized. Physical provider interruption, real cost
settlement and real-network latency are not established by local FakeProvider
checks.
