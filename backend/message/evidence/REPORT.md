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
