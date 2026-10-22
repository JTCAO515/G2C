# RUN@1.0 candidate — internal RC1, not frozen wire

CJ010 / Issue 11; base d30cbc5200f8fdaa59558a07984049caa5ba5999.
This candidate implements the accepted RUN scope, not a declaration that RUN@1.0
is frozen. CJ005 owns formal OpenAPI and generation. No public routes/schema,
AUTH principal parsing, durable worker or real provider has been introduced.
The follow-on PostgreSQL repository is described in backend/run/evidence/REPORT.md;
the original core 930236d is preserved in Git; the independent P2 fix is
8a5c81a and does not include the repository increment.

## Internal values and semantics

`backend/run/cj_run/core.py` is the executable type/transition definition.
Binding is immutable: trusted internal scope, conversation_id, generation,
message_id, run_id, message_sequence. MESSAGE creates the IDs and sequence;
RUN never generates a replacement run on delivery/recovery. A trusted adapter
must verify ownership and receipt provenance before accepting this value.
Calling Service directly does not authenticate anyone.

Per-run events have sequence 1..N, event_id, original binding, kind, value.
Exact duplicate returns unchanged state; reuse of ID/sequence with different
content conflicts. Gaps/out-of-order require authoritative snapshot recovery,
not buffering until a guessed completion. The sequence counts all status events.
Unknown kind/version is rejected, not silently treated as success.

Queued -> started -> running; running accepts text_delta/effect_committed.
Completed/failed/cancelled/context_invalid/unknown are single terminal outcomes.
Queued can cancel/fail/invalidate without starting. UNKNOWN means unresolved
execution, never success and never authorization to redispatch. In the fixture,
UNKNOWN also blocks later runs in the chat pending future reconciliation design.
No automatic recovery timeout or made-up final answer exists.

Cancellation is itself a persisted terminal event. Prior partial text and
committed receipt references remain; late output cannot change terminal state.
Partial text is not a completed answer. Effect references here are synthetic;
a production trusted adapter must verify real durable receipts. Late settlement
of already in-flight effects belongs to its authoritative receipt ledger and
must remain queryable there; this RC does not yet project post-terminal receipts.

The validity hook is checked before start, text/effect publication and completion;
only literal True passes. Missing/false/unknown/throwing checks fail closed.
Cancel/failure/invalidation do not require valid context so revocation can stop
work. The production adapter must check current AUTH/account and relevant domain
versions within the write fence, not cache this fixture predicate. Context
invalidation is explicit; a failed hook does not silently fabricate a terminal.

Snapshot returns immutable full state and sequence, including terminal/effects.
An internal Cursor binds the whole binding, external repository epoch, fixed
through and after; pagination never includes events appended after through.
Wrong epoch/identity/range requires resync. PostgreSQL stores the explicitly provisioned epoch and per-run expiry, and
rejects expired recovery. Epoch provisioning/rotation policy, retention cleanup,
public tamper-proof token codec, read authorization and wire mapping remain
unimplemented. Never accept serialized client scope/cursor as authority.
A consumer replaces its projection from an authenticated snapshot and continues
from that sequence; stream EOF alone does not change status.

## Transaction contract and ordering

Repository.transaction must hold scope/chat/run serialization through commit,
atomically bind unique scoped run ID, scoped message ID and chat sequence,
store events + derived state together, rollback failures and acknowledge only
after durable commit. Unknown commit ACK requires original-binding query.
A restarted worker must load original state/attempt receipts, not reconstruct a
new action from text. Full binding equality is mandatory on read and replay.

The memory fixture checks every preceding chat message is present and terminal
(excluding UNKNOWN) before start. This assumes contiguous MESSAGE sequence from
1 for that generation; retention cannot delete predecessors without a separately
verified durable watermark. Missing predecessor fails closed. Different chats
can progress independently. No second scheduler or platform is introduced.

## Consumption record / remaining gates

- MESSAGE source inspected at d30cbc5: `Receipt(message_id, conversation_id,
  generation, sequence, run_id, input_sha256)` and pending outbox. Confirmed
  semantic intent: original run reuse, chat sequence serialization, no dispatch
  authorization from receipt alone. Proposed internal mapping sequence ->
  message_sequence; scope must come from trusted composition. MESSAGE owner
  confirmation and formal adapter are PENDING, no guessed wire fields consumed.
- USAGE source inspected read-only at exact 2520bca6e86f75e54fb969c9f45a81e894561bb0:
  `Command(attempt_id, operation_id, run_id, kind, input_digest, reserve,
  output_limit)`, Meter.reserve/claim/query/cancel/settle. Claim changes reserved
  to unknown exactly once; cancellation only releases unclaimed reservations;
  late original receipt settlement remains allowed. These semantics are compatible
  with immutable RUN terminal and original-ID recovery. No USAGE source copied.
  Integration is PENDING: trusted scope/clock/config, operation/attempt identity,
  precise outbound digest ownership, quota reservation units, run-stop/claim
  atomic fencing, late receipt projection and AUTH/context recheck must be fixed
  with owners. No placeholder amounts, permission booleans or synthetic executor
  are wired into production. Independent USAGE review is still pending.
- Runtime spike discoveries retained: AgentScope 2.0.10 / DBOS 3.3.0 candidate;
  workflow success != business success; persisted intent + absent receipt is
  UNKNOWN; automatic model/tool retries forbidden. Spike modules are not imported.
- Main relayed AUTH semantic confirmation for USAGE2520bca: stable issuer/sub
  plus environment partition, recheck ALLOWED before dispatch, UNKNOWN only
  reconciles original attempt/reservation, late receipt grants no new execution.
  This RC adds no recovery_action wire field. Direct RUN adapter confirmation
  remains pending; these notes do not implement authentication.
- AUTH consumption/worker composition, production repository integration, real receipts and
  API/iOS consumers require fixed owner-confirmed adapters. dispatch raises Denied
  unconditionally, even with enabled/auth/quota kwargs. There is no provider path.

Private inventory: binding, partial output, events and receipt references.
Future cleanup must revoke scope/generation/epoch and invalidate queued workers,
not merely hide UI. Retention duration and physical deletion/backup policy are
not invented; cleanup adapter remains UNRUN. Local PostgreSQL persistence has
limited fixture evidence; production persistence and policy remain UNRUN.

Positive/negative executable samples are `backend/run/tests/test_core.py`.
Independent Review/Testing pending; real model, accounts, workers/DB recovery,
network, device and release UNRUN. Issue 11 stays open.

## USAGE owner follow-up (relayed by Main)

USAGE owner confirmed the pinned semantics above. RUN terminal events currently
do not call Meter.cancel and cannot declare reserved quota released. Future
claim/cancel integration must share a serialization fence. USAGE claim UNKNOWN
is conservative pre-dispatch accounting, distinct from RUN terminal unknown;
started/claim durable ordering and reconciliation must be fixed before connecting
them. A RUN completed/failed event is never a fee receipt; settle accepts only the
original trusted receipt. This repository slice adds no usage ledger or dispatch.
