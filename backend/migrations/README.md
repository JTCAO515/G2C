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
| 11 | local_runtime_rls | `backend/migrations/0011_local_runtime_rls.sql` |
| 12 | message_active_one_way | `backend/migrations/0012_message_active_one_way.sql` |
| 13 | run_draft_outcome | `backend/migrations/0013_run_draft_outcome.sql` |
| 14 | m1_budget_needs_binding | `backend/migrations/0014_m1_budget_needs_binding.sql` |
| 15 | memory_runtime_rls | `backend/migrations/0015_memory_runtime_rls.sql` |
| 16 | local_run_protection | `backend/migrations/0016_local_run_protection.sql` |
| 17 | registered_usage_source | `backend/migrations/0017_registered_usage_source.sql` |
| 18 | travel_context | `backend/migrations/0018_travel_context.sql` |
| 19 | memory_edit | `backend/migrations/0019_memory_edit.sql` |
| 20 | memory_stop_use | `backend/migrations/0020_memory_stop_use.sql` |
| 21 | memory_typed_context | `backend/migrations/0021_memory_typed_context.sql` |
| 22 | trip_manual | `backend/migrations/0022_trip_manual.sql` |
| 23 | needs_runtime_write | `backend/migrations/0023_needs_runtime_write.sql` |
| 24 | trip_needs_basis | `backend/migrations/0024_trip_needs_basis.sql` |
| 25 | trip_needs_actions | `backend/migrations/0025_trip_needs_actions.sql` |
| 26 | message_trip_context | `backend/migrations/0026_message_trip_context.sql` |
| 27 | message_edit_context | `backend/migrations/0027_message_edit_context.sql` |
| 28 | trip_scoped_edit | `backend/migrations/0028_trip_scoped_edit.sql` |
| 29 | message_edit_result | `backend/migrations/0029_message_edit_result.sql` |
| 30 | trip_scoped_result | `backend/migrations/0030_trip_scoped_result.sql` |
| 31 | message_source | `backend/migrations/0031_message_source.sql` |
| 32 | local_cleanup | `backend/migrations/0032_local_cleanup.sql` |
| 33 | feedback_lifecycle | `backend/migrations/0033_feedback_lifecycle.sql` |
| 34 | memory_history | `backend/migrations/0034_memory_history.sql` |
| 35 | account_cleanup | `backend/migrations/0035_account_cleanup.sql` |
| 36 | account_cleanup_gate | `backend/migrations/0036_account_cleanup_gate.sql` |
| 37 | memory_publication | `backend/migrations/0037_memory_publication.sql` |
| 38 | device_bridge_v2 | `backend/migrations/0038_device_bridge_v2.sql` |
| 39 | device_original_actions | `backend/migrations/0039_device_original_actions.sql` |
| 40 | background_jobs | `backend/migrations/0040_background_jobs.sql` |
| 41 | c_account_cleanup_locks | `backend/migrations/0041_c_account_cleanup_locks.sql` |
| 42 | memory_decision_source | `backend/migrations/0042_memory_decision_source.sql` |
| 43 | background_v3 | `backend/migrations/0043_background_v3.sql` |
| 44 | memory_item_erasure | `backend/migrations/0044_memory_item_erasure.sql` |
| 45 | memory_payload_erasure | `backend/migrations/0045_memory_payload_erasure.sql` |
| 46 | formal_memory_activation | `backend/migrations/0046_formal_memory_activation.sql` |
| 47 | device_erasure_journals | `backend/migrations/0047_device_erasure_journals.sql` |

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
- Runtime access goes through the local-only role `cj_m1_runtime` (v11 onward: minimal
  grants plus ENABLE/FORCE RLS per table) and, for the #26/#27 cleanup paths only, the
  local-only `cj_local_cleanup` role (v32). Neither is a production provisioning decision.
- `down` files for versions 1–12 and 15 drop tables and their data unconditionally; later
  versions refuse to go down while data they introduced exists (ADR-0007). Use any down only on
  disposable databases; a rollback on a database holding user data needs explicit operator
  approval.
