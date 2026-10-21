# CJ009 message-domain.1 author evidence

2026-10-21 / macOS / Python 3.9.6. Local implementation, no database/network execution.
Parent 482c8351c95403df52351e2087272129021a37f8; verified source 7cd587bf1476cbdbbee433068fcc7f8fd79427a8.

PASS: 14 Python tests in tests.txt. Pure domain covers exact-byte duplicate/conflict,
transaction-double rollback when delivery insertion fails, commit ACK unknown and
original-action query, original-run pending replay, input rejection, pagination
creation/data/scope fences, append high-water, holes and stale receipt generation.
Recording DB-API tests cover commit/rollback lifecycle, no automatic unknown retry,
autocommit refusal, parameter binding and query predicates. Two service-to-repository
checks exercise one connection for both inserts and rollback on injected delivery SQL
failure. The doubles do NOT execute SQL in PostgreSQL.

Initial test run had 11 PASS / 1 ERROR: the recording test double returned a scope-row
shape to receipt lookup. Corrected that test's lookup response to None; no production
error handling was weakened. Initial output retained in initial-test-failure.txt.

PASS: Python syntax compilation without pycache, git diff --check, only authorized
new backend/message paths. Original contracts and accepted cursor evidence unchanged.
UNRUN: PostgreSQL SQL parse/application, constraints, true transaction atomicity,
concurrent processes, storage/commit durability, permissions/RLS, full AUTH integration,
RUN worker, external provider, cleanup/TTL, true service/device/CI/deployment.
Pending fixed AUTH gate interface: no production adapter constructed from caller owner.
No independent Review/Testing claimed. Issue #10 remains open; no push/PR/merge.

## AUTH consumer delta from 3cd6b136ef66a517e8eb29fd9c2fc81fc5a6a068

PASS: 6 targeted tests against actual fixed e49ea1a2 AUTH interface/gate using existing
Python 3.14; output auth-consumption-tests.txt. Runner extracts immutable git blobs into
an ephemeral directory; no moving-tree import or copied AUTH types committed. Existing
14 tests reused; domain/postgres/SQL unchanged. Source syntax and diff checks PASS.
Consumer confirmation and concrete runtime/revocation/mapping limitations documented in
../AUTH-CONSUMPTION.md. AUTH RC not frozen; genuine JWT/DB/API/dispatch still UNRUN.

## Runtime documentation correction from dc5352f

Root pyproject requires >=3.12; fixed CJ007 3ffe0559b990dd99b98c1f8a0e2a2751b33bc52a
root requires >=3.12 and backend/auth/pyproject requires >=3.12,<3.15. Read-only metadata
inspection only, not adoption/testing of that AUTH implementation. Current interpreter
readback is Python 3.14.7. Integrated range documented as >=3.12,<3.15; 3.12/3.13 UNRUN.
Prior 3.10+ was a syntax inference, not a support claim; 3.9.6 core results remain
historical evidence. Documentation/requirements comments only; source/tests unchanged,
prior evidence reused, no package install or configuration mutation. Diff check PASS.

## Fixed AUTH repair delta from ba6051a

Current AUTH pin 79f88b6552da1bd3d4b27e22f64a158bddf2853b. Read-only git diff against
e49ea1a2 finds only non-VALID principal validation tightened in imported files;
admission.py/__init__.py unchanged. Message boundary implementation unchanged.
PASS: 2 affected tests on Python 3.14.7, auth-repair-delta.txt. Original six consumer
checks reused with their original provenance, not rerun/relabelled as new execution.
Runtime package declaration >=3.12,<3.15 read from fixed new AUTH head. Other runtime
versions/JWT/DB remain UNRUN. Runner pin and compatibility record updated; no AUTH copy.

## Repository cleanup P2 from f314a0aa79ddc9e95bbb1e7d47963726962a1540

Input: Testing CJ-009-repository/REPORT.md (fixed early 3cd6b13 candidate). On current
unchanged repository code, Python 3.14.7 reproduced 3 errors / 1 pass before repair;
cleanup-before.txt preserves the failure. The apparent credential/SQL text there is
an explicit synthetic test marker, not a real secret or query.

Repair preserves the primary transaction result/exception. Body failure remains the
primary exception even if rollback and both closes fail. CommitUnknown survives both
close failures; commit is attempted once and rollback is not invented after unknown
commit. Successful commit remains successful despite close failure. Both closes are
attempted independently. Secondary failures emit only fixed stage/outcome labels via
cj_message.postgres logger: no exception text, traceback, SQL, scope or credentials.
A failing logging handler is suppressed to protect the primary result; such a handler
cannot guarantee diagnostic delivery, so host logging health remains its responsibility.
A rollback diagnostic does not assert successful rollback; connection discard is still
attempted and no retry is performed by this adapter.

PASS: 6 targeted tests, cleanup-after.txt; includes simultaneous commit/close faults,
body/rollback/close faults, successful commit/rollback, safe diagnostics and logging
handler failure. PASS: 4 related existing adapter lifecycle tests, cleanup-regression.txt.
No full 14-test/contract/AUTH rerun; unchanged evidence reused. Python 3.14.7, DB-API
doubles only; actual PG transaction/resource cleanup remains UNRUN. Diff check PASS.
Current AUTH consumer pin 79f88b65 and prior runtime notes preserved. Independent delta
Review/Testing pending; no claim that P2 is independently closed. No remote/config/URL
changes made in response to repository rename; no push/DB/resource action.

## Real isolated PostgreSQL delta from cec92299

See PG-REPORT.md: actual PostgreSQL16.15 + psycopg3.2.10 in new private Unix-only
cluster; candidate SQL applied only there. Six real transaction/concurrency/paging
checks and post-graceful-restart original-action readback PASS. Final safe stop and
data/log preservation verified. Previous UNRUN entries describe prior candidates;
only this precise local PG scope is newly validated. AUTH/RLS/provider/cloud still
UNRUN. Production source/SQL unchanged; no old unit suites repeated.
