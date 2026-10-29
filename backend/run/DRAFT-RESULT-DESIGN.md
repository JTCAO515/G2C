# #170 draft outcome — design for review

Status: proposed, not an implemented or frozen contract. JT approved design first,
then implementation after review. Base: 414b0ac9edcd18c95ff154a194a5b69632682a0a.
Sources: #170, #168 comment 6485249974, worker._draft, RUN core/postgres,
contracts/run/DISPLAY-SNAPSHOT.md, current OpenAPI RunDisplaySnapshot and SSE.

## Required behavior

A rejected draft must be distinguishable from an answer failure. Preserve the
answer bytes and its existing completed/partial semantics. A rejection publishes
no TRIP candidate or effect receipt. Results must survive API/worker restart and
remain bound to the original authenticated MESSAGE and RUN. Never infer failure
from proposal_id=None or claim a missing historical event proves no attempt.

This design covers the transferred draft-failure presentation requirement. It does
not claim that #170's budget and NEEDS revision fence boxes are satisfied. Those
need their own actual boundary mapping and evidence; #9 metering remains separate.

## Minimal persisted addition

Add one internal nonterminal event kind `draft_outcome`, with exactly one of:

- `validation_failed`: DraftRejected at the model/publisher boundary.
- `provider_failed`: the draft provider definitively rejected the request.
- `provider_unknown`: the draft provider outcome is unresolved; never auto-retry.

No raw model text, error message, credential, prompt, or stack trace is stored in
this event. Do not reuse text_delta or effect_committed for a failure.

The event is valid only while RUN is running, at most once per original RUN. Its
normal binding, sequence, event ID, exact replay and transaction fence rules apply.
It does not alter RUN status, text, or effects. Reject a second contradictory draft
outcome or a draft publication after a recorded failure; preserve exact replay.
The worker catches each existing draft exception separately and appends its fixed
outcome under the current RUN fence. If cancellation/context invalidation wins
first, do not append a late event; retain the terminal status. If recording the
outcome has an uncertain commit, do not invent completed or retry the provider:
recover the original RUN/event stream under existing unknown handling.

Successful publication keeps the existing trusted trip_proposal effect path.
Do not redesign TRIP publication atomicity or add a second candidate store here.
The failure event is emitted only when no successful publish receipt exists;
storage/commit-unknown exceptions must not be reclassified as validation_failed.

## Migration and rollback

Migration 3 uses backend/run/sql/candidate.sql. That file and migrations 1–12 remain
byte-for-byte unchanged. A new migration, allocated from the latest manifest,
updates only the cj_run_event kind/value CHECK constraints to permit the new kind
and three fixed values. It retains every prior allowed kind and value rule.
No new table, column, RLS policy, role grant, connection binding or transaction scope.

Determine actual existing constraint names from catalog/known creation SQL before
writing the migration; do not guess or drop unrelated constraints. Tests must prove
old rows and old event rules remain valid, invalid new payloads are rejected, and
up/down/up works on a fresh private database.

Old server code rejects unknown kinds on replay. Deployment order is therefore:
stop the local worker; apply the additive constraint migration; start the new
reader/worker together. No mixed old/new server processes on the same database.
The down migration must fail visibly if draft_outcome rows exist; never delete or
rewrite user events to make rollback pass. If rows exist, retain the new reader and
disable new draft-outcome production until a separately reviewed recovery plan.
This is local-only rollout guidance, not production migration authorization.

## Public API: additive version, old reads unchanged

Keep /v1/run-display and /v1/run-events byte/shape semantics unchanged. Add a small
protected read endpoint /v1/run-draft-status?message_id=... with an explicitly
versioned response `RUN-draft-status.1`. Proposed response fields:

- request_id, version;
- conversation_id, generation, message_id, run_id, message_sequence;
- run_status (the existing RUN status enum), event_highwater;
- draft_outcome: not_requested | not_recorded | published | validation_failed |
  provider_failed | provider_unknown.

`not_requested` requires the authenticated original stored MESSAGE creation_intent
not to request a trip. `published` requires the original trusted persisted RUN
trip_proposal receipt, not a caller ID or a search for the newest Trip. Recorded
failure values come only from the new event. Otherwise return `not_recorded`;
this covers old runs and crashes without durable draft outcome. Overall cancelled,
context_invalid or unknown remains independently visible through run_status.
Conflicting/corrupt stored evidence fails closed, not a guessed outcome.

Use the existing MESSAGE-owned with_history_context and original receipt-derived
binding, followed by RUN recovery/integrity validation, within the same protected
callback. Encode and bound the full response before final owner/identity checks.
Never decode/rebuild an already protected envelope after that callback. No caller
scope, second JWT parser, raw input/event value, or direct unscoped repository path.
Apply the existing private/no-store response and explicit size-limit conventions.
Unauthorized, missing, expired or unreadable originals use existing error semantics;
they must not masquerade as not_requested/not_recorded.

This creates a new OpenAPI schema/route and generated types, coordinated as shared
files. It does not mutate the old frozen nine-field schema or old SSE status enum.
The new wire version and samples are reviewed before freezing/implementation.

## A-line child ticket

After the public shape is approved, create an A-line child under #19 referencing
#170 and this version. The App uses the original message ID and current session to
read the new status after the existing answer stream completes (and when reopening
history). It renders a separate bilingual draft status without replacing the answer.

Acceptance: validation_failed is explicit; provider_unknown is not presented as a
safe retry; not_recorded makes no success/failure claim; cancellation remains clear;
account/environment switch discards stale results; no new write/PUT or automatic
retry is enabled. Test delayed old-session responses, offline/unknown reads, native
history reopen, and accessibility. A owns all iOS changes and native evidence.

## Implementation and evidence mapping (all new checks UNRUN)

1. RUN state/replay tests: the three outcomes; invalid payloads; duplicate exact
   replay versus conflicting identity; cancellation/outcome and context/outcome
   interleavings; rejection after terminal; corrupt persisted event fail-closed.
2. Private PG: new migration up/down/up, down refusal with real outcome rows,
   preserved existing event rules/RLS/runtime role, original RUN recovery after
   process reconstruction, no candidate or effect on rejection.
3. Formal local worker/API: valid answer plus invalid draft yields completed answer
   and validation_failed; distinct definite/unknown provider failures; foreign
   account and mid-read revocation reveal no private status; old runs are not_recorded.
4. Compatibility: old display/SSE outputs unchanged; generated positive/negative
   new-wire samples; no changed frozen fixtures or weakened existing assertions.
5. Full scripts/test.py and scripts/pg_suites.py, precise-head CI and independent
   redline review; rebase/review/locked merge; post-merge main CI; A native evidence.

No implementation is approved by this document alone. Review must decide whether
these scope/semantics satisfy JT's approved minimal extension, including the guarded
rollback. Unresolved decisions must be returned explicitly, not silently expanded.
