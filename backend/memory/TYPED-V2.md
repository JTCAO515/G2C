# MEMORY typed V2 (local runtime only)

C #227 owns this additive contract under JT's 2026-10-30 standing authorization.
This candidate consumes B #273's frozen four contracts and real
MessageContextAuthority, not a client Context/hash/version as permission. Full
OpenAPI/backend-generation publication and final gates follow shared group locks.
V1 inputs, receipts, applied migrations and legacy raw bytes remain unchanged.

## New inputs and projections

`POST /v2/memories` accepts exact original UTF8 JSON, max 32768 bytes, no duplicate
or extra keys, version `MEMORY-manual.2`. Fields are operation_id/item_id/subject/
slot/kind/text/extent/context/occurred_at/version. Server derives scope, source ID,
source version, approval and result. Canonical subject/slot/kind must be explicitly
allowed by the server's bounded collection policy; inference stays candidate.

Long-term requires context null. Current requires exactly
`{kind:"travel", id:<B's 32 lowercase hex ID>, expected_version:<positive int64>}`.
B Selection grammar is reused. Context version is checked at original collection;
it is not the Memory source version and not a permanent memory version. B advance
keeps identity but invalidates old RUN references; later new messages may use the
same still-valid Memory item for that identity. Deactivation is not revival.

`GET /v2/memory-items?item_id=...`, `/v2/memories?limit=...&after=...` (after optional),
and `/v2/memory-receipts?operation_id=...` return `MEMORY-result.2` plus request_id.
Item projection keeps command fields, replacing ambiguous context_id with context:
null for long-term; legacy/id/expected_version:null for old conversation values;
travel/id/expected_version for V2 collection. Source IDs/versions/original language
and approximate time remain visible. A read/receipt is data, never execution rights.
V1 projections cannot silently remove typed scope or reinterpret travel as chat;
legacy-only decoders explicitly refuse new stored commands.

`MEMORY-management.2` uses action_id/operation/item_id/expected_version/
expected_source_version/version. Pause/resume have exactly these fields. Edit adds
text and context (null for long-term, same original travel ID plus current B
expected_version for travel). Edit cannot change subject/slot/kind/extent/context
ID or approximate time. New exact bytes get a new source; disabled stays disabled
and keeps own-pause causality. Current B context may advance, so new input attests
that current version rather than pretending the old source version is B's version.

`POST /v2/memory-management-actions` accepts this typed lifecycle; new
`MEMORY-STOP-USE@2` at `/v2/memory-withdrawal-actions` keeps the existing stop-use
fields plus its new version. Receipt query is
`/v2/memory-management-receipts?action_id=...`. Original action namespace and
byte-exact replay/409 conflict remain shared with the existing ledger. A typed
edit replay only reads the original result even after context invalidation; it
does not renew source or context. Stop-use does not require new collection and
never physically deletes, clears accounts or completes #26.

## One canonical engine and real authority

ContextRef(kind,id) is immutable selection data; same opaque ID with kind legacy
and travel is distinct. None selects no current values. current_context remains
long-term plus the matching current slot override; require_current re-derives that
same selection and source validity under the original scope lock. No second
priority/version/constraint engine or natural-language grouping is added.

Typed save acquires B hold_current's M/T lease before MEMORY, checking the actual
owned active row/version and same principal/scope. Memory source/item/epoch and
original save ledger commit atomically while M/T remains held. First original-ID
lookup releases MEMORY before M/T, so historical replay needs no renewed travel
permission and no inverted lock acquisition. Rollback and lost ACK are distinct
observations; UNKNOWN keeps original bytes/ID and is queried, never auto-resubmitted.

Typed runtime takes context only from B's original accepted message reference,
using hold_for_effect/reference and the same authority instance as the actual
worker. V2 payload is `MEMORY-RUN-CONSUME@2`. Explicit none uses long-term only;
no conversation fallback. Same travel across chats selects the same current
rows, one chat changing travel selects only the newly bound identity. ABA cannot
reactivate an old segment because B checks original selection_epoch. Publication
holds RUN→M→T→MEMORY→NEEDS→USAGE per the actual B graph; canonical Memory currentness
and fresh admission are checked before the real effect/commit, not on caller hash.
Already sent/displayed or previously committed effects cannot be retracted.

## Storage, compatibility and configuration

Migration0021 appends context_kind default legacy and generated nullable
travel_context_id, same-owner FK to public.cj_travel_context(scope,context_id),
RESTRICT deletion. New active slot index includes context_kind. Travel only
permits current; all long-term remains legacy kind, so no duplicate long-term
namespace. Old rows/raw/source/version/epoch/receipts are not rewritten. Existing
FORCE RLS/ACL remain; no new role, DELETE/TRUNCATE, source approval UPDATE or
SECURITY DEFINER. Runtime cannot UPDATE context_kind. Empty up/down/up works;
conservative down refuses any retained Memory business data and preserves it.

Explicit typed_context storage capability defaults false. Old candidate schemas
keep old SQL and strict V1 decoding; V2 repositories know new columns/commands.
This is explicit consumer deployment, not reflection or failed-read fallback.
Only after a compatible consumer is deployed is the typed producer configured.

`local-memory-typed.1` contains collection (the fixed local-memory-policy.1) and
explicit travel_contexts sets for every configured identity. Legacy conversation
allow-lists are not repurposed as travel consent. The collection's per-slot consent,
semantic-resolution decision, scope and deadline remain mandatory; B ownership
alone never approves new text. `local-memory-run.2` contains that typed collection
plus the existing explicit subject/slot/max_bytes selections. Old @1 cannot be
used in upgraded message-travel scopes; missing configuration never turns Memory
off. Local app entry is cj_memory.typed_api.create_local_typed_app; runtime uses
scripts/run_worker.py with explicit typed policy and B travel capability.

## Evidence boundaries

Typed grammar, same-ID type isolation, old decoder refusal, actual signed B/C
APIs, real current leases/runtime PG, scope/FK/immutable kind, original bytes,
rollback/lost ACK, new host readback, pause/edit/resume/stop, actual M2 worker,
same-chat switch/same-travel new-chat/none/ABA, new worker process and in-flight
edit are exercised by typed_pg.py. Invalid projection or policy stays unavailable;
no fixture Context or initialization-role source-state mutation establishes PASS.
NEEDS/PLACE production semantics are separate; all business data/provider replies
are synthetic. Full current-head CI/independent review/merge is required before
closing #227. App/real models/cloud/fees/device remain UNRUN and A/L2/L3-owned.
