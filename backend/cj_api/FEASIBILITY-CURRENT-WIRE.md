# FEASIBILITY-CURRENT-WIRE@0.1.0-rc.1 — candidate CLOSED

Owner CJ-005. Fixed CJ035 `2df1fe0d0a363ee24f3f372405dd2f31f57b3fbb`, NEEDS
`4cc9c815293a4e03225b26adfa228fdd0b50b2e7`, canonical AUTH
`8b6abb236cf10c1865a9cc8c6155bd8ac732c07e`; every imported file is SHA-pinned in
`feasibility_pins.json`. Exporter reads explicit fixed Git blobs only. Imports are
NEEDS-only validator/current read; no solver, route, OR-Tools or provider dependency.

`GET /v1/needs-feasibility?needs_id=<existing ID>` is read-only and requires bearer.
Only this selector is accepted: original NEEDS identifier, ASCII96 maximum.
No owner/environment/snapshots/history/candidate/limit/projector request fields.
No source config returns safe BASE503. Public `create_feasibility_app` always
raises pending-consumer-gate refusal; default root route503. No wire/env/host
switch enables it. Internal candidate dependencies/private app parameter are
local review harness assembly only; independent gates and explicit activation
remain required. Source factory status is not product approval.

## Original byte projection and guards

Use existing canonical AdmissionChecker and trusted resolver
`resolve(principal, environment) -> (stable fresh-connect callable, opaque scope)`.
Issuer/audience/environment and all bounds are trusted host configuration only.
Explicit max_revisions1..128, max_input_bytes/max_report_bytes/max_response_bytes
1..1048576; no production defaults or truncation. The connect callable identity
must remain stable for a binding, and resolver must use supplied host environment.

Each HTTP request receives a fresh canonical ProtectedReadBoundary with the same
checker, then canonical NEEDS ProtectedReader/ReadConfiguration. Root invokes
public `ProtectedReader.read(token, fixed_host_projector)`. Inside that lifetime,
the projector calls the EXACT original `cj_feasibility.current_read.project_current`
with original Operation/ProtectedReadContext, selected needs_id and fixed ReadLimits.
No private tx/state, copied AUTH/history/evaluate algorithm or domain mutation.

The source `CurrentNeedsRead.read` facade settles and returns only raw report bytes;
wrapping BASE after that facade would be too late. Root instead consumes the
owner-documented public ProtectedReader callback seam and its same fixed public
project_current. Validate official generated report model without reserializing
it; embed the original raw bytes literally in `{request_id,evaluation}`. Full BASE
is bounded/validated inside that callback, then NEEDS serialized_return/current
host binding, outer canonical AUTH final admission and callback-free original
field checks settle. The route returns those exact bytes, with request-id/no-store.
No further encoder/provider/IO callback follows producer settlement.

Source reads current Snapshot, exact original revisions, validates history and
evaluates its own rules, then rereads current Snapshot and compares exact version/
bytes/metadata. Report has original needs_id/revision/content_sha256 and source
UTF8/action/revision/input hashes; original projected report bytes are preserved.
This is checked-current read evidence, not a global atomic latest-record promise
across separate transactions, persistent freshness capability or write authority.

## States and errors

Successful response requires nonnull `{request_id,evaluation}`. Original report
version/evaluator_version constants and bounded revision/hashes are explicit.
`status` is CONFLICT or UNKNOWN; `overall` is ALWAYS UNKNOWN. Each original local
check retains PASS/CONFLICT/UNKNOWN/INVALID/NOT_APPLICABLE, bilingual text, missing
paths, detail pairs and declared JSON evidence. Declaration may be any original
JSON value (including null); decimal money text stays text, never float coercion.
Private `sources` retain exact original input UTF8 and its SHA, not reconstructed
input or new approval. No source bytes are logged or persisted by evaluation.

Original Report type can represent INVALID, but the fixed protected-current
projector WITHHOLDS it as ReadWithheld(EVALUATION_INPUT_INVALID). Wire reflects
that with safe BASE503 `FEASIBILITY_INPUT_INVALID`, no fabricated INVALID success
report or private invalid history. Other missing/changed/current/bound/close/read
failures return safe BASE503 `FEASIBILITY_UNAVAILABLE`; never empty/null success.
Malformed selector400, missing bearer401, initial denied401/403 or access unknown503
reuse BASE. Read errors are unknown/retry_safe_read, not a business not-saved proof
or permission to resend an original NEEDS action. No automatic retry is provided.

This endpoint does not accept an uncommitted candidate, call a solver or assess
route/provider truth, create a Trip/Proposal, mint confirmation/write permissions,
or prove real feasibility from local PASS checks. No new authority or data store.

## NEEDS package compatibility and validation

Existing root NEEDS pin remains c821. Domain/init/schema bytes are identical to
4cc9; original Boundary adds only read_only method restriction, Repository adds
strict_close=False default plus opt-in strict close and post-close settlement.
Legacy ordinary-close semantics remain original, including old known failures.
New4cc9 package does NOT satisfy old c821 boundary/postgres file hashes: actual
legacy root factory refuses it. Candidate tests/export use a separate process;
no alias/second NEEDS/hash bypass and NO cohost approval. Later cohost requires
an explicit accepted root pin-upgrade/compatibility gate.

`evidence/feasibility-current-wire/REPORT.md`: five new real-private-PG/in-process
ASGI scoped root cases, official Swift fixture consumer, affected foundation4,
old-definition compatibility and official generation checks. Source's12 and all
solver/old large suites are reused, not repeated. Original af52 two-FAIL evidence
is SHA-identical at2df and remains untouched. New private PG stopped/preserved.

Registry records no new persistence; original NEEDS cleanup/retention/restore
gaps remain. No SQL migration registration, old DB/data/permissions/RLS change,
real account C2, live HTTP/Swift-PG chain, App/UI/RUN/provider, deployment/release
or independent acceptance. Public factory remains hard CLOSED; Issue18/5 open.
