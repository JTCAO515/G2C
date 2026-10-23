# CJ005 guarded lifecycle wire candidate

Base `e5ff05cd783878116b2ea670d171cf466442affc`; exact executed files recorded in
`executed-input-sha256.json`. New wire version MEMORY-MANAGEMENT-WIRE@0.1.0-rc.1.
CJ019 `a7e706ce44095d43ab0b80c2e75a2bf81927ce76`, canonical MEMORY
`0045e423f004f873e2786aa98b2600b70772a921`, strict canonical AUTH
`8b6abb236cf10c1865a9cc8c6155bd8ac732c07e`, all imported file hashes pinned.
These dependencies' independent gates are pending. Factory unconditionally
CLOSED; no runtime/host/wire gate override is introduced. Internal candidate
assembly/private app arguments are solely the isolated review harness path.
Default new root endpoints503, no deployment/activation or ticket closure.

## Changes and evidence

Adds only pause/resume original UTF8 POST and original-action read-only receipt
GET, explicit bounded host config, restricted guarded context consumer, stored
hash/ID historical receipt projections, OpenAPI/official Python+Swift generation,
candidate SQL ledger registry documentation and targeted validation. No text
edit, new source/approval, automatic retry, candidate promotion, inference
activation or direct unguarded domain route call. Existing AUTH checker/fresh
MemoryBoundary guard is reused. Three small existing dispatch/type/parser helper
extractions preserve old manual-save/read behavior; no copied AUTH state machine.

PASS six new actual private-PG / in-process-ASGI wire methods:

1. Exact whitespace/combining/Chinese UTF8/action ID persisted unchanged; hash
   equals stored original bytes; pause disabled/version2, resume active/version3;
   historical original pause query/replay remains disabled/version2 without
   mutating current active/version3. Changed original whitespace conflicts409.
   ONE real connection for apply+canonical same-transaction stored-receipt check;
   actual ASGI response bytes equal the whole protected BASE encoder output.
2. Other scope and missing original action have required explicit null receipt,
   no replay. Public factory raises pending-gate refusal and default root503.
3. Actual COMMIT succeeds then controlled ACK-loss callback raises: BASE503
   reconcile_original, no receipt/private exception; durable row remains disabled;
   fresh original-ID-only query recovers stored hash. Resume commits then real
   connection-close callback revokes fixture invitation: withheld503; after fresh
   valid binding, original resume action query recovers historical active receipt.
4. Precommit synthetic access change rolls back both action receipt and item
   status/version; outcome stays original reconcile, not false not-saved proof.
   Whole-response cap failure after actual commit withholds success503; original
   query recovers the exact committed receipt under normal cap.
5. Final-return trusted Service repository/scope change after commit withholds
   all receipt bytes503; restoring valid original binding then querying original
   action recovers receipt. Canonical bound repository checks are exercised.
6. Text/owner/approval extras, edit operation, bool/overflow versions and duplicate
   keys reject400 with zero DB connections. Current denied403/unknown503 also
   open no transaction. Caller query owner forbidden; JSON media rejected415.

Actual output in `guarded-pg-wire.txt` / `pg-result.json`: 6 run, 0 failure/error.
Only new root seam cases run; producer12, original19/011 suites and unrelated
9scoped/foundation/e5ff full integration are not repeated or claimed here.

PASS two old426 affected boundary regressions in a SEPARATE process with original
fixed old pin: save/replay/query/private detail, and precommit rollback/postcommit
original recovery. `old426-boundary-2.txt`; old root MEMORY pin remains unchanged.
This is not approval of cohosting0045 and426. Hash verification fails closed if a
host tries to substitute packages. Later activation needs explicit accepted root
old-pin upgrade/compatibility and dependency independent gates.

PASS official Swift CJAPI build + executed generated client fixture transport:
exact pause/resume binary request bodies, original query ID URL encoding,
active/disabled historical receipts, required null; missing/null POST receipt
rejects, malformed nonnull GET fallback is explicitly distinguished from absence.
`generated-swift-consumer.txt`. This transport is synthetic; no real network
request, Swift/PG chain or real account is inferred.

PASS all pre-e5ff schema and operation definitions identical via conservative
`scripts.check_contract.compatible`; current OpenAPI/examples/registry valid.
PASS official generator reproducibility (`generate.sh --check`, exit0).
PASS diff whitespace check. No test failure occurred in this increment. Original
f87/e5ff failures/evidence are preserved byte-identical; no source-owner file edit.

## Private PG provenance and authority limits

New `.local-cj005-mm-pg`, port55456, cj005mm bootstrap role, mode0700 Unix socket,
listen_addresses='' verified from real server along with exact data directory,
empty public schema and zero action rows before fixtures. Ambient PG*/LIBPQ*/
DATABASE_URL/CJ_DATABASE_URL cleared, explicit connection fields/empty passfile/
timeouts. Only original fixed MEMORY and management candidate schemas were
applied to this NEW empty instance; no old/production DB, migration manifest,
role/grant/RLS/security/authority change. Bootstrap role is a test fixture,
not production least-privilege or RLS proof. No TCP/live HTTP listener was opened.

Strict synthetic-key RSA JWTs go through actual canonical PyJWTVerifier and
AdmissionChecker. Approved original source rows and initial save are fixture
setup using the existing source schema/trusted service, not a new producer or
wire source-approval endpoint. Every wire action thereafter invokes only a7
GuardedService.with_operation and restricted ctx.apply/ctx.query; actual canonical
Repository owns commit/rollback, existing lock and same transaction. Controlled
COMMIT/close/policy callbacks inject failures around REAL PG connections.

Only 91 whitelisted psycopg3.2.10 code/metadata files copied from retained driver
code; symlinks refused, source/copy hashes checked before and after. No old data,
config, logs/socket or instance reused. Manifest digest/version/count in result.
No new dependency install/lock changes. PASS exact new PG stopped; pid and socket
absence asserted; data/logs retained. No restart/cleanup/deletion of old clusters.
Test connection config is explicit local metadata in excluded private directory;
no password/API key/token persisted or printed by this new runner.

UNRUN real account C2/remote AUTH/provider, real network HTTP/Swift/PG action flow,
UI/device, text editing/new approved edit provenance, RUN publication, actual
cleanup/backup/restore/retention, deployment/release and production permissions.
Independent Review/Testing/Publish are Main-owned pending gates. Finite fixture
results do not prove full Issue17 or Issue5 acceptance. No push/merge/deploy.

## Reproduction

`prepare-memory-management-deps.py` exports explicit fixed Git inputs only.
Build/run `UV_OFFLINE=1 ./scripts/check-generated-memory-management.sh` for official
fixture consumer. The PG runner is `tests/memory_management_private_postgres.py`:
use root locked Python environment, clear ambient DB settings, provide explicit
--auth-repository, --memory-repository, --management-repository, --driver-source
and a NEW absent --private-name .local-cj005-mm-<suffix>. Existing directories
are refused; never reuse the retained instance. Shared-memory sandbox execution
may need the authorized tool escalation used here. Use synthetic fixture only.
