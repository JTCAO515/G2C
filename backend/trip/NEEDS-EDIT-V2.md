# TRIP-needs-edit/save/result.2 — both structured source-bound formats

Appended C interface for #21. Existing TRIP-needs-edit/save/result.1 remains
exact and structured.2-only. No migration, role/permission or frozen content change.
The new service uses the original current NEEDS reader/lease, accepted lineage,
manual preparation, shared constraints/time checks, ConfirmationSigner and act.

Explicit local factory:
`cj_trip.local_place_manual.create_local_place_manual_app(conninfo_path=...,
auth_dir=...,run_context=...,confirmation_signer=...)`.

| Endpoint | Input/output |
|---|---|
| POST /v2/trip-needs-edits | canonical octet-stream TRIP-needs-edit.2 -> preparation |
| GET /v2/trip-needs-edits?request_id=... | original preparation or null |
| POST /v2/trip-needs-saves | canonical octet-stream TRIP-needs-save.2 -> receipt |
| GET /v2/trip-needs-discovery?message_id=...&run_id=... | original source-bound candidate, either structured format |

The edit envelope retains exactly version, needs_reference={id,expected_version},
edit. For actual structured.1 the nested edit is TRIP-manual-edit.1; for actual
structured.2 it is TRIP-manual-edit.2. Cross-format requests refuse rather than
convert/pad times. All original selection/version/hash/protection rules remain.
Save retains exactly version, action_id, proposal_id, candidate_hash. IDs and
bytes are original and immutable; concurrent/version/source changes do not rebase.

The new discovery response is TRIP-needs-discovery.2 with the original
TRIP-needs-discovery.1 fields and guards; it explicitly supports structured.1/2.
Old discovery.1 keeps its structured.2 gate. This does not reclassify source
snapshots as fresh: source_profile still denotes original NEEDS creation/current
Trip context, and historical PLACE snapshots retain their original query times.

Response envelope is TRIP-needs-result.2, request_id and preparation/receipt.
Preparation is proposal_id/trip_id/expected_version/candidate_hash/status/content/
diff. Receipt is original action_id/kind/proposal_id/candidate_hash/trip_id/
committed_version. Original action receipt recovery remains available through
GET /v1/trip-needs-action-receipts on the existing source-bound host. Missing
receipt is not permission to retry with new IDs. Save ACK uncertainty returns
503 with reconcile_original; query the original receipt, never a second writer.

The basis is needs-manual.2 in existing immutable byte tables. Old manual.1
preparation reads withhold this unsupported basis. Old actions are not silently
upgraded; a new-version save must reference its own original preparation.

Bounds/media/query rules follow the existing source-bound host: bounded canonical
body and 1MB complete private output, exact single query for original GET, canonical
AUTH/owner through encoding/return. Missing token401, invalid input400, conflict409,
unknown/revoked/dependency503; no partial success or leaked exception details.

Both formats retain exact source snapshots during title, time, or other-item
edits. Existing text-change provenance clearing remains: no old provider point is
silently attached to new words. Optional missing coordinate is map UNKNOWN, never
default zero or another point. The result is a proposal until the user's exact
save reaches the original Signer/act; no direct Trip writes are added.
