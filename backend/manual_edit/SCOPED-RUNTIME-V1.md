# C scoped runtime — additive local versions / #336 Part1

Consumes frozen MESSAGE-send.4, message-trip.2 and CJ-MESSAGE-EDIT/MEMORY/PUBLISHER@1.
Old send/profile/API/config versions stay unchanged. No B or iOS implementation edit.

## Actual trusted composition

`cj_draft.scoped_publisher.local_configuration` requires local conninfo/auth_dir,
original registered run_context, C344 EditRuntimeConfiguration, a trusted fresh
credential-for-owner supplier, original ConfirmationSigner, explicit solver/output
verification Limits and language (zh-Hans/en). It returns (database,EditConfiguration).
Pass that configuration unchanged into the original B API and run_once. No module
loader/new model exit, caller owner/intent/ABI, automatic source upgrade or retry.

B accepts only actual modification_intent=propose_scoped_edit with original Trip/
version/hash/day or item IDs, independent travel namespace and explicit current
NEEDS. C cannot manufacture intent from model prose or discussion none.
C344 remains the actual memory implementation; ScopedMemoryConfiguration only
associates its issued capture with the same binding/thread-context for the C
publisher. It never replaces currentness/eligibility or produces permission.

Before model IO C captures canonical NEEDS via the original protected reader and
full history bounds (128/4000000). Scoped Request/resolve and preview are the same
#335 core, with original manual ID/hash/version/fixed/position checks. Unknown or
cross-day date partitions require explicit clarification; selecting item IDs is
not silently substituted for a day choice. The bounded TRIP-scoped-model.1 prompt
asks for original canonical manual-edit.1/.2, never intent/source authority fields.
No SQL lease spans model IO; the original registered B exit/Meter alone calls it.

## Same source checks and independent output

Current actual NEEDS declarations and accepted prior candidate metadata map known
Trip IDs through the same C285 mapped_item helper. Other NEEDS items remain exact.
Unmapped Trip occupancy/person/booking data is explicitly UNKNOWN; no fabricated
Snapshot/Revision, participant, booking state, zero route/cost or new evidence.
Original proposed.evaluate/protect and independent output_check.verify_output are
called with actual candidate data and explicit Limits; unresolved instants/profile
are visible UNKNOWN, substantive invariant rejection is not publishable. Trip time,
fixed/selected and IDs are independently checked by the original #335 chain.
There is no solver invocation or claim of real-world feasibility.

## One publication transaction

B publication opens RUN→MESSAGE/TRAVEL leases. C344's actual Memory hold is active;
C registers original NEEDS RevisionLease, checks actual capture and original Memory
snapshot/payload/selection fingerprint, then publication.lock_trip on the same
scoped cursor. C's sole _publish_in_tx plus immutable source/diff/report basis and
original RUN effect commit together. No independent Trip SHARE/transaction/commit.
Before_write runs sources and the original deadline last. A pending candidate does
not automatically accept or change any formal Trip.

Append local runtime only migration0028: immutable cj_trip_scoped_basis/action,
original MessageReceipt/Proposal/Receipt FKs and owner-derived scope, FORCE RLS,
SELECT/INSERT only. No new role/UPDATE/DELETE/TRUNCATE/BYPASSRLS/SECURITY DEFINER.
Empty up/down supported; retained data refuses down. Applied0001–0027 unchanged.

## Display, explicit action and recovery

Explicit `cj_trip.local_scoped_app.create_local_scoped_app(database=...,
configuration=...)` uses the same actual configuration and canonical AUTH/Trip
protected Operation lifetime, with complete bounded encoding before final admission.

GET `/v1/trip-scoped-proposals?proposal_id=...` returns TRIP-scoped-result.1:
version/request_id/proposal. Proposal contains proposal_id,trip_id,expected_version,
candidate_hash,status,expires_at,content,scope,diff,feasibility. Scope retains the
original reference and scoped request; diff contains exact before/after; feasibility
contains original bilingual checks/missing evidence and output_check. No hash/DTO
or display state is fresh confirmation permission. Response default cap4000000.

POST `/v1/trip-scoped-actions`: canonical immutable UTF8 <=32768 bytes, exact
TRIP-scoped-action.1 fields version/action_id/kind/proposal_id/candidate_hash;
kind accept/reject. This explicit user choice confirms that exact diff once.
Duplicate/unknown fields or changed bytes under the same action ID refuse.

Accept re-enters actual B phase=accept (original completed RUN), captures current
Memory and compares the full original snapshot/payload/context/selection fingerprint,
re-reads original NEEDS and repeats the original candidate validation. Actual source
leases stay held through the same cursor's original Signer/_act_in_tx and receipt.
Only the explicitly selected Trip's version grows; an existing planning pointer for
that Trip is kept consistent without choosing or rewriting another formal plan.
Source/version/selection/account/cancel/namespace changes refuse old acceptance.
Reject is explicit discard via the original Signer/act, not a new source use.

GET `/v1/trip-scoped-action-receipts?action_id=...` reconciles only the original
scoped action, returning receipt or null. Same original bytes reconcile before
current-source checks, including host rebuild and later source changes. Concurrent
source denial re-reads only that original receipt; commit ACK UNKNOWN remains
UNKNOWN/reconcile_original, never automatic write retry/new ID. Rollback preserves
original draft/diff/Trip. Missing token401, invalid input400, explicit CAS409,
dependency/currentness/unknown503; private bytes withheld on lifetime/size failure.

## Explicit remaining interface stop

This Part1 covers valid scoped generation/diff/confirm/read/recovery and safe refusal.
A model expansion/clarification currently becomes only B draft_outcome.validation_failed;
the rejected raw reply/diff/reason is not durable/queryable. #343 comment6543070557
requests an additive protected non-acceptable-preview outcome seam. C does not fake
a trip_proposal effect or bypass a frozen interface to store it. #336 frames2/4 remain
partial until expansion explanation and rejected-draft recovery have actual evidence.
App337 and real providers/models/fees/cloud/production/device remain UNRUN.
