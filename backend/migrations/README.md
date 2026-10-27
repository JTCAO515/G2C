# Migrations

`manifest.json` is the single ordered migration chain (ADR-0004). Each entry names its
up file, a down file under `down/`, and the sha256 of both; `scripts/migrate.py`
refuses any file whose bytes differ from the manifest.

| Version | Name | Up file |
|---|---|---|
| 1 | foundation | `backend/migrations/0001_foundation.sql` (schema `cj`, ledger `cj.schema_migrations`) |
| 2 | message | `backend/message/sql/candidate.sql` |
| 3 | run | `backend/run/sql/candidate.sql` |
| 4 | usage | `backend/usage/sql/001_candidate.sql` |
| 5 | trip | `backend/trip/sql/candidate.sql` |
| 6 | needs | `backend/needs/sql/candidate.sql` |
| 7 | feedback | `backend/feedback/sql/candidate.sql` |
| 8 | cleanup | `backend/cleanup/sql/candidate.sql` |
| 9 | memory | `backend/memory/schema.sql` |
| 10 | memory_management | `backend/memory_management/schema.sql` (depends on 9) |

Domain SQL stays in each domain directory so tests and the chain use the same bytes.
Changing a registered file requires updating its manifest sha256 in the same PR; once a
version has been applied to any shared database, add a new version instead of editing it.

```bash
uv run --locked python -B scripts/migrate.py verify          # fresh private cluster: up, down to empty, up
uv run --locked python -B scripts/migrate.py up --conninfo-json conn.json
uv run --locked python -B scripts/migrate.py status --conninfo-json conn.json
```

`conn.json` holds explicit psycopg connection keyword arguments; ambient `PG*` variables
are refused. PostgreSQL binaries for `verify` come from `CJ_PG_BINDIR` or `pg_config`.

Known limits (decisions still open, not solved by this chain):

- Domain tables live in schema `public`; moving them into `cj` needs a search_path and
  provisioning decision across all domains.
- No runtime roles, grants or RLS beyond what each domain file already declares
  (USAGE keeps ENABLE/FORCE RLS and PUBLIC revoke; FEEDBACK revokes PUBLIC).
- `down` files drop tables and their data. Use them only on disposable databases; any
  rollback on a database holding user data needs explicit operator approval.
