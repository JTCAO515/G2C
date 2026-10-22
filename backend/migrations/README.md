# CJ-005 empty-database initialization admission candidate

`initialization-plan.json` is `CJ-EMPTY-INIT-PLAN@0.1.0-rc.1`. It pins the
accepted tree `3c52f72daf1d8e2304c0c569b47e68d92a4b323e` and exact Git
revisions, SHA256 bytes, table inventory and intra-file references of foundation,
MESSAGE, RUN and USAGE. `manifest.json` remains the sole registered migration
list: foundation v1 only. The three domain files remain candidates, new empty
private PostgreSQL only, never existing-database upgrades.

From the repository root, using the existing Python environment:

```sh
.venv/bin/python -B scripts/check-empty-db-init.py --source-repo .
```

The source repository must contain the pinned Git objects (an accepted Publish
clone can also be supplied explicitly). This command is offline: it validates
artifact ancestry, equality with the fixed accepted tree, hashes, SQL inventory
and registered foundation hash. It does not use moving main or working-copy SQL.
The reference inventory is a check of these exact files, not a general SQL parser
or a proof of runtime privileges. No cross-file SQL FK was found; RUN's original
MESSAGE receipt/USAGE bytes, canonical scope, provisioning and concurrency fences
are runtime obligations and do not establish an apply order. PostgreSQL16 is the
local validation baseline; no extension, role or grant is installed by this tool.

The result reports source validation and target admission separately, with
`apply: BLOCKED` even when validation passes. There is no apply option. Blockers:

- Domain candidates lack an accepted composite migration/rollback protocol.
- Unqualified candidate tables lack an accepted product namespace/search_path
  and trusted scope provisioning contract.
- Product runtime roles/RLS/grants remain unresolved. Preserve USAGE ENABLE/FORCE
  RLS, PUBLIC revoke and no-policy denial; do not add bypass grants/policies.
- Cross-domain original association and dispatch fences remain domain work.

Optional **read-only point-in-time** target admission requires every explicit
argument below. It accepts only a newly provisioned task-private directory named
`.local-cj005-init-*` directly under this checkout, with real `data` and `s`
directories. It refuses symlink paths, inherited PG*/DATABASE_URL/CJ_DATABASE_URL,
TCP listeners, mismatched actual data/socket/user/database/read-only settings,
existing initialization ledger and user schema/relation/function/type/extension/
event-trigger objects. No DSN, network fallback, credential lookup or SQL apply.
An admission PASS is not a lock/reservation for a later apply.

```sh
.venv/bin/python -B scripts/check-empty-db-init.py --source-repo . \
  --inspect-target --target-root "$PWD/.local-cj005-init-new" \
  --pg-bin /opt/homebrew/Cellar/postgresql@16/16.15/bin \
  --user EXPLICIT_TASK_USER --port EXPLICIT_SOCKET_IDENTIFIER
```

`new`, user and identifier are placeholders, not existing targets or provisioned
resources. Missing configuration/rejected targets return 2; dry-run success
returns 0 without suggesting apply success. This checker does not create or
start a database. Existing-target upgrade, restore, cleanup and production
activation remain unimplemented. Storage ownership/retention/deletion boundaries
are registered in `backend/storage-registry.json` (v1.1.0).

Targeted verification:

```sh
.venv/bin/python -B -m unittest discover -s backend/cj_api/tests -p test_initialization_plan.py -v
# Only with explicit fresh private-PG execution authorization; refuses existing root:
.venv/bin/python -B backend/cj_api/tests/initialization_admission_postgres.py \
  --target-name .local-cj005-init-new
```

Use a fresh lowercase suffix matching the validator, never reuse retained test
data. The one-shot test uses installed PostgreSQL16.15, bootstrap role `cj005i`,
database `postgres`, Unix socket identifier55447 and TCP disabled. It seeds only
registered foundation v1 to prove repeated/nonempty target refusal, then stops
its exact instance in finally. No candidate SQL, drivers, cloud or old DB needed.
The absolute Homebrew binary path is the tested machine dependency, not a portable
installer. New private output directories need a clone-local exclusion, never
commit database files. See the evidence report for actual executed targets.
