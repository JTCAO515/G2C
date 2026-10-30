# TRIP-initialize.1 / initialize-save.1 / initialize-result.1 — frozen

C-owned additive compatibility entry for the **current** CJ015 canonical title/items
records. It does not migrate old accounts or historical products, alter old wire
versions, automatically initialize a Trip, or invent a new Trip writer. The exact
original record remains in immutable basis/history. App owner A #286 consumes it.

## Explicit input and limits

`TRIP-initialize.1` is canonical UTF8 JSON, at most1,000,000 bytes, exactly
version/request_id/trip_id/expected_version/original_hash/items. IDs and original
version/hash follow TRIP-manual-edit.1. items contains exactly the original ID set,
1–60 unique entries, each exactly id/schedule/fixed. Every start/end date/time/
timezone/utc_offset and fixed Observation must be explicitly supplied under
structured.1 grammar, including unknown/missing. The input cannot replace title,
text, fact evidence, IDs, owner, source or the original order. No device defaults,
text parsing or inferred unlocked set exists. Output order follows the original.

Server reads the actual protected current Trip and validates its old canonical
legacy grammar with the original validator. New shape preserves original title,
IDs, text, verification/evidence; newly introduced source_category=unknown and
source_refs=[] explicitly avoid calling old model text a user declaration or a
verified source. Newly added time/fixed values are the explicit user input.
No false preference or NEEDS record is created. Output remains UNKNOWN without
genuine current NEEDS/route/budget evidence. Explicit reversed time conflicts
produce no Proposal/basis/Trip/receipt.

Scope of compatibility is exact title/items legacy and values within structured.1
bounds. Existing provenance.1 includes distinct source/date-decision semantics;
this version refuses to silently remove/relabel them. Their original reads remain
available; source-bound conversion is separate work with the genuine producer.
Already structured records use the original manual editor; they are not silently
rebased or initialized again.

## One canonical publication and save

Preparation uses the same internal _prepare implementation, source basis table
and original _publish_in_tx; basis_version=manual-initialization.1. Same request ID
and original bytes read the original candidate/diff; changed bytes conflict.
New public methods are OperationContext.prepare_initialization and initialization
(read-only original request ID). No raw Repository or caller owner is exposed.

Explicit `TRIP-initialize-save.1` is canonical UTF8 at most32768 bytes, exactly
version/action_id/proposal_id/candidate_hash. save_initialization reuses _save,
ConfirmationSigner, final DB clock/expiry and sole _act_in_tx. It rechecks the
actual original Trip and exact initialization/basis, then atomically records the
same Trip/version/candidate terminal/receipt/manual intent. This is the user's
one explicit save confirmation, not a client viewed/confirmed Boolean.

No new tables/permissions/migration are needed. Existing0022 immutable basis and
intent accept this additive original input. Original-ID/bytes replay, conflict,
rollback/ACK unknown and same-user private output lifetimes remain unchanged.
After unknown, query the original action; do not send another ID or automatically
retry. Old manual-save.1 refuses initialization candidates rather than adopting
them under the wrong input version.

## Explicit local endpoint

Same opt-in `cj_trip.local_manual_app.create_local_manual_app` canonical host.
Old endpoints/results are unchanged. New endpoints:

| Method/path | Input/query | Result field |
|---|---|---|
| POST /v1/trip-structured-initializations | octet-stream initialize.1 | initialization |
| GET /v1/trip-structured-initializations | request_id | initialization or null |
| POST /v1/trip-structured-initialization-saves | octet-stream initialize-save.1 | receipt |
| GET /v1/trip-structured-initialization-receipts | action_id | original Trip receipt or null |

Top-level version=TRIP-initialize-result.1 and request_id; initialization has the
same preparation/diff/FEAS fields as manual-result.1 but reports its actual new
basis_version above. Receipt is the original Trip action receipt. After commit,
/v3/trip-structured and the existing manual editor read the newly committed
structured.1 version; old readers fail closed on it, not strip its fields.

Positive/negative tests: test_initialization.py; manual_pg.py proves signed API
read from actual CJ015 minimal detail, explicit initialization through original
Proposal/confirmation/act, preserved bytes, current version increase, foreign owner
and wrong-version save refusal, followed by actual original manual editor save.
Fixtures are synthetic and private local PG only. Data/grammar does not grant
source/currentness/RUN permission. NEEDS-bound publication still depends on B305.
