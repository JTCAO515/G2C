# Held-lock consumer increment — author evidence, 2026-10-23

Parent 426d337b0647d7770f1716fad83f2e5e724d28e4. Initial git status clean; prior core/manual/receipt/cancellation evidence retained. Only backend/memory/** and contracts/memory/** changed. No backend/memory_management/CJ019 or root edits. Existing public API inspection found only detached effective Context/check_fence and private Transaction.require_current; no equivalent public held-lock consumer existed.

Actual implementation: OperationContext.consume_current with request/thread/callback-lifetime CurrentMemory; canonical helper reused by effective/require_current; original scope lock and transaction retained around synchronous callback; post-callback and after-fresh-AUTH-precommit full data fence; exact bytes/explicit size bound; sticky errors/cancellation/deferred-close; prohibit nested context DB calls. Old read/probe/save/manual/query remain available with original compatibility boundaries.

PASS final `backend/memory/.venv/bin/python -B backend/memory/tests/consume_current_checks.py`: 13 focused methods, 0.266s, new empty PostgreSQL17:

- Canonical effective selection matches existing ordinary read: long-term/current override, companion partition, inference exclusion.
- Actual competing disable writer is observed in pg_blocking_pids waiting on the scope row while consumer callback runs; after consumption commits writer completes, next consumption excludes disabled item.
- Source withdrawal writer takes scope first; waiting consumer selects after withdrawal commit and excludes it.
- Same-transaction epoch, item version, disabled status, source revocation and source-version changes reject; those deliberately instrumented test changes roll back.
- Source expires during callback → Conflict; original source remains intact after rollback.
- Item changed by late precommit guard → final data fence rejects, proving data validation follows fresh guard.
- Strict materialized bounded result: view, iterator, coroutine, generator, generator-close cancellation, bytearray and oversized bytes reject; exact-bound bytes accepted.
- Escaped/old view, other thread and explicit early close reject; view is already expired when precommit guard runs.
- CancelledError/KeyboardInterrupt and caught bounded-result failure cannot turn into a successful operation response.
- Identity or same-scope repository object replacement by the outer callback after consume_current returns is rejected by final guard.
- Reentrant operation-context DB call during consumption rejects before second connection/deadlock.
- Earlier committed save followed by failed consumption retains original operation_id/commit_possible/reconcile and original query; failure does not pretend the earlier save rolled back.

PASS existing three no-DB binding checks after increment. PASS syntax/whitespace validation. No old full PG/manual/guard/keyset suite rerun; prior evidence reused.

Final PG identity: role cj011_consume / DB postgres / port56116 / listen_addresses='' / UTF8. Fresh cluster backend/memory/.local/consume-nf7k9plk/pg; private socket /tmp/cj011-consume-6a2d13ou (0700); explicit empty task pgpass0600; inherited PG* removed; no service/DSN/default pgpass inheritance. Cluster stopped in runner finally; data and test.log/server.log retained under the private directory, ignored by Git. No previous instance started.

Preserved earlier attempt: new cluster .local/consume-op04b2l7 initialized and stopped, but test setup failed because libpq treats explicit service='' as an empty named service lookup; zero behavioral tests ran. Removed that invalid service parameter; next separate new cluster .local/consume-7emiewqv passed initial 12 tests. Tightened view expiry to callback exit and added corresponding 13th regression; final run used another new cluster above. No retained cluster restarted or cleared.

The test runner always allocates a new task-local data directory and private socket; same fixed port is Unix-socket-only. Each invocation initializes from empty, runs only this impacted suite, and stops its own process in finally. Tests use synthetic source records and AUTH principal/guard decisions. No provider/real account/permissions/RLS/paid operation involved.

UNRUN: independent Review/Testing acceptance, actual CJ019 runtime composition, same-transaction RUN/Trip output persistence, real model context/reply/planning, App/device or complete Issue12. No atomic cross-store publication claim. Copied immutable private data cannot be revoked from trusted Python callback memory; request view freshness capability expires and is not reusable.
