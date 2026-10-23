# CJ-005 actual cleanup progress HTTP/PostgreSQL author integration

Runtime under test: fixed `f87a78a9d8984c59905e385483f17dddd8144d8a`.
No runtime implementation repair was required. The containing commit adds only
this integration runner/client/script, evidence and a current evidence link.
Original f87 FAIL logs and original source report remain unchanged. No full
9 scoped or old foundation suite rerun; those remain f87 evidence.

Fixed dependencies remain AUTH `8b6abb236cf10c1865a9cc8c6155bd8ac732c07e`,
cleanup runtime `514aba717dd0e0a7f7783b6d9072d347cdb0a623` /
producer evidence `6635bb9b301b567edeef91689c0097b25c576ba9`.
`cleanup_progress_pins.json` hashes every imported runtime file. Root actual
combination below is separate from producer and independent acceptance evidence.

## Actual result

PASS 8 integration groups plus safe stop (`live-checks.txt`, `result.json`):

1. New empty task-private PostgreSQL identity and exact source candidate schema;
   Unix socket only, `listen_addresses=''`, port 55455. Runtime `cj005c_read` is
   nonsuperuser/NOBYPASSRLS with SELECT and no INSERT/UPDATE/DELETE. No RLS policy
   or new product authority; canonical scope WHERE is the exercised isolation.
2. Actual numeric loopback HTTP through formal GET/canonical protected reader /
   canonical Repository.query and real PG. Original unknown, missing-hook blocked,
   original in-flight awaiting_revocation, finite frozen-operation complete;
   missing row/original ID unavailable. Refreshed synthetic JWT keeps partition.
3. Same original ID in four accounts and two environments. Account-a/local is
   unknown while account-b/local is blocked and account-a/other-local-fixture is
   complete. Correct current local account never observes the other's progress;
   mismatched trusted environment scope unavailable; caller owner/env forbidden.
   Current denied/unknown access never resolves storage.
4. Actual HTTP response body equals exact full BASE bytes captured from protected
   encoder, including server request_id; whitelist/header/no-store verified.
5. Real PG connection is closed, then controlled close callback revokes synthetic
   invitation or raises close failure. Both withhold all progress with safe 503.
6. After actual PG close, final outer native AUTH fence receives either another
   real canonical verified synthetic identity, or same-principal callback changes
   captured repository connect binding. Both return safe 503 with no progress.
7. Official generated Swift GET with real URLSession/numeric HTTP/PG preserves
   original unknown/revision, pending backup barrier, exact original ID and BASE
   request-id. Redirects disabled; ephemeral session, no cookies/cache/proxy.
8. All five rows' full scope/journal/state bytes and revisions are identical before
   and after. 56 runtime SQL statements are SET/SELECT only, no FOR UPDATE or
   mutations. No recover, hook, delete, logout or permission restoration executed.

AUTH keys, principals, invitation facts, registry/capability metadata and original
receipts are synthetic local fixtures. `core.request/intent/receipt` are used only
to construct original metadata journals; they execute no hook. Real DB-API
connections and real PostgreSQL queries are wrapped only to observe SQL and inject
close/final-boundary faults. Final identity transition calls the actual pinned
PyJWTVerifier on another locally signed token at the last fence; it does not
replace canonical AdmissionChecker or fabricate an ALLOWED decision. The outer
binding swap uses an actual same-principal canonical policy callback. This is
controlled boundary fault injection, not real account logout or remote identity
provider acceptance.

## Isolation, failure and stop

First default sandbox run failed inside initdb's shmget with Operation not
permitted, before any server started. Original failure and initdb logs retained;
failed `.local-cj005-cleanup-pg` was not reused. Tool execution escalation then
permitted a wholly new `.local-cj005-cleanup-pg2`. Its exact data directory, empty
public schema, socket, no TCP and bootstrap role were verified before fixtures.

All ambient PG*/LIBPQ*/DATABASE_URL/CJ_DATABASE_URL variables were removed before
runner invocation. Connection identity is explicit host/socket/port/user/dbname,
empty task passfile and timeouts. No cloud/old data/config/socket/log reads.
Only 91 whitelisted psycopg 3.2.10 code/metadata files were copied from existing
`.local-cj005-history-pg/driver` into the new driver directory; symlinks rejected,
SHA checked before/after both source and copy. Manifest hash/version/count in
result.json, full file manifest retained privately. No installation/lock change.

PASS HTTP thread joined and exact private PG fast-stopped; postmaster.pid and
socket absence asserted, data/logs retained. Initial failure directory never
started. No old PG instance restarted, reused or deleted. Synthetic signed token
settings stay mode 0600 only in excluded private directory, not tracked evidence.
No secrets printed. `runner-manifest.json` records exact executed source hashes.

## Reproduction

Build `UV_OFFLINE=1 ./scripts/build-cleanup-progress-loopback-client.sh`, then run
`backend/cj_api/tests/cleanup_progress_loopback_postgres.py` using the root locked
Python environment after clearing the ambient DB variables above, with explicit
`--auth-repository`, `--cleanup-repository`, `--driver-source`, and a NEW absent
`--private-name .local-cj005-cleanup-<suffix>`. An existing directory is refused;
never rerun using either retained cluster. Shared-memory/loopback sandbox access
may require the same execution escalation. The source-fixed dependency exporter
must receive actual local cj-007-auth/cj-024-cleanup repository paths.

## Remaining evidence boundaries

PASS above is author actual HTTP/PG/Swift integration with synthetic AUTH fixture.
Real isolated account C2, production RLS/auth policy, physical cleanup/hooks,
post-logout credentials, backup/offline/external retention proof, UI/device,
provider/deployment/release and independent Review/Testing/Publish are UNRUN or
Main-owned pending gates. Finite complete fixture never proves universal account
physical deletion. No push/merge/deploy; Issue #5 remains open.
