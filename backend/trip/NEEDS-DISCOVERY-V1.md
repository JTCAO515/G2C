# TRIP-needs-discovery.1 — original NEEDS planning candidate discovery

Additive C local API for #374 / #22 / A #286. This discovers the existing
structured.2 planning candidate produced by needs_local or needs_context. It is
not the scoped edit API and does not implement B's source2 run_once/CLI host.
Existing MESSAGE/RUN/NEEDS, TRIP-needs-result/action and getters remain unchanged.

Explicit factory: the existing `create_local_needs_app` with actual local conninfo,
canonical AUTH, registered run_context and original ConfirmationSigner. New route:

`GET /v1/trip-needs-discovery?message_id=...&run_id=...`

Exactly the original MESSAGE-send.2 receipt's message_id/run_id, never a generated
prefix, worker Outcome, model text/request_id, environment proposal ID or caller
owner. The same C discovery query parser as scoped discovery preserves original
UTF-8 IDs, with2048 bytes per ID and12400 raw query bytes; duplicate/unknown keys,
blank/NUL, malformed percent/UTF-8 encoding refuse. No inference of latest Trip.

## Envelope

`version=TRIP-needs-discovery.1`, original HTTP request_id, and discovery:

| Field | Meaning |
|---|---|
| state | published / not_requested / pending / no_candidate / unknown / unavailable |
| reference | Complete actual MESSAGE-travel-reference.1 for the original receipt |
| run_status, draft_outcome | Original canonical RUN facts; not execution/accept permission |
| needs_reference | Original explicit id/expected_version or null |
| source_profile | TRIP-source-input.1 or .2 for a published candidate; otherwise null |
| planning_context | Captured source2 current Trip id/version/content_sha256, or null |
| proposal | Existing full structured.2 proposal snapshot or null |

Proposal retains the existing C NEEDS getter fields: proposal_id,trip_id,
expected_version,candidate_hash,status,expires_at,content. No raw message/source
bundle, proposed_fields or model reply bytes are exposed. The source2 context
identity is display data, not a pointer selection or mutation grant.

The context Trip and proposed Trip need not share an ID. Frozen planning creates
a new plan with expected_version=0; explicit acceptance creates that new Trip and
selects it, while preserving the old context Trip. Manual save and scoped edit
are the separate same-Trip version-increment paths. The App reads the trip_id in
the original action receipt, never assumes planning overwrites the context ID.

`published` requires the original completed RUN, exactly matching original
trip_proposal effect, immutable C source basis and original needs-run proposal.
The ID is read from that actual association. Manual edits sharing a root run ID
cannot be mistaken for the original planning candidate. Source1 has no planning
context row; source2 retains even an explicit null context. Both are distinguished.

No intent maps to not_requested only without contradictory publication/failure.
An actual queued/running RUN without a candidate is pending. Completed explicit
validation_failed/provider_failed/budget_exhausted is no_candidate. RUN unknown or
provider_unknown stays unknown; failed/cancelled/context_invalid is unavailable
if its original source remains readable. Missing/unreadable/contradictory records
withhold503, never become successful empty/queued guesses. Future unknown result
versions are not silently mapped. Metadata is original history, not fresh source
permission or a claim that current NEEDS still equals that reference.

## Protected read and original action

Lookup derives owner only from canonical admission and verifies the complete
original receipt/binding. Published reads hold the original RUN transaction,
then the actual M/TRAVEL/NEEDS source authority/lease, then the original Trip
scope lock on the same RUN cursor. The retained full source is compared to an
actual canonical capture, including full bounded NEEDS history. Discovery and
acceptance reuse the same adopted-current-Trip CAS helper; changed Trip selection,
manual version/content or NEEDS refuses the old planning candidate. No second
constraint/version engine or source authority is introduced.

Complete private JSON encoding and the existing explicit response cap (default
1,000,000 bytes) precede final source/AUTH guards and strict RUN commit/cleanup.
Read performs no publish/act/effect/put, business DML, model call, meter charge or
new action ID. Unknown cleanup withholds bytes. Old getters remain historical
snapshots; discovery is not a new Memory retrieval or authority to reuse withdrawn
input, nor a promise to recall already-published content. Existing NEEDS planning
publication/acceptance semantics are retained; the stronger scoped-edit Memory
fingerprint contract is not falsely projected onto an old planning basis.

App uses original receipt → this HTTP discovery → original candidate review →
explicit unchanged TRIP-needs-action.1 accept/reject → original action receipt.
Status/hash/expiry are snapshots, not permission. Same action ID/bytes reconcile
before source checks; no automatic new ID or model redispatch. After acceptance
changes current Trip, discovery may conflict while original receipt still recovers.

Missing AUTH401, invalid query400, explicit captured-context conflict409,
dependency/currentness/cleanup/private-output-bound503. All failures withhold
candidate bytes. B source2 official runtime, App native, real providers/models,
fees/cloud/production/device and B360 phase2 are independently UNRUN until delivered.

## Verification boundary

needs_discovery_pg creates actual signed NEEDS/MESSAGE via runtime-role private
PG and original worker/C production publishers. For the discovered candidate,
Outcome is discarded; only original HTTP receipt drives discovery and original
needs-action/readback. Source2 component tests explicitly compose the existing C
context publisher, as its original component tests did; this is not evidence that
the still B-owned source2 official run_once/CLI entry has shipped. No SQL seeds a
Trip, no new capability/DDL/grant is added. Old accepted tests remain unchanged.
