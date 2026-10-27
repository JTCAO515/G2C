# Backend

One Python distribution (`cj`, root `pyproject.toml` + `uv.lock`). Each domain keeps its
import name (`cj_auth`, `cj_message`, `cj_run`, ...); `backend/cj_api` composes them by
plain import — the Git commit is the pin (ADR-0004).

| Entry | Purpose |
|---|---|
| `uv sync --locked` | Install everything, editable; no `PYTHONPATH` needed |
| `uv run --locked python -B scripts/test.py` | All non-database suites and check scripts |
| `uv run --locked python -B scripts/pg_suites.py [GROUP ...]` | PostgreSQL suites on fresh private Unix-socket clusters |
| `uv run --locked python -B scripts/migrate.py verify` | Migration chain up → down → up ([migrations](migrations/README.md)) |
| `scripts/check.sh` | Both of the above, as CI runs them |

PostgreSQL binaries: `CJ_PG_BINDIR` (else `pg_config --bindir`); suites that need a
specific major read `CJ_PG16_BINDIR` / `CJ_PG17_BINDIR`.

Per-feature run instructions in older `*-WIRE.md`, `*VALIDATION.md` and domain READMEs
(per-module `uv sync --project ...`, `check-*-wire.sh`, git-export or `--auth-repository`
arguments, Homebrew-only paths) predate ADR-0004 and are superseded by the entries above.
Their evidence is archived at tag `evidence-archive-2026-10-27` ([docs/evidence.md](../docs/evidence.md)).

## Local walking skeleton (P2a)

```bash
export CJ_ENV=local
uv run --locked python -B scripts/dev_auth.py init .local/dev-auth --invite alice
uv run --locked python -B scripts/migrate.py up --conninfo-json .local/conn.json   # your own empty local DB
CJ_LOCAL_CONNINFO=.local/conn.json CJ_LOCAL_AUTH_DIR=.local/dev-auth \
  uv run --locked uvicorn cj_api.local_app:app_from_environment --factory --host 127.0.0.1 --port 8765
uv run --locked python -B scripts/run_worker.py --conninfo-json .local/conn.json          # FakeProvider; --real needs a key
TOKEN=$(uv run --locked python -B scripts/dev_auth.py token .local/dev-auth --subject alice)
```

Flow: `PUT /v1/conversations?conversation_id=c1` → `POST /v1/messages` (application/octet-stream,
MESSAGE-draft.1 JSON) → worker answers → `GET /v1/run-events?message_id=...` streams the answer.
`conn.json` holds psycopg keyword arguments for a database you created; nothing here creates one.
`scripts/pg_suites.py e2e` runs the same flow automatically on a fresh private cluster.

macOS note: Python 3.14 ignores `.pth` files carrying the `hidden` file flag. If imports
such as `cj_api` suddenly fail after `uv sync`, run
`chflags nohidden .venv/lib/python3.*/site-packages/_cj.pth`.
