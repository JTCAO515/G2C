# Manual producer increment — author evidence, 2026-10-22

Parent f410193c3d8675869a9a996e83ead23b1a5a6a56. Only original backend/memory/** and contracts/memory/** lease. No new authority tables or DDL columns; same source/item/operation transaction. Existing reference path and f410 guard retained; added configured manual policy and public guarded save_manual.

PASS 12 tests in tests/manual_checks.py (0.116s), against a new private PostgreSQL 17 database:

- First manual save: source/item/operation counts 0/0/0 → 1/1/1 without any source seed; exact original request stored in receipt ledger, server-derived source bytes in source/item.
- 12 concurrent submissions across 6 workers return one original result/source/item; same operation with different raw whitespace conflicts.
- Client source_id/source_version/owner/confirmed/authorized/source_kind injection rejected.
- Missing policy, expired deadline, sensitive denial/UNKNOWN, companion/slot/current-context scope mismatch: no source/item/receipt written.
- Inference and unresolved semantic equivalence persist as candidates, excluded from effective context.
- Precommit AUTH guard denial rolls back all three rows. Item-slot conflict rolls back newly created source too.
- Actual commit then simulated ACK loss: reconcile_original and guarded original query; all three committed rows retained.
- Scope B cannot read A's manual item/receipt; replay of revoked source does not change its active=false/version=2 state.
- Replacing server policy at precommit rejects and rolls back.
- Existing reference save with a separately approved source remains compatible under with_operation.
- Current-context manual item overrides only its matching context; other context does not receive it.

PASS existing three binding_checks.py tests after additive implementation. PASS compileall and diff whitespace checks. No repeated old PG validation or claim that prior fixed snapshots changed.

New private cluster: backend/memory/.local/manual/pg; role cj011_manual; fresh default postgres database; UTF8; Unix socket /tmp/cj011-manual-01a16218 (0700), port56114, listen_addresses empty. Explicit task-local empty pgpass0600; ambient PG* removed, no DSN/service inheritance. Previous core/guard/list instances remained stopped. New instance successfully stopped after tests; data retained and ignored by Git. No real accounts, sensitive user data, provider or production resource used.

Tests create tables/passfile once and intentionally reject an existing destination. For reproduction allocate another authorized fresh private cluster and change only explicit test connection identity; never clear retained evidence or launch old instances. Test allow callbacks and one-hour deadline are synthetic only, not accepted product scope/sensitivity/retention policy.

UNRUN: actual CJ005 manual route/official generated client consumption, actual UI/account acceptance and same-session next answer; accepted production collection/retention policy and physical cleanup. This increment does not close Issue12.
