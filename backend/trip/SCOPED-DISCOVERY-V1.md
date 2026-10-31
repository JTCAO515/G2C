# TRIP-scoped-discovery.1 — original-message candidate discovery

Additive C HTTP version for #366 / A #337. Existing send.4, RUN versions,
TRIP-scoped-result.1, proposal/detail/action/receipt routes and frozen ABIs retain
their semantics. No migration, new role, grant, model exit or Trip writer.

Explicit factory: `cj_trip.local_scoped_app.create_local_scoped_app(database=...,
configuration=...)`, using the actual database/configuration returned by the C
production `cj_draft.scoped_publisher.local_configuration`. It requires the same
canonical AUTH, registered RUN context, real C typed-memory adapter and original
ConfirmationSigner. A DTO, ID, hash, request_id or ready flag is never authority.

## HTTP input and response

GET `/v1/trip-scoped-discovery?message_id=...&run_id=...`. Both values must come
from the original signed MESSAGE-accept.4 receipt. Exactly two query parameters;
UTF-8 nonblank IDs <=2048 bytes each, no NUL, duplicate/unknown keys or malformed
URI percent/UTF-8 encoding. No caller owner, conversation inference, model text,
hidden operator field or `scoped-<run_id>` prefix construction. Decode once and
preserve the original characters; Unicode, spaces and escaped URI punctuation
are supported. The raw query is bounded to12400 bytes before parsing, enough for
both maximum IDs with complete percent escaping.

Response: canonical protected JSON envelope with `version=TRIP-scoped-discovery.1`,
`request_id` and `discovery`. Discovery contains exactly `state`, `reference`,
`run_status`, `draft_outcome`, `proposal`. Reference is the complete original
MESSAGE-edit-reference.1; all original owner/message/run/generation/sequence/hash/
selection/Trip/independent travel namespace/NEEDS association is checked server-side.

| state | Authoritative meaning | proposal |
|---|---|---|
| published | Original completed RUN has the matching sole C candidate and original effect | Original full proposal/diff/report |
| not_requested | Original modification_intent=none, no contradictory effect or draft failure | null |
| pending | Actual queued/running RUN has no candidate yet | null |
| no_candidate | Completed RUN recorded validation_failed/provider_failed/budget_exhausted | null |
| unknown | Original RUN is unknown or recorded provider_unknown | null |
| unavailable | Failed/cancelled/context_invalid original RUN, if its source remains readable | null |

Unknown is never converted to successful absence. Missing/unreadable RUN or
contradictory publication/basis is withheld503, not a guessed queued/empty result.
Source invalidation may also withhold metadata503. Future unknown result versions
are not silently mapped into this old version.

Published `proposal` has the original TRIP-scoped-result.1 proposal shape:
proposal_id/trip_id/expected_version/candidate_hash/status/expires_at/content/scope/
diff/feasibility. Its scope.reference exactly equals discovery.reference. The
published state describes the recorded original candidate, not accept permission;
status/expiry remain visible and the original action path independently checks
fresh eligibility. No new action/confirmation/expiry is issued by this GET.

## Currentness and read-only lifetime

The server resolves the original receipt and reconstructs the canonical binding,
then checks the actual B RUN and immutable C basis. Internal effects are only
server-side consistency evidence; clients never parse them or receive them as an
alternative association contract. No worker Outcome is an App input.

For published candidates, discovery and explicit accept share the same C source
capture/revalidation implementation. A readonly memory bind verifies an existing
scope via SELECT, avoiding the old runtime provisioning INSERT. It captures actual
typed Memory and compares the retained full snapshot/payload/selection fingerprint,
then checks actual original message/namespace/Trip/selection and canonical NEEDS.
No empty or partial Memory fallback, bare Context or caller version permission.

The existing B completed-RUN publication lease supplies RUN→M/TRAVEL→Memory/NEEDS
→Trip locking. C only reads on its cursor: no _publish_in_tx, act, RUN put/effect,
write or meter call. Its before_write method is reused solely as the existing
final source/deadline guard. The actual active lease is reused inside Memory hold,
so capture source_lock=False and publication lock order stay unchanged.
The entire bounded JSON encoding precedes the final guards and original strict
RUN commit/cleanup. AUTH/owner or cleanup uncertainty withholds all private bytes.

Metadata without a candidate likewise retains original RUN and real B source
guards through encoding; it never invents an absent original operation. Responses
use the existing explicit max_response_bytes bound (default4,000,000), fail whole
on overflow, and expose no model_input, raw model stream, retained source envelope
or internal SQL/effect. No model call or usage exposure occurs during reads.

## App chain and recovery

1. Retain original MESSAGE-accept.4 receipt and original bytes.
2. GET this route using its message_id/run_id; verify the full original reference.
3. Show the returned original diff/report and pending candidate, including UNKNOWN.
4. On explicit user accept/reject, use the unchanged TRIP-scoped-action.1 route
   with the exact returned proposal ID/hash and retained original action ID/bytes.
5. Recover only that original action via the unchanged receipt route; do not use
   discovery failure/UNKNOWN as permission to create another ID or rerun a model.

Same source/candidate can be rediscovered after API rebuild or presentation-language
change. Memory edit/withdrawal, namespace/NEEDS/selection/generation/Trip advancement
withholds a newly current candidate; there is no auto-rebase. After acceptance
advances Trip, discovery may be withheld while the original receipt remains
queryable/replayable. Old v1 detail behavior is unchanged; this new route returns
the guarded diff inline so the App does not need an unguarded second detail read.

Missing AUTH401, invalid query/encoding400, currentness/dependency/cleanup/private
output bound503 (unknown/retry_safe_read). The old explicit action route retains
its own conflict/UNKNOWN/reconcile-original behavior. No API error body contains
candidate private data.

## Evidence boundary

scoped_discovery_pg tests use real signed APIs, private runtime-role PG, original
unmodified run_once/Meter/Fake and C production publisher. Setup creates/accepts a
real protected legacy then calls source-initialize HTTP to get the selected formal
Trip; no SQL seeds a Trip and no factory is replaced. For the edited candidate,
worker Outcome is discarded: only the original HTTP message/run association feeds
discovery→diff→original action→same Trip readback. SQL spying checks zero business
DML; usage/model counters stay unchanged. Generation invalidation via private test
administrator is explicitly a negative probe, not a claimed public producer.

This version discovers acceptable original candidates only. B #360/C #336 phase2
clarification/expansion durable non-acceptable results remain separate and UNRUN.
App #337 native behavior and real model/API/fees/cloud/production/device evidence
are not established by the backend suite.
