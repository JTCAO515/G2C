# CJ005 protected current FEASIBILITY wire candidate

Base `90e4967b3420ef8e50d481a7bb2bcc0d083fb4ff`; fixed inputs in
`feasibility_pins.json`: CJ0352df1fe0 / NEEDS4cc9c815 / AUTH8b6abb2.
Public FEASIBILITY factory hard CLOSED pending independent consumer gates;
default/unconfigured route503. Internal review harness only, no gate override.
No source owner tree edit or producer algorithm change. Executed input SHA in
`executed-input-sha256.json`.

## New implementation and source contract

Adds formal `GET /v1/needs-feasibility?needs_id`, exact source Report schema,
official Python/Swift generation, explicit host history/input/report/final caps,
closed candidate composition and original-byte envelope projection. Canonical
NEEDS ProtectedReader public callback + fixed source project_current execute the
whole BASE inside original lifetime. No private tx/state or repeated evaluator,
NEEDS replay or AUTH implementation. Source CurrentNeedsRead facade would settle
before a later BASE wrapper; root deliberately uses the owner-documented public
producer projector seam, not that unsafe post-facade wrapping approach.

Original source bytes are embedded literally; generated validation never dumps
or reconstructs the report. Complete BASE then passes producer final host/current
binding guards, canonical AUTH final admission and callback-free field checks.
Return Response uses the exact fully encoded bytes. Only NEEDS token/ID are
request-selected; no owner, history, candidate, provider or resource authority.

Report preserves CONFLICT/UNKNOWN, overall ALWAYS UNKNOWN, original checks/states,
bilingual explanations/evidence and original current-content/source-input hashes.
The protected source rejects Report INVALID with its typed ReadWithheld code;
root maps explicit `FEASIBILITY_INPUT_INVALID` BASE503 without a fake/private
INVALID success report. No solver/routes/CP-SAT optional package is imported.
No Trip/Proposal, write/confirmation capability, real feasibility or source truth.

## Actual new verification

PASS five NEW real-private-PG / in-process-ASGI root tests (`root-pg-5.txt`):

1. Real current version2/history yields CONFLICT and overall UNKNOWN; exact
   source projector bytes appear unchanged in the complete HTTP/ASGI BASE body.
   Every stored original UTF8 and SHA preserved, content_sha256 equals actual
   current stored bytes; request-id/no-store match. Full scope/record/revision
   inventories unchanged; runtime SQL only SELECT/SET. Another signed synthetic
   account sees its OWN version1/UNKNOWN rather than A's CONFLICT/version2.
2. History/input/projected-report/whole-BASE caps reject503 without evaluation.
   Missing record unavailable; owner/environment/history/candidate/limit extras400
   open no new connection. Public factory refused and default app503.
3. Deliberately malformed original action association in private fixture history
   yields explicit `FEASIBILITY_INPUT_INVALID`503, no evaluation or private sentinel.
4. Actual first PG close ordinary exception OR resolver scope remap withholds at
   first close (one real connection opened/closed); wire exposes no report.
5. After whole BASE encoding, final outer canonical AUTH callback mutates public
   reader configuration under SAME admitted principal. Producer post-retirement
   comparison rejects all bytes503. Current denied403/unknown503 then open no DB.

First run 5/5, zero failure/error. Original NEEDS scope FOR UPDATE lock is retained
inside canonical read transaction; SELECT-only here does NOT mean a transaction
READ ONLY mode or absence of scope locks. No act/query_action is exposed by this
read-only producer. Write seeding and one intentional corruption are fixture
setup only in new private DB, not wire writes. Source project_current retains
its original final current Snapshot reread/history validation; source12/solver/
old large suites are reused and not independently re-performed here.

PASS official generated Swift CJAPI build + executed FIXTURE transport consumer:
new operation/selector, CONFLICT/UNKNOWN and overall UNKNOWN, original UTF8/hash,
exact decimal declaration text/detail pairs; missing/null evaluation and invented
FEASIBLE overall reject. Fixture only, not network/PG/real account evidence.
`generated-swift-consumer.txt`.

PASS affected foundation4 plus OpenAPI/example/registry checks; conservative
compatible() confirms EVERY90e old schema/operation definition identical.
PASS official generation reproducibility --check. PASS diff whitespace check.
No runtime implementation failure or repair was needed in this increment.

## Original NEEDS compatibility and FAIL preservation

Root legacy `needs_pins.json` remains c821; no other old domain pin upgrade.
Read-only Git comparison: domain/init/candidate SQL exact same bytes c821/4cc9.
Boundary adds read_only method denial only; Repository optional strict_close=False
preserves old accepted path, new opt-in strict behavior belongs to ProtectedReader.
Interface additive is not accepted cohost proof: in the actual4cc9 candidate
process, old root factory rejects c821 hash mismatch before DB. No second NEEDS,
dynamic alias, old consumer reinterpretation or hash bypass. Later cohost needs
explicit pin-upgrade/independent gate. `compatibility.txt` records that refusal.

Original af52 `current-read-seam-fail.txt` equals2df byte-for-byte, SHA256
209fa0d29fd1d3bf2b5fdc26b70a149d7d9145ccbd235b0525e52dc130532fc0.
Those two legacy FAILs are preserved, not repaired/overwritten or hidden. Their
new strict read counterpart now refuses at root first close as above. All earlier
root20aa/82f/90e and original failure evidence remains untouched.

## Private PG and evidence limits

NEW `.local-cj005-feas-pg`, Unix55459, listen_addresses='' verified with exact
new data directory/bootstrap identity/empty public schema. Only fixed NEEDS
candidate SQL applied there. No new table/schema/source code, production/old DB,
registered migration, grants/RLS/permissions change. Bootstrap cj005feas fixture
role is not production least-privilege/RLS proof. Real strict PyJWTVerifier with
synthetic RSA/account facts; explicit approved synthetic NEEDS source content.
No real identity/provider/token resource or native UI/model authority.

All ambient PG*/LIBPQ*/DATABASE_URL/CJ_DATABASE_URL cleared; explicit socket/port/
role/db/empty passfile/timeouts. Copied only91 whitelisted psycopg3.2.10 driver
code/metadata files, no symlinks and source/copy SHA before/after. No old data,
config/log/socket read/reuse/restart; no new package install or lock changes.
PASS exact new PG stopped; pid/socket absence asserted; data/log retained.
No live HTTP listener or Swift-PG connection was run. pg-result.json separates actual
PG/ASGI from synthetic identity/input, fixture Swift and independent acceptance.

Registry only documents read consumer/private original-history output with NO
new persistence; existing NEEDS retention/cleanup/restore limitations unchanged.
UNRUN source/root independent consumer approval, c821/4cc9 cohost, real-account
C2, actual network HTTP/Swift-PG, App/device, RUN/provider/real route or overall
feasibility, production policy/RLS/backup/retention, deploy/release and Issue I.
Public factory remains hard CLOSED; no push/merge/deploy/Issue closure.

Reproduce scoped runner with locked root Python after clearing ambient DB vars,
explicit auth/needs/feasibility Git repos and whitelist driver source, NEW absent
--private-name .local-cj005-feas-<suffix>. Existing dirs refused; no retained PG
restart. Shared-memory execution escalation was used. Official fixture consumer:
`UV_OFFLINE=1 ./scripts/check-generated-feasibility.sh`.
