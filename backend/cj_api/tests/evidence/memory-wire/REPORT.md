# MEMORY wire author evidence — 2026-10-22

Base main23e12f. Candidate exact head reported after commit; no push/merge/deploy.
Read Issue12 via GitHub gh API after connector returned empty, docs/memory and
fixed producer1ca, AUTH confirmation6a, guarded e3, final identity delta f410.
All code consumes public interfaces; no backend/memory, CJShell, migrations,
RLS/grants, old DB or source approval changes.

PASS eleven scoped wire tests on e3 with actual existing PyJWT/AdmissionChecker/
CJAccessProvider plus actual public MEMORY Service/context and isolated transaction
double. Covers exact UTF8 replay; historical original receipts/null; candidate/
active; source policy and absent approval rejection; list/groups/detail; A/B
partitions and timestamp refresh; original query after lost ACK; precommit denied
rollback; postcommit/final denial with no private bytes; wrong service scope;
output size after commit remains unknown; strict inputs, duplicate JSON/query,
media/limits, generated Python required-null/enum/int64 and explicit configuration.
`wire-tests-e3.txt` contains the actual eleven-test output. Earlier eight-test
interface evidence was narrowed to the changed guard slice, not called real DB.

Final f410 changes only producer same-repository identity comparison. Updated all
runtime hash pins/export; targeted wrong-service test PASS at f410. Other e3
evidence remains applicable. No broad producer or unrelated PR49/59 rerun.

PASS official Swift generator Client actual five operations through a transport
fixture: original body preservation, opaque '+' query encoding, candidate receipt,
receipt/item/page nulls; missing receipt and invalid enum/fallback checks. This is
no network/DB evidence. Warnings are generated unused imports, not test failures.
PASS reproducible official Python/Swift generation (--check), baseline contract
check (all existing accepted23e operations/schemas unchanged), existing foundation
four tests and whitespace diff check. Starlette httpx deprecation warning retained;
no unsolicited replacement dependency installed.

Default/factory source policy, principal scope provisioning and actual source
approval rows are deliberately absent. Tests grant synthetic exact-byte inputs
only inside isolated fixtures, not a product approval/default or real write channel.
No model effective/context publication integration. Actual account/session
revocation, App/manual UI, next-answer/new-chat/trip usage, cleanup/restore,
production role/RLS and complete Issue12 acceptance remain UNRUN.

Real private PostgreSQL + loopback combination is NOT part of this first candidate;
may be added after its fixed head under the granted fresh task-private execution
scope, without reusing retained databases or rerunning PR49/59.

## Manual completion increment (supersedes reference-only POST scope)

Producer9b added exactly nine-key manual input and server-owned explicit
ManualPolicy; final426d337b0647d7770f1716fad83f2e5e724d28e4 adds required receipt
input_sha256 from actual operation-ledger readback and fixes the two real Review
cancellation failures. Prior f410/9b HOLD is not called passed. Current source
pins contain all five runtime files at426d, AUTH f3 unchanged. New fixed candidate
will be reported separately after commit; independent Review/Testing remain UNRUN.

POST path/operationId stay saveMemory /v1/memories, request now manual nine keys;
source/reference fields are server-derived detail only. Old reference save stays
internal, no second public write route. This changes un-frozen144fc70 MEMORY rc
semantics and adds required receipt hash; no compatibility claim for that rc.
Accepted23e operations/schemas remain byte-for-byte definitions unchanged.

PASS fourteen scoped tests on426d for current manual API (new output
manual-wire-tests.txt): real public manual Service/context, synthetic transaction
double, explicit collection allow-list policy, no preseeded sources. First save
creates source/item/operation together; receipt hash equals original manual bytes
and differs from derived Command. Missing/unknown ManualPolicy rejects with no
source/item/operation. Precommit cancellation withholds/rolls back; postcommit final
cancellation returns unknown and original hash remains queryable. Also mixed
MESSAGE+MEMORY app composition shares existing AUTH provider; previous applicable
wire cases exercised using new manual shape. These do not prove actual PG/network.

PASS regenerated official Py/Swift output and generated Client fixture on current
manual/hash definitions; prepared live Swift consumer compiled. Fresh private PG
manual-first/HTTP combination has not yet executed at this source commit. Prepared
runner refuses existing directories, uses only numeric loopback/new Unix socket,
explicit dependency whitelist and verified empty candidate DB, then safe-stops.
Execution requires current task's explicit private-resource authorization; it is
not a startup command or product policy installer.

## Real manual loopback attempt and required Swift date repair

Source9a25e65aaf07a16c76ab1b5dea645ef259702c0d / producer426d. New private
`.local-cj005-memory-pg`, PostgreSQL16.15/cj005m/postgres, Unix55448, TCP disabled,
0700 private directory/socket, explicit fresh pgpass0600, inherited DB settings
rejected. Only fixed candidate schema in verified empty public DB; source table
started with zero rows. No preseeded source. Offline psycopg3.2.10 code/metadata
copy from the previously authorized driver whitelist, 91 files hashed before/after;
no old data/socket/config/log copied or old instance started. Driver Python impl.

Actual first run: seven groups PASS (see loopback-first-result.json): empty/private
identity/schema; first HTTP manual save+ledger original UTF8/hash+exact replay/
modified-byte conflict; unknown collection policy rejection; real source/item/
receipt rollback on fresh AUTH precommit withdrawal; committed original query after
postcommit denial; real COMMIT then injected lost ACK; actual API Unicode C keyset
and separate B partition. Final generated Swift Client group FAIL. Whole attempt
is **FAIL**, not a full combination PASS. HTTP thread and exact PG stopped in
finally; no PID/socket remained, data/failure logs retained. The Swift manual save
may have committed before failure; no blind resend/reuse against that old instance.

No-DB official Client reproduction isolated recorded_at: default Runtime .iso8601
failed a valid fractional timestamp; generated oneOf fallback was nonnull and
correctly rejected. Official fractional transcoder alone fixed that reproduction.
Main explicitly granted only new formal MemoryClientConfiguration.swift; final
helper composes official whole/fractional transcoders, leaves DB microseconds,
OpenAPI date-time, generated sources and old consumer defaults unchanged.

PASS no-DB current generated Client with the formal `Configuration.memory`:
fractional UTC, whole UTC, fractional +08:00 and whole +08:00 produce matching
instants; invalid-date remains invalid nonnull fallback and is explicitly rejected.
Existing five operation/null/input checks preserved. Actual output date-fixture.txt.
Prepared live consumer rebuilt with `.memory`; safe failure diagnostics show fixed
stage/status/decoding class only, no private IDs/body/token/URL/error strings.
A fresh `--swift-only` runner mode will rerun only the affected real Swift segment,
starting from empty sources; earlier Python groups reuse their actual evidence.
No successful post-repair real-loopback claim is made at this commit.
