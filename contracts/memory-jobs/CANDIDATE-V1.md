# MEMORY-CANDIDATE@1 / MEMORY-EXTRACT@1 / MEMORY-EXTRACT-DATA@1

Additive C-owned local runtime contracts for #410. Existing MEMORY command,
history, job and MESSAGE contracts keep their bytes and meaning. The explicit
collection host requires server-owned policies; this contract alone is no worker
registration, Meter exit, source permit or App integration.

## Candidate review API

All endpoints use the original signed admission and current principal's canonical
MESSAGE/Memory scope. No client owner, authorization, source ID or model-provided
confirmation is accepted. Responses finish inside the original protected boundary.
Both independent C hosts consume B's ACCOUNT-ADMISSION@2 public factory. Fresh
retirement checks use the runtime role, without cleanup credentials or an
invitation-only fallback. Committed retirement denies the same token before
physical erasure; unavailable retirement lookup remains UNKNOWN.

`GET /v3/memory-candidates?job_id=...&attempt_id=...` requires a completed original
collection job. The JSON response is
`{version:"MEMORY-CANDIDATE-list@1",request_id,result:{job_id,attempt_id,memory_epoch,candidates}}`.
Each candidate has candidate_id, version, current status, subject, slot, kind,
text, extent, occurred_at, and context. Long-term context is null; current context
is `{kind:"travel",id,expected_version}`. The list projects actual current Memory
rows associated with the original producer. Completed does not mean active;
candidate/withdrawn rows cannot enter effective Memory context.

`POST /v3/memory-candidate-actions` accepts octet-stream UTF8 JSON, at most 32768
bytes, with exactly these confirm fields:

```json
{"version":"MEMORY-CANDIDATE@1","action_id":"review-1","job_id":"job-1","attempt_id":"attempt-1","candidate_id":"history-item-v1:example","expected_candidate_version":1,"expected_memory_epoch":2,"operation":"confirm","kind":"preference","text":"不吃辣 / no spicy food","extent":"long_term","context":null,"occurred_at":"date unknown"}
```

Action/job/attempt IDs preserve exact Unicode, at most 256 characters, no blank or
NUL. Candidate ID is nonblank UTF8, at most 4096 bytes. Versions are non-bool int64
integers at least 1. Text and occurred_at are nonblank, no NUL, at most 4096
characters and 16384 UTF8 bytes. Kind is fact, experience or preference; inference
must be reviewed into a concrete kind. Extent remains the original candidate's
long_term/current range. Current context must name the original travel identity
with its freshly reviewed positive expected_version; the host acquires B's real
current lease before Memory. A stale, retired, other-owner or missing lease fails
closed. Parsing context is not authority.

Reject has exactly the eight base fields through operation, with operation=reject;
it omits kind, text, extent, context and occurred_at. Explicit rejection is allowed
after source expiry, but confirmation needs a live original source. Reject disables
the candidate/source and increments its version and Memory epoch. Nothing is
published for an unreviewed or rejected candidate.

Confirmation CAS checks the actual candidate/version, current Memory epoch and
original producer association. It writes a separate confirmed source, replaces
that candidate's stored value, disables the old source, and advances item version
and Memory epoch. It never overwrites an existing active canonical slot. An active
user correction makes publication/review conflict rather than replace it.

The action response is
`{version:"MEMORY-CANDIDATE-response@1",request_id,result:{version:"MEMORY-CANDIDATE-result@1",action_id,candidate_id,input_sha256,receipt}}`.
Receipt has item_id, version and status=active/rejected. Active additionally has
source_id and source_version. The digest covers exact original action bytes.
Same action ID/bytes returns this original result, even after source/Travel state
changes. Changed bytes conflict. Replaying a receipt cannot reactivate anything.
The original automated publication receipt remains historical candidate data.

`GET /v3/memory-candidate-receipts?action_id=...` returns the same response wrapper
with original result or null. Null does not authorize a new operation or resend.
COMMIT ACK loss and possible postcommit admission loss return 503 UNKNOWN with
reconcile_original. Keep original bytes/IDs and query the original action. Reads
never retry a provider or renew approval. Conflict is 409, invalid grammar 400;
unavailable source/context/storage remains explicit 503. Revoked identity is denied.

## Untrusted extraction data

The internal `prepare_model_input` consumes an original inflight job inside the
current protected source and Memory fence. It returns fully encoded UTF8
`{system,messages}` within B's bounded callback; no context, transaction or lease
escapes. The system instruction is fixed. Exactly one user message contains JSON
data tagged MEMORY-EXTRACT-DATA@1: purpose, finite canonical subjects/slots,
max_entries/max_text_bytes, original source coordinates/versions, actual end
reference or null, and message IDs/sequences/hashes/text. Scope/owner are omitted.
Ending purpose requires B's actual immutable end ID and has a separate cursor.
The explicit data byte bound is at most 262144; overflow rejects without truncation.
The full protected response also remains subject to B's 524288-byte bound.
Completed, unknown, changed-Memory or already-checkpointed jobs cannot prepare a
new input phase. These detached bytes do not authorize dispatch/retry; the actual
registered worker/Meter must reacquire source and fresh admission at its exit.

`MEMORY-EXTRACT@1` is internal model output, never an HTTP save operation. Maximum
UTF8 size is 16384 bytes. It has exactly version and entries; entries are a list
bounded by a server-owned policy (at most 100). Each entry has exactly subject,
slot, kind, text, extent, occurred_at, evidence. Kind additionally permits inference;
extent is long_term/current. Evidence is a nonempty list of exact
`{message_id,quote}` objects, without duplicate message IDs. Every ID must exist in
the protected original batch and every quote must be an exact substring of that
message's text. Quotes/text are bounded by explicit server policy, at most 4096
UTF8 bytes. Unknown fields, duplicate JSON keys and invalid Unicode fail.

Canonical subject/slot and sensitive-content acceptance come from explicit trusted
policy, never the model. The host independently classifies original statements;
inference cannot classify itself as direct. Current context is resolved by the
server's accepted joint lease, never by model JSON or manual-source fallback.
Historical text and model output remain data, with no authority over tools,
identity, consent or source lifecycle.

Same-source identity hashes the original principal scope digest, exact message
revisions, canonical subject/slot/extent and context identity. It excludes output
language, text, quote order, job ID and organization mode. Changed values conflict
on original Memory bytes. Output checkpoint is immutable; publication reparses it
under the fresh original source/Memory fence. Canonical operation, origin mapping,
job completion and cursor advance commit atomically. Output checkpoint survives a
publication conflict for original reconciliation, never automatic provider resend.

## Retention and cleanup

Output bytes, candidate actions and exact origin metadata are registered with
memory-derived and the public CleanupHook in the same PR as the append migration.
They use forced owner RLS and minimal runtime SELECT/INSERT/column UPDATE, without
runtime DELETE or cleanup-role membership. The account hook consumes B's persisted
original CLEANUP@1.1 intent and result in the deletion transaction. Only the opaque
M34 erasure fence survives. Expiry limits use and does not delete user content.
Single-item deletion, source masking and prevention of original-chat re-extraction
remain #26; unsupported memory selection fails closed.

Positive/negative examples are in candidate-v1-examples.json and the candidate
codec tests. publication_pg.py uses actual signed API, restricted PG and supplied
synthetic output; it does not claim the actual worker/Meter path. Automatic current
extraction requires B's combined MESSAGE/Travel lease. Actual producer/Meter and
real model quality remain separate #410–#413 / L2 #32 acceptance.
