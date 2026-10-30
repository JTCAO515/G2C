# Source-bound Trip editing and subsequent planning

Status: C owner freeze, additive local runtime contracts for #285. Requires the
original B NEEDS@1.0, NEEDS-MANUAL-RUNTIME@1, MESSAGE-send.2 and revision lease,
and C structured.2 / TRIP-NEEDS-SOURCE@1 (#204). Existing versions remain exact.
Only explicit `create_local_needs_app` / `cj_draft.needs_context.publisher`
composition in CJ_ENV=local enables these paths. No real service, device, cloud
activation, or legacy CLI activation is implied. App #286 belongs to A.

## New request versions

All mutation requests are bounded immutable UTF-8 bytes, JSON objects in the
canonical `cj_trip.domain.packed` encoding: exact keys, no duplicate keys,
unknown fields, nonfinite numbers or version fallback. IDs and SHA-256 use the
original Trip validators. Content-Type is application/octet-stream; duplicate
media headers, non-identity encoding and query arguments on writes are refused.

* `TRIP-needs-action.1`: `{version, action_id, kind, proposal_id, candidate_hash}`,
  kind exactly `accept` or `reject`, at most 32768 bytes. POST
  `/v1/trip-needs-actions`. Only an actual source-bound RUN proposal can use it.
* `TRIP-manual-edit.2`: same explicit fields/selection grammar as
  TRIP-manual-edit.1 (`request_id, trip_id, expected_version, original_hash,
  title, changes, order` plus version), validates structured.2 minute or second
  time observations without normalization. It is nested in
  `TRIP-needs-edit.1`: `{version, needs_reference:{id,expected_version}, edit}`.
  Positive explicit NEEDS version required; at most 1000000 bytes. POST
  `/v1/trip-needs-edits` prepares the original diff and pending Proposal, without
  changing a formal Trip. GET the same path with only `request_id` recovers it.
* `TRIP-needs-save.1`: `{version, action_id, proposal_id, candidate_hash}`,
  at most 32768 bytes. POST `/v1/trip-needs-saves`. This explicit save confirms
  that exact pending diff once; no separate confirmation round trip is required.

The old manual-edit.1 entry remains seconds-only and refuses NEEDS-bound Trips.
Neither endpoint converts an old request or silently drops new source fields.
Existing receipt/Proposal identities, expiry and candidate hash rules apply.

## Read and result versions

GET `/v1/trip-needs-action-receipts?action_id=...` reconciles an original action.
GET `/v4/trip-structured?trip_id=...` reads the actual structured.2 record; a
missing visible Trip returns null. GET `/v2/trip-needs-proposals?proposal_id=...`
reads its original Proposal. Each route accepts exactly the single named query.

`TRIP-needs-result.1` has `version`, original HTTP `request_id` and exactly one
result member: `receipt`, `trip`, `proposal` or `preparation`. Receipt fields are
`action_id, kind, proposal_id, candidate_hash, trip_id, committed_version`.
Trip fields are `trip_id, version, content`. Proposal fields are `proposal_id,
trip_id, expected_version, candidate_hash, status, expires_at, content`.
Preparation fields are `proposal_id, trip_id, expected_version, candidate_hash,
status, content, diff`. Nullable results do not grant access or author mutation.
Responses are encoded and size checked inside the original protected operation;
errors reuse BASE@1.0 error envelopes. Missing token=401, invalid input=400,
explicit CAS/selection conflict=409. Dependency/lifetime/uncertain outcome=503;
mutations always instruct reconcile_original, never invent a replacement ID.

## One source, writer and confirmation path

A planning accept re-enters the original RUN, MESSAGE/travel and B NEEDS revision
lease before taking the Trip scope transaction lock. It compares the original
source capture, selected Trip ID/version/content (including an explicit absence),
and original candidate hash. Then ConfirmationSigner and the original
Repository._act_in_tx alone create the receipt/record; the new immutable action
mapping and current-selection pointer commit in that same transaction. Reject
is explicit discard and requires the original action/expiry rules, but does not
require a now-current NEEDS source. Neither operation edits NEEDS or memory.

Manual prepare/save read the current explicit source through B ProtectedReader;
full retained history is bounded at 128 revisions / 4000000 source bytes.
`TRIP-CURRENT-NEEDS@1` retains the original canonical B snapshot/revision bytes.
An issued capture is data until held by the original B readonly shared revision
fence. The original source, fresh canonical admission and selected Trip CAS are
checked before the sole Trip commit. Save rechecks the original diff, Trip
version/hash, source bytes and FEAS/protected scope. A source correction wins
before save => no receipt/Trip change; save wins => the real writer waits until
Trip commit. No lease is held across model IO. Local scope locks serialize
selection and manual commits; selecting a different Trip refuses both a fresh
old-Trip prepare and a previously prepared old-Trip save.

The same original manual selection/fixed validator and FEASIBILITY-PROPOSED@1
are reused. Canonical NEEDS locks cannot be silently unlocked by a Trip edit;
the user must explicitly correct NEEDS first. A Trip-local lock on an originally
unlocked/adopted activity can be explicitly set/cleared, persists in Trip content,
and never rewrites NEEDS. Title/time/text edits preserve every unselected field;
no inferred date, time zone, offset, booking, participants or long-term preference.
Conflicts/invalid checks reject; unavailable evidence stays UNKNOWN.

## Subsequent actual planning

`TRIP-source-input.2` adds `current_trip` (null or `trip_id, version, content,
proposed_fields`) to the existing source-input fields `needs_id, revision,
fields, version`. It is read from the committed current-selection pointer and
its exact accepted Proposal/receipt/source association; no DTO or display flag
is authority. Context is captured before model dispatch and rechecked in the
actual final publication transaction, then retained in the immutable planning
basis, including explicit null. A later accept rechecks it again. An intervening
manual edit or Trip selection therefore cannot be overwritten by old output.

The original model-plan.1 grammar stays exact. Existing locally fixed items
cannot be removed, unlocked or changed by the model. Already adopted model
activities retain their actual prior NEEDS candidate kind, booking state and
participants; they are not treated as newly invented activities. Only genuinely
new IDs require explicit proposed_subjects. Confirmed UTC offsets are retained only when the entire original event is unchanged;
new or changed model observations are refused. FEASIBILITY-TRIP@2.0 reuses the
original explicit-time checker with the structured.2 validator, including observed
offsets, without changing FEASIBILITY-TRIP@1.0. New activities remain intent with
unknown booking/fixed state and unknown evidence. The actual committed Trip
fixed state is kept in Trip content, while FEAS consumes the canonical source
lock and history; neither projection manufactures a NEEDS snapshot/revision.

## Local persistence and recovery

Append-only migration 0025 adds immutable needs action/edit/planning-context
associations and the selected Trip pointer. All four tables FORCE RLS on the
canonical Trip scope; current selection additionally checks the canonical NEEDS
scope. Runtime grants are SELECT/INSERT plus UPDATE(trip_id,trip_version) only
on the pointer. No new role, DELETE, TRUNCATE, BYPASSRLS or SECURITY DEFINER.
Foreign keys retain the original Trip, receipt, proposal and NEEDS identities.
Empty local up/down is supported; any retained row refuses down without deleting
it. Applied migrations are untouched.

Original action IDs/bytes reconcile before current-source checks. Same ID with
different bytes conflicts. Rollback changes no formal Trip/pointer/receipt;
commit ACK or serialization/close uncertainty withholds private bytes and keeps
the original draft and action for receipt lookup, including after a host rebuild.
Historical receipt/preparation reads are not fresh edit permission. There is no
account cleanup, physical user-data delete, autoaccept or second record writer.
