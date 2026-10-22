# NEEDS-WIRE@0.1.0-rc.1

Fixed producer c821b34d607016c6dbc1020c203621841f1a60e8 on accepted main8f2ff455;
AUTHf3 unchanged. Root contracts/api/openapi.json is the sole formal wire source;
official Python/Swift generation, no handwritten alternate model. All accepted9dc
paths/schemas remain unchanged. NEEDS is current planning input, not formal Trip,
long-term Memory, verified booking, feasible plan or a NEEDS@1.0 freeze.

Four operations: POST /v1/needs-actions (actOnNeeds), GET /v1/needs-action-receipts
(queryNeedsAction), GET /v1/needs (getNeeds), GET /v1/needs-revisions (getNeedsRevision).
Query IDs and historical positive version are explicit. Every route exclusively calls
public Boundary.with_operation and ctx.act/detail/revision/query_action. All output
binding validation, generated projection, byte caps and JSON encoding complete within
the public synchronous lifetime. Only returned bytes leave it; no repository/private
method access, new AUTH provider, credential fallback or scope authority.

POST is the exact original UTF8 JSON NeedsCommand carried as octet-stream. It has
exactly action_id, needs_id, expected_version, source and changes. Source is explicit
manual text, never MESSAGE/RUN/model/owner/approval/verification fields. Duplicate,
extra/nonfinite/invalid-Unicode inputs reject. Maximum131072 bytes plus explicit host
limit. Original bytes are never regenerated/normalized for idempotency.

Original receipt has action_id/needs_id/version/operation=manual_patch. It does not
invent a hash. After query_action returns a receipt, read revision with that exact
needs_id/version, check action_id and compare original_input_utf8_base64 with the
preserved original bytes. The public Revision supplies those actual persisted bytes;
no private ledger read or current-request hash substitution is needed. Latest detail
cannot prove an original action. Required null means not observed, never noncommit
proof or permission to retry/new-key. Original queries remain historical after CAS
corrections. Revision also provides full snapshot bytes and typed fields; no fabricated
per-field source/time is added. Original command may be decoded with generated
NeedsCommand to display its actual source.text and patch.

Fields distinguish absent, explicit missing, unknown, uncertain note and known value.
Nested objects/collections replace entire fields, omitted fields retain old data;
empty collections explicitly clear. Response serialization uses exclude_unset so
absent fields stay absent rather than becoming null/default observations. Required
null envelope keys remain explicitly present. Reference validity is checked in the
resultant record; a companion referenced by retained conditions/items cannot be
removed alone. Snapshot source_kind=user_provided labels provenance, not verification
or a claim that latest source text supplied every retained field.

Money is exact decimal string, not float/arithmetic. Local date/time are strings,
never generated Date/instants or device-zone conversions. Explicit event timezone
is not copied from destination/overseas timezone. Ambiguous DST wall times stay as
reported; solver requirements remain CJ035. Fixed booking and locked intent remain
user-provided; no verified orders, automatic relaxation or long-term promotion.
Schema limits mirror defensive producer encoding bounds, not approved travel limits.

create_needs_composed_app requires explicit local strict JWTConfiguration/keys,
existing unique CJAccessProvider, trusted principal/environment→connection/scope
resolver and NeedsWireConfiguration. Existing create_composed_app accepts the same
optional NEEDS injection. Missing resolver/config fails closed. No public scope
provisioning or production write configuration exists; candidate SQL is unregistered.

BASE mapping: no bearer401; invalid raw/grammar/resultant reference400; media415;
input/private-read cap413; original-input/CAS conflict409. Producer Denied conflates
unknown/denied AUTH and unavailable binding/scope, so generic503 access unknown
without guessing cause or disclosing private content. Commit/ACK/cancellation or
postcommit projection failure is503 unknown/reconcile_original; read errors are
unavailable, not fabricated empty values. No auto resend or latest-value inference.
No query/body/token/ID/exception text logging. Request-ID/no-store semantics unchanged.

Official Swift Client uses existing Configuration.memory (no new date parser). Its
oneOf null fallback must have value==nil; nonnull fallback is invalid. Typed local
wall time/money stay String, and optional fields remain distinguishable from explicit
observation enums. User App/model/source extraction/CJ035/Issue14 full I acceptance,
production permissions, cleanup/retention/restore are not supplied by this slice.

Checks: scripts/check-needs-wire.sh AUTH_GIT_REPOSITORY NEEDS_GIT_REPOSITORY;
scripts/generate.sh --check; scripts/check-generated-needs.sh;
scripts/build-needs-loopback-client.sh. Scoped wire positive cases are explicitly
public-seam fixtures, while denied/unknown AUTH uses the actual verifier/provider.
Fresh private PG/HTTP runner is separate author evidence and must never reuse an old
cluster. Registry1.4 records all three private stores; no migration apply/RLS/cloud.

Author real combination passed9 groups at b22c690 on a new private PG/HTTP instance,
including official Swift4ops and original-byte recovery; services stopped. The first
runner startup failure is retained in evidence and does not affect production source.
See tests/evidence/needs-wire/REPORT.md for exact layer and remaining product limits.
