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

macOS note: Python 3.14 ignores `.pth` files carrying the `hidden` file flag. If imports
such as `cj_api` suddenly fail after `uv sync`, run
`chflags nohidden .venv/lib/python3.*/site-packages/_cj.pth`.
