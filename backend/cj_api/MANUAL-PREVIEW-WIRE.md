# MANUAL-PREVIEW-WIRE@0.1.0-rc.1

Base accepted main93687e32375060b2a1e1702e43c6bc23f8d0a351; prior a5f source and
all c02 existing schema/operations preserved. Producer6944a66186800ecd26246ce7028d9c9a8767f810
pure edit/Draft/EditSession and canonical TRIP5fd are fixed by runtime hashes. Root
owns only formal wire/assembly; no manual/Trip algorithm or storage source is changed.

POST /v1/trip-manual-previews (previewManualTripEdit) is a READONLY computation,
using JSON body to carry explicit trip_id, expected_version, original canonical
content bytes as base64, selected_ids, title_selected, nullable title, text_updates,
nullable full order. Every field is required; null title/order means no update.
Input duplicate/extra/invalid Unicode/base64, caller owner/protected_ids/action/
confirmation/proposal/basis/expiry/day/time/lock are rejected. Host body/original/
new-field/response byte limits are mandatory explicit values, not production defaults.
Original content cap cannot exceed existing producer1MB format. No trimming or
normalization substitutes for original bytes; generated scalar wrappers are serialized
to their plain JSON ID values before forming immutable producer tuple arguments.

The ONLY source is actual own formal Trip from public ctx.detail under the existing
TRIP Boundary.with_operation. Client original bytes/version are comparison evidence,
not a server-authenticated historical DTO. Mismatch returns409 BASE; no caller bytes
are made into a fake original Trip or silently rebased. Missing/unknown/unavailable
own read returns503. Client must preserve its original request/local draft on either.
Server does not persist that draft or provide a write receipt/settlement.

Matching first read calls public cj_manual_edit.edit with exact server Trip and client
original bytes, immutable selected IDs/title/text/order. No patch algorithm duplicated.
EditSession.observe reads current source after edit, then complete generated-model
projection/JSON encoding and size checks occur in the same callback, followed by
another public current read. Observed CONFLICT409 or UNKNOWN503 discards the encoded
success, retaining caller's local input. Final existing Trip guard still checks same
identity/configuration/scope. No outer guard, rawDB, private method or new provider.
A later unobserved change remains possible; no distributed/instantaneous freshness or
persistent lock is promised. Each HTTP call is a new readonly calculation; successful
preview does not clear a caller's older sticky session UNKNOWN/CONFLICT or settle any
write. Reconciliation/new base choice belongs to explicit host/UI flow.

Success is only LOCAL preview: exact original Trip/content, canonical after content,
typed documents and source Change(path,before,after) display bytes. Diff is not an
apply-patch wire. Before/after values are canonical JSON-value bytes base64; path is
local title/items-order/items-id display metadata. Unselected objects/index remain
exact; changed text becomes pending with empty evidence, unrelated evidence is not
copied. No-op diff is empty and title-only edits are explicit.

No public Trip protected-state/feasibility source exists, so protected_ids is explicitly
None and protection_status is UNKNOWN, never unlocked or complete checking. There is
no caller protection provider. can_save is always actual EditSession.false, enforced
by formal model false constant. Preview is not feasible/verified/adopted/saved. It
never calls save/to_proposal/ctx.act/publish, creates no Proposal/action/confirmation/
expiry/basis/ledger/Trip/Memory/lock/session row and enables no write endpoint. Existing
manualsave remains unavailable; CJ035/actual confirmation issuer/App/I are not supplied.

Same-app create_trip_composed_app and create_composed_app reuse the exact configured
TRIP boundary/checker/resolver. Standalone create_manual_preview_app uses the existing
strict TRIP factory with default absent confirmation; no new authority/config fallback.
Missing resolver/configuration fails closed. Complete private response bytes are sent
unchanged after with_operation. BASE trace/header/no-store and sanitized errors persist.
413 bounds;400 unsupported input/edit;409 known source conflict;503 unknown/callback/
authority/codec/read cancellation; no preview success on failure and no log of private
input/IDs/exception strings. No auto retry/rebase/new action; client keeps draft.

Official Python/Swift generation uses existing Trip DTOs and date configuration;
no new dependencies/parser or UI code. Registry records only a transient readonly
consumer of existing Trip; no new persistent store or cleanup promise. Actual App,
manual save/lock state, real accounts/services/feasibility and full Issue22 I remain
separate. Checks: check-manual-preview-wire.sh, check-generated-manual-preview.sh,
build-manual-preview-loopback-client.sh, generate.sh --check. Real private PG/HTTP
combination is separately attributed, not inferred from fixtures or producer gates.

Author real combination at c5ffafb passed7 groups including official Swift over
numeric HTTP and canonical private PostgreSQL. Read/preview inventory unchanged;
test-induced concurrent canonical correction is separately labeled. All services
stopped. See tests/evidence/manual-preview/REPORT.md for hashes/layers and remaining
save/UI/protection/feasibility/Issue22 requirements; no production authority follows.
