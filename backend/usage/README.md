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
