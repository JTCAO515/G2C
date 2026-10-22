# CJ023 private feedback candidate

Internal implementation and executable persistence checks for
[FEEDBACK](../../contracts/feedback/README.md). Requires repository Python >=3.12,
verified with cached Python 3.14.7 and psycopg 3.3.4. No root dependency/lock edits.

Run from the repository root (uses only cached packages and a new private PG):

```sh
PYTHONPATH=backend/auth:backend/message:backend/run:backend/feedback uv run --offline --no-project --python 3.14 --with psycopg==3.3.4 python -B backend/feedback/tests/private_pg.py --pg-bin /opt/homebrew/opt/postgresql@16/bin
```

The runner creates a new empty cluster under `backend/feedback/.local/`, a private
Unix socket directory, fresh explicit bootstrap/runtime roles, canonical source fixtures and an empty private
passfile. It removes ambient PG/LIBPQ configuration, uses no DSN, sets
`listen_addresses=''`, and never targets an existing server. It stops the cluster
in `finally`, preserving data, logs and inventory. Change `--pg-bin` only to an
explicitly verified local PostgreSQL installation; do not substitute an old DSN.

`test_domain.py` can run without PostgreSQL. The persistence module intentionally
skips without the runner's injected fresh connection configuration. This is not
production AUTH, production database/RLS, real model, App or independent Testing.

Candidate exports: `Action`, `Receipt`, `Boundary.with_operation`, safe failures.
Optional `Sources` consumes pinned MESSAGE/RUN public reads. Only the host callback sees typed values and emits final encoded bytes; no endpoint
is registered. SQL installs exactly one domain table and no cross-domain access.
See [evidence](evidence/SOURCES-REPORT.md) and [cleanup inventory](../../contracts/feedback/CLEANUP.md).
