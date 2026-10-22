# CJ015 proposal transaction candidate

Internal implementation only; see [contract](../../contracts/trip/README.md).
No API route, activation config, model/provider call, production migration or RLS.
AUTH boundary consumes the base's existing internal interface; host resolver and
trusted review/confirmation adapter default absent. `Repository.publish` and
`retire` are trusted internal lifecycle operations, never user request endpoints.

## Author validation — 2026-10-22

Base 23e12f28435ab0ddc685d544670564e3fa79db41. Python 3.14.7,
PostgreSQL 17.11 (Homebrew), psycopg 3.2.13; package lock is local to this module.
14 tests PASS on real private PostgreSQL, synthetic candidates/auth/review only.
Separate-process seed → PostgreSQL stop/start → read PASS: original action remains
version 1 while latest Trip is version 2, list/detail same record, other scope absent.
Database stopped after validation; data/logs preserved under ignored private-pg/.
Initial run 11 FAIL / 1 PASS due SQL_ASCII returning bytes: preserved as
`evidence/pytest-initial-failure.txt.gz`. Created explicit UTF8 cj015_test in the same
new private cluster; did not alter old/shared instances or discard failed evidence.

Identity: role cj015_private; DB cj015_test; port 55435;
listen_addresses=''; socket `<this module>/private-pg/socket`.
Tests ran with `env -i` (only PATH/TRIP_TEST_SOCKET supplied), no inherited DSN,
pgpass, credentials or network listener. No superuser/RLS production claim.
Private test role is the isolated cluster bootstrap role only.

To reproduce in a separately authorized fresh private UTF8 PostgreSQL database:
install module dev dependencies via `uv sync --project backend/trip --frozen`,
apply sql/candidate.sql to that empty database with explicit connection parameters,
then set TRIP_TEST_SOCKET to its socket and run the module venv's
`python -m pytest backend/trip/tests -q` from repository root. The harness fixes
role cj015_private/database cj015_test/port 55435 and truncates its four tables;
never point it at a shared database. Existing preserved cluster is stopped, not an
automatically reusable environment. tests/restart_probe.py seed/read are explicit
phases for a real controlled restart, not a mock restart.

## Original Issue20 acceptance mapping

1. Formal record/list/detail durability: DB PASS; two App entrances/reopen UNRUN.
2. Same action/original result and different-input conflict: DB PASS.
3. Missing trusted review/hash mutation/expiry/wrong scope/stale version: DB PASS;
   real display proof and live auth qualification UNRUN, default denies.
4. Commit ACK loss/original action at then-version: DB PASS (injected lost ACK
   after real commit), App recovery UNRUN.
5. Transaction rollback/no partial Trip, pending facts preserved: DB PASS.
6. Rejection/idempotency/accept-reject-expire races/terminal denial: DB PASS;
   generation cancel intentionally has no candidate-rejection side effect.
7. Minimal list/detail from real same table: DB PASS; formal API/App UNRUN.

Review/Testing independent gates PENDING. CJ005 formal API, CJ014 actual candidate,
App review confirmation, real account/auth/RLS/cleanup and full I integration remain
open. No push/PR/merge/closure/deployment performed. Scope serialization is a
correctness-first first slice; no throughput benchmark or atomic auth-revocation
claim. Stored latest Trip has no historical content lookup; original receipt always
retains the committed version and candidate hash and immutable proposal content.

Raw initial failure/initdb logs are losslessly gzip-compressed; no evidence lines rewritten.

## de4e transaction-boundary repair

Independent Review/Testing found autocommit partial writes, expiry after a slow
commit guard, and close errors masking primary outcomes. These findings supersede
any implication that the original 14 positives alone establish the transaction
boundary. [Repair evidence](evidence/repair-de4e/REPORT.md): minimal repository fix,
25 distinct real-PG tests plus original fault probes and actual restart PASS;
new private clusters stopped. Original evidence retained. New independent gates pending.
