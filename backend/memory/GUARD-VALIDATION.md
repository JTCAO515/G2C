# Guard increment author validation — 2026-10-22

Parent: 6a3492fbd0249d02cea250630b409c90be39a0b0 (core 1ca000f retained). Changes: additive Service.with_operation, request-lifetime context, guard fault tests and internal consumption contract. No root API/auth/migration changes.

PASS `backend/memory/.venv/bin/python backend/memory/tests/guard_checks.py`: 12 tests, 0.097s, real fresh PostgreSQL transactions with synthetic trusted guard decisions:

1. Exact entry/transaction/transaction_ready/precommit/private_return/return order and saved JSON bytes.
2. Four precommit faults (DENIED exception, UNKNOWN/no binding, principal replacement, scope replacement): item and operation rows absent after rollback.
3. Postcommit access loss: response withheld, original operation retained and queryable, reconcile_original.
4. Read projection encoding precedes final guard; final rejection yields no response bytes.
5. Escaped context expired; deferred/non-bytes results rejected.
6. Cross-thread context use rejected.
7. All five read methods pass through transactional precommit and final guard.
8. Real commit then simulated lost ACK: reconcile_original, original receipt persisted.
9. Projection failure after save: reconcile_original, not false rollback.
10. Callback swallowing precommit denial cannot turn it into a successful response; rollback verified.
11. Entry denial does not open a DB connection.
12. Repository scope mutation detected at precommit; rollback verified.

New cluster only: backend/memory/.local/guard/pg, role cj011_guard, DB postgres (fresh empty default database), UTF8, Unix socket /tmp/cj011-guard-01a16218 (0700), port 56112, listen_addresses=''. Explicit task-local empty pgpass (0600); PG* environment removed, no inherited DSN/service/credentials. PostgreSQL 17 initialization/start and tests succeeded; pg_ctl stop -m fast returned server stopped. Data retained, ignored by Git. Old 56111 cluster never started.

Tests deliberately create tables without IF NOT EXISTS and a new empty passfile without overwrite. Reproduction requires another authorized fresh private cluster and adjusted explicit identity; do not rerun against retained evidence or delete old state to force green.

Original core evidence remains at 1ca000f / VALIDATION.md. Guard tests use synthetic decisions and existing TrustedPrincipal type, not real AUTH/network/account revocation evidence. API route consumption, App UI, same-session model next reply, production permissions and complete Issue12 remain UNRUN. Fresh guard does not provide distributed AUTH/DB atomicity.

## CJ005 live-list consumption delta

PASS `tests/list_checks.py`: 12 opaque IDs including ASCII case, leading/trailing whitespace, Chinese, emoji, composed é versus decomposed e+accent, ß/ss and İ/i. Explicit C comparison/order returned exact UTF8 byte order with no duplicates; JSON round-trip retained exact IDs; pages 5/5/2/0 with final null anchor; limits 1 and 100 accepted, 0/101/bool rejected. Save and list ran through new guarded public context.

Separate new cluster backend/memory/.local/list/pg, role cj011_list, fresh postgres DB, UTF8, private socket /tmp/cj011-list-01a16218, port56113/listen_addresses empty. Old guard/core clusters remained stopped. New empty private passfile, ambient PG* cleared. New cluster stopped successfully after test and retained. Candidate schema delta adds C collation to item ID columns; no existing migration applied. Source SQL now explicitly uses C for keyset comparison and sorting; exact-ID semantics no longer rely on default database collation. This is live pagination, not a has-more or snapshot guarantee.
