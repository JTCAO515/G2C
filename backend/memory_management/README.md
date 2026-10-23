# CJ019 memory management domain candidate

Internal pause/resume extension of CJ011. See [the internal contract](../../contracts/memory-management/README.md) for authority, CAS, receipt, unknown/cancellation and unresolved edit-source semantics. Root API and migrations remain CJ005-owned.

No production connection or service entry is supplied. Import paths are `backend/memory` and `backend/memory_management`; only trusted server composition may construct a scoped repository. The original CJ011 Python source and contract are fixed inputs, not copied implementations. Candidate SQL applies **after** original `backend/memory/schema.sql` in a newly created private test database only; actual registration/application is unimplemented.

Run with an already installed Python 3.11+ / psycopg[binary] 3.2.10 and local PostgreSQL 16:

```sh
python -B backend/memory_management/tests/run_private_pg.py
```

The runner creates a new `.local/pg-*` cluster and task-private `/private/tmp/cj019-*` Unix socket on port 56219, with explicit new `cj019_owner`, empty private passfile, C locale/UTF8, no inherited PG environment and `listen_addresses=''`. It checks actual identity/settings before candidate SQL, runs 14 directed tests, stops/restarts the same task-owned server for read/replay checks, then stops and verifies absent PID/socket. It never reuses a previous data directory, starts other clusters, reads a DSN or connects by TCP. Data, connection parameters and detailed server logs remain local and ignored. The driver stores unique run evidence in `evidence/`; failed evidence is retained.

This checkout used the existing CJ011 installed Python environment read-only; it was not modified. The scoped lock reuses the accepted CJ011 dependency graph with only project name changed. No install/lock resolution success is claimed: the prior uv cache approval was interrupted and not retried. The fixed installed psycopg version was checked before actual execution. Root locks were untouched.

Publication integration, protected AUTH/API entry, actual source authority, UI, actual model/provider and device acceptance remain UNRUN. A shared-lock test is only a domain transaction check. Pausing is not physical deletion; action-ledger content must join CJ021/CJ024 cleanup and restore handling before production use.
