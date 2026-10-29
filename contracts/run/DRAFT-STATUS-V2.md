# RUN-draft-status.2

One new public read version for #170 budget/fence integration. No separate
RUN-budget-status endpoint. GET /v2/run-draft-status selects only original
message_id and current authorization; never run_id, owner/scope or quota account.
Registration/consumer activation belongs to later PRs; contract generation alone
does not activate a working route.

Retain v1 reference fields, run_status and event_highwater. version is exactly
RUN-draft-status.2. draft_outcome retains not_requested/not_recorded/published/
validation_failed/provider_failed/provider_unknown and adds budget_exhausted.
Add required budget_exhausted_stage: none | answer | draft, sourced only from the
original persisted budget_denied reason event, never guessed from failed/unknown.
none means no recorded budget_denied event; null, empty string and missing stage
are invalid. The field is required and nonnullable.
The stage is a historical reason fact; terminal cancellation/unknown remains
visible independently and must never be relabelled as success or safe retry.

Pre-answer definitive rejection is RUN failed plus budget_denied(answer), no
provider call or candidate. Pre-draft rejection preserves the answer and supplies
budget_denied(draft) plus draft_outcome budget_exhausted. No new wire enum is added
to v1, old nine-field display or old SSE. A v1 read unable to represent a newly
persisted outcome returns explicit unavailable/unknown (non-200), not an invented
v1 outcome or truncated successful response. Old representable records retain
exact v1 behavior; not_recorded must not disguise known-but-unsupported outcomes.

Encode bounded private bytes within original MESSAGE authority, derive binding
from receipt, recover/recheck RUN and source before final AUTH return. No caller
scope, separate JWT authority, raw input, ledger/attempt bytes or diagnostic text.
No record/expired/revoked/unknown cannot masquerade as not_requested. All writes,
real models, cloud/production and App editing remain separately gated.
