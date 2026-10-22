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
