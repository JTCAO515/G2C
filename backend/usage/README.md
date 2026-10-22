# CJ008 local metering core

Core is stdlib-only Python >=3.12,<3.15 candidate. Tested Python 3.14.7.
See [contract](../../contracts/usage/README.md) for all scope and trust boundaries.

Run from this directory:

```sh
uv run --offline --frozen python -m unittest discover -s tests -v
```

`cj_usage/core.py` supplies value types, mandatory configuration, repository
protocol and transitions. `local_exit.py` only permits injected synthetic execution
and defaults disabled. `tests/test_core.py` owns the nonpersistent transaction fake;
there is deliberately no production in-memory fallback. `sql/001_candidate.sql`
is a module candidate, not a registered migration. `postgres.py` implements the
injected DB-API repository; `codec.py` validates persistent state. Test dependency
`psycopg==3.2.10` reuses `backend/message/tests/pg_requirements.lock`; it is optional
and does not add a default connection or provider.

Author verification: 18 tests PASS, covering absent/invalid configuration, disabled
exit, ID conflict/replay, concurrent budget and one-shot claims, pre-dispatch cancel,
timeout/unknown/late settlement, over-reservation actual receipt, aggregate output,
loop limits, deadline/clock regression, config reset refusal, receipt conflicts,
unknown commit ACK, immutable reads and shared background memory budget.

UNRUN: independent Review/Testing of this increment, product PostgreSQL/RLS,
real AUTH/admission integration, trusted receipt pricing, provider caps/hard timeout,
real external calls, host/API integration, production rollover/cleanup, deployment
and device E2E. No Issue closure, push, PR, merge or release performed here.

## PostgreSQL increment after a6693615

Author evidence: `evidence/repository-unit-tests.txt` records 22 PASS (18 original
core regressions plus 4 codec tests); `evidence/postgres-tests.txt` records 24 PASS
using PostgreSQL 17.11 and psycopg 3.2.10. Covers independent-connection budget and
one-shot claims, cancellation/claim race, cancel release, retained unknown, actual
server restart, late synthetic receipts, rollback, commit ACK faults, cleanup error,
missing scope, corruption and synthetic-role RLS isolation. No real cost receipts.

Opt-in reproduction (creates a NEW private cluster; never accepts an external DSN):

```sh
uv sync --frozen --extra postgres-test
PYTHONPATH=. uv run --offline --frozen --extra postgres-test python tests/pg_probe.py
```

Harness requires `/opt/homebrew/opt/postgresql@17/bin`. It creates a fresh
`/tmp/cj008-pg-*` directory with mode 0700, private socket, empty 0600 pgpass,
explicit socket port 55438, admin `cj008_admin`, database `postgres`; inherited PG
variables are removed. `listen_addresses=''`, host authentication rejects, socket
permissions 0700. Before applying SQL it checks user/database/data directory/socket/
port/no TCP and zero public tables. Test-only roles `cj008_a/b` have no superuser
or BYPASSRLS. Runtime receives no INSERT grant and cannot recreate missing scopes.
Finally stops the server and requires `pg_ctl status` exit 3; data/logs retained.

Final run `/tmp/cj008-pg-tcrp_vfe` stopped with exit 3. Earlier run
`/tmp/cj008-pg-1wnpq4lk` also stopped with exit 3; the final run added cancellation
race/release and actual exposure checks. These are entirely new synthetic clusters,
not existing user databases. Nothing was deployed or connected to Auth/RUN/API.

## SELECT-only original-attempt status increment

Runtime source commit `68763c44fddf2e6d11799d1311dbd497d9c657c9` adds
`read_status()` and a minimal bilingual historical status projection. See
[read contract](../../contracts/usage/READ-STATUS.md). Unlike Meter.query(), it does
not enter the write transaction, bind config, lock rows or change revision.
Mandatory original-authority guard, bounded final projection, read completion and
all cleanup must succeed before any bytes return. No authenticated public facade
is exposed: current AUTH has no owner-confirmed public operation-lifetime context
for independent/background usage. This concrete integration gap is recorded.

Author evidence: `evidence/read-status-unit.txt` has 13 targeted PASS using canonical
AUTH types with synthetic verifier/facts and injected DB faults; no real account.
`evidence/read-status-postgres.txt` has 11 checks PASS against a new private
PostgreSQL 17.11 cluster, runtime SELECT-only with NOSUPERUSER/NOBYPASSRLS, explicit
READ ONLY transaction, no UPDATE/revision change, cross-scope denial, original
unknown status, final projection/close revoke and unknown completion. Prior core,
codec and metering-transaction evidence is reused, not recounted as new execution.

Reproduce from this directory:

```sh
uv run --offline --frozen python -m unittest discover -s tests -p test_read_status.py -v
PYTHONPATH=. uv run --offline --frozen --extra postgres-test python tests/pg_read_probe.py
```

The latter always creates a NEW `/tmp/cj008-read-*` cluster with socket port 55439,
user `cj008_read_admin`, empty pgpass and no ambient DSN, `listen_addresses=''`,
0700 root/socket, host authentication reject. Test-only `cj008_read_a/b` roles and
RLS policy are not production authority. Before SQL it checks identity, directory,
empty public schema, socket/port and disabled TCP. Final run
`/tmp/cj008-read-hyn2mr5a` was stopped with pg_ctl status exit 3; data/logs retained.
No old cluster restarted, no runtime dispatch, no real fee or user-auth acceptance.

A verification invocation from repository root without the documented module
working directory failed to import cj_usage; its original output is retained as
`evidence/read-status-root-invocation-error.txt`. Re-running the documented command
from backend/usage produced the final 13-PASS `read-status-unit.txt`; this was an
invocation-path error, not a product test assertion failure.

## Canonical AUTH protected-status composition

Later consumer source `6f2b552d1b53792dfae88647dcb8ea155319c552` closes the earlier
AUTH public-context source gap using fixed AUTH8b6abb2 ProtectedReadBoundary;
[composition contract](../../contracts/usage/PROTECTED-STATUS.md) has exact bindings.
`protected_status.py` requires actual AUTH read_context imports; only this optional
consumer depends on AUTH, while core/PostgreSQL storage remain standalone.

12 new targeted composition checks PASS in `evidence/protected-status-tests.txt`.
They import exact Git-exported canonical AUTH source and use synthetic facts and DB
callbacks, not real accounts. Original 13 storage/11 private-PG read evidence is
reused; no cluster opened for this composition. Independent gates, real environment
resolver/admission, RLS, formal root API and Issue9/I remain pending/UNRUN. Read
history gives no current budget, source or execution permission.

## Final-binding P2 repair

Outer AUTH's last provider callback previously could change domain scope/config
without changing principal. The status consumer now follows AUTH return with a
pure local captured-binding comparison and directly returns the original bytes;
no additional external callback or new authorization check. Original 2 FAILs kept.
Author 14 affected checks PASS and original Review's 2 assertions PASS against the
repaired fixture; see evidence/final-binding-* and review-final-binding-after.txt.
Independent re-review remains pending. No database/resource operation for this fix.
