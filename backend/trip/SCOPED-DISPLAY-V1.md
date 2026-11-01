# TRIP-scoped-display.1 — original clarification/expansion body

C #336, parent #25, consumer A #337. Additive to SCOPED-RUNTIME-V1,
SCOPED-DISCOVERY-V1 and B CJ-MESSAGE-EDIT-PUBLISHER@2 / RESULT@1. Existing
publisher1 and all frozen versions remain. This document describes C production
code; evidence and exact delivery head are recorded in the PR/Issue.

## Explicit local composition and original run

Use `cj_draft.scoped_result_publisher.local_configuration` with the same explicit
arguments as publisher1. It returns the same database plus an actual
`EditResultConfiguration`. Install it on that database before B operator
`cj_api.edit_result_profile.activate`; the current owned independent travel
selection, existing edit activation, actual C344 Memory and NEEDS configuration
are required. There is no environment auto-upgrade, dynamic loader or Memory-off
fallback. The production worker/run_once is B's supported publisher2 runtime.

Non-READY resolve captures the current original Memory/NEEDS and returns
PreparedClarification, without a prompt or model dispatch. A READY reply uses
the original finite edit grammar, manual CAS/protect validators, deterministic
scope explanation and the existing shared FEAS/protect/output_check. In addition
to outside IDs/order/title, the deterministic date projection detects selected
items moved beyond the selected date. This display result does not expose a
ManualCandidate or grant a hash permission. Malformed, fixed or invariant errors
remain DraftRejected/validation_failed; valid in-scope candidates retain the
original Proposal/Signer/act path.

The immutable `cj_trip_scoped_result` row retains original message bytes/hash,
RUN, Trip bytes/version, scope/request, Memory descriptor and NEEDS snapshot,
and deterministic bilingual explanation/report. Expansion retains the original
reply's UTF-8 bytes for recovery verification only; clarification has no model
bytes/report. Neither API nor B history receives these model bytes.

Publication reuses the actual source leases and original RUN cursor. Lock order
is RUN -> MESSAGE/TRAVEL -> Memory -> NEEDS -> Trip UPDATE. All validation and
values precede the final `publication.before_write()` immediately before C INSERT.
B records the separate scoped_result effect and completes the same transaction.
No second commit, Proposal, action, formal Trip change or acceptance shortcut.
Rollback leaves neither body nor effect; uncertain physical ACK reconciles only
the original IDs/bytes and never redrives the model or mints a result ID.

## Protected read

`create_local_scoped_app(database=..., configuration=...)` adds this route only for
the explicit publisher2 configuration:

`GET /v1/trip-scoped-results?result_id=<original B scoped_result.result_id>`

Exactly one bounded formal ASCII ID; authenticated canonical local AUTH. No owner,
language, scope, new intent, hash permission or model input parameter. No POST,
accept/reject link or action is offered for a result. A consumer discovers the
original pointer through B's new versioned status/display/history; it does not
guess ID prefixes. Normal proposal discovery/actions keep their existing API.

Response: `{version:"TRIP-scoped-display.1",request_id,display}`. Display is exactly
`result_id,state,expected_version,current_version,result`.

- `state="current"`: result is exactly `result_id,kind,reference,explanation,feasibility`.
  Kind is clarification_required or expansion_required; reference is the original
  MESSAGE-edit-reference.1; explanation is TRIP-scoped-explanation.1 (original
  selection, resolved IDs, outside IDs/dates, concrete changes, required selection,
  bilingual reasons and UNKNOWN observations). Feasibility is the existing
  report/output_check projection or null for pre-model clarification. Neither a
  required selection nor a reason is a user selection/permission.
- `state="stale"`: the actual owned Trip version differs; result is null. Only
  identity/version metadata is returned, without old explanation, scope, source
  text or reply. It never revalidates an old result as a new candidate.

The default host output limit is 4,000,000 UTF-8 bytes, configurable lower with
the existing explicit `max_response_bytes`; overflow withholds the complete
response. Missing/foreign result, UNKNOWN/corrupt source, withdrawn/corrected/
paused Memory, changed NEEDS/namespace/selection, revoked owner, failed cleanup or
other dependency withholds with 503 TRIP_UNAVAILABLE. Bad query 400, missing token
401. No empty success or partial Memory fallback.

Current content is re-derived from original signed source and existing finite
validators, matched byte-for-byte against the immutable body. The reader uses
strict original RUN transactions and fresh actual Memory capture (no provision),
short `hold_for_effect(source_lock=False)` before waiting for Memory, then current
Memory -> NEEDS -> Trip SHARE. Source refresh takes compatible SHARE; no Trip
UPDATE is held while a second connection refreshes SHARE. Source/Memory/NEEDS and
canonical owner are checked after complete bounded encoding, with leases held
through return/strict cleanup. Reads perform no business DML/model/Meter operation.
Both language reasons are stored once; rebuilding a Chinese or English host
retains the exact original request/results and IDs.

User expansion requires a new explicitly selected send.4 against the current
Trip/version/hash. Only a subsequent normal candidate can use the existing
Signer/act; rejection does not change the Trip. No automatic resend or reuse of
the old selection/hash is provided.

## Retention and scope

Migration 0030 is append-only local runtime only, follows B's 0029, FORCE RLS,
owner-derived Trip scope, SELECT/INSERT only. No new role, DELETE/TRUNCATE,
SECURITY DEFINER or BYPASSRLS. Down rejects any retained result. Table and its
original source/model/explanation bytes are registered in #26/#27 for later
single-memory/account cleanup; this slice stops stale use but does not claim
physical deletion or completion of those lifecycle issues.

Actual private PG/signed API/original worker/Meter/Fake evidence belongs to L1.
App #337, real model/services/fees/cloud/production/device and JT-deferred maps
are not established by this backend contract; preserve UNRUN until owner evidence.
