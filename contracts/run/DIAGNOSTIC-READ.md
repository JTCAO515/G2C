# CJ023 consumption seam: internal RUN diagnostic whitelist

Base: 8f2ff45519d1d09f178f1fa766b6829d81bda77a (main). Author branch was clean
and fast-forwarded from 25e8e1b; original source/history and retained clusters
remain preserved. This delta only adds a read/projection and targeted tests.

## Exact callable and result

```python
from cj_run.diagnostics import read_diagnostic, RunDiagnostic
read_diagnostic(repository: Repository, binding: Binding) -> RunDiagnostic
# frozen dataclass fields:
# binding: Binding
# status: str
# event_highwater: int
```

Public Python function, **internal and unauthenticated**. It is not a route or
independently authenticated API. repository and complete original Binding must be
supplied by trusted server composition, never a caller-selected owner/run ID.
`Service.valid` is not a read authorization check and is not repurposed here.

Binding is the original internal tuple of scope, conversation_id, generation,
message_id, run_id, message_sequence. Scope is an internal partition reference,
not an extra identity authority or a proposed public response field. CJ023 must
not serialize this internal dataclass wholesale into a public API without its
own accepted wire projection. Returned data contains no State, text, event values,
effect references, USAGE object, original inputs, digest, attempt or operation.
No external/version/diagnostic fields are synthesized.

status is the observed persisted RUN status: queued/running/completed/failed/
cancelled/context_invalid/unknown. event_highwater is the run's contiguous event
sequence at that read, NOT model version, application version, timestamp, or
state at the earlier instant when a user decided to send feedback. A cancelled
run is a legitimate observed status; cancellation of the read itself is an error.
Model version, actual tool execution status, historical instant and persisted
failure stage are unavailable in this source; consumers must keep them UNKNOWN,
not infer from status, effects, event sequence or synthetic exception stages.

## Required protected composition (MESSAGE fixed seam PENDING)

MESSAGE owner is implementing HistoryReadContext.query_message. That callable's
fixed signature/return has not yet been supplied to this RUN task. No guessed
method is called and no private MESSAGE service/repository is accessed here.

After Main supplies and confirms the fixed interface, server composition must:
1. Enter the MESSAGE-owned protected context under current real AUTH.
2. Get the original persisted receipt through the owner-approved receipt-only
   method. Derive conversation_id/generation/message_id/run_id/message_sequence
   from that receipt (receipt.sequence -> message_sequence).
3. Take scope from that same active trusted context and resolve the RUN repository
   through the server-owned identity/environment mapping. Caller identifiers must
   not select a principal/partition or substitute any receipt field.
4. Call read_diagnostic within that protected lifetime, and fully materialize the
   allowed feedback representation before leaving it. The owner context's final
   identity/ownership guard must succeed before publishing/persisting its result.
   CJ023 must separately respect its write-time guard; this function does not
   make a multi-domain feedback write atomic.

These are composition requirements, not already tested integration. No boolean
`authorized`, parallel principal schema, grant, or new auth callback was added.
Authentic receipt provenance, same-context mapping and final publication guard
remain for MESSAGE/CJ023 fixed-source integration validation.

## Repository and error behavior

The function uses one existing repository.transaction + tx.get(binding), validates
exact State/Binding, supported status and contiguous event references, and builds
RunDiagnostic by explicit allowlist while still inside the transaction. It returns
only after successful transaction exit. It performs no business mutation, no retry
and no nullable-success fallback. Existing PostgreSQL adapter still performs its
scope active guard, full binding match and recovery-expiry checks. Its transaction
uses locks; this is not a promise of SQL READ ONLY mode or lock-free reads.

Conflict, Denied, ResyncRequired, CommitUnknown, I/O errors and BaseException read
cancellation propagate. Unknown new status or corrupt event boundary is resync,
not a guessed valid status. The outer server boundary must map errors using its
accepted BASE contract without leaking private scope/existence or exception data.

## Author evidence and limits

Executed on this delta:

```sh
PYTHONPATH=backend/run python3 -B -m unittest discover -s backend/run/tests -p test_diagnostics.py -v
```

8 tests PASS on local Python 3.9.6:
- Exact three-field result; distinctive private text/receipt/USAGE/raw sentinels
  absent from serialized projection; no invented model/tool/failure-stage fields.
- Same run with changed message/chat/generation/message_sequence/scope rejected.
- Cancelled and unknown RUN statuses remain explicit.
- Missing/expired/denied/I/O/read cancellation never produce null success.
- Exit guard failure, unknown commit and read cancellation withhold projection.
- Foreign/malformed/future status/event-boundary states rejected.
- Existing PG transaction active guard exercised with injected DB-API connection.
- Existing PG get expiry and scope guards exercised with injected DB-API cursor.

No PG source/SQL changed. Prior real-PG evidence is reused only for the unchanged
repository; this new function's direct checks use local fixtures/injected DB-API.
No cluster was started, no actual AUTH/receipt/feedback composition tested, no
provider/network call, and no sharedAPI or MESSAGE/feedback source changed.
Independent Review/Testing and MESSAGE fixed consumer integration remain pending.
