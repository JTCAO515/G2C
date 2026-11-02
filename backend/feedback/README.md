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
# M3 FEEDBACK@1.0 closeout (#15)

The additive stable wire is [FEEDBACK@1.0](../../contracts/feedback/V1.md); rc wire
and old default internal hosts are retained. The local app now configures the
existing submit/original-query routes with the same canonical MESSAGE checker,
actual runtime-role PG, and an explicit v1 scope binder. No request diagnostic or
new Memory/Trip reference type is accepted. The source observation remains historical.

Local migration 0033 provides a nonsecret irreversible scope-digest fence, minimal
runtime SELECT/INSERT and key-column UPDATE solely for its row lock; runtime can
neither retire/unretire nor DELETE. Explicit scope serialization plus an INSERT
trigger rejects late raw writers. `FeedbackHook` validates the original persisted
intent, retires/erases the exact account scope, verifies absence, and records the
original result atomically. Other accounts remain intact. Restore must replay the
retired hash before reads/writes; new IDs never reactivate it.
V1 hosts must configure both the transaction binder and the final current-scope
reader. After full encoding/fresh AUTH, the latter rereads the irreversible fence
before publishing bytes. Retirement during projection withholds an old receipt;
AUTH alone is insufficient. Old rc hosts with neither callback keep old semantics.

[FEEDBACK-LOCATOR@1](../../contracts/feedback/LOCATOR-V1.md) reads actual original
protocol/registration/attempt/input references and current persisted stages/timing.
It copies no transcript/tool payload and invents no external model, rule, fee or
internal provider failure metadata. `diagnostic_at` applies only to new RUN events;
legacy timing is null, and #27 owns 90-day timestamp erasure separate from content
and reconciliation retention. The feedback store itself remains until user deletion.

Test: `scripts/pg_suites.py feedback_runtime` (actual signed API + runtime PG +
original run_once/FakeProvider); full `scripts/test.py` and `scripts/pg_suites.py`
remain the gates. App/native combination belongs to A; real provider/account/cloud,
device and backup acceptance remain #32/#29/#30, not a receipt of this local slice.
