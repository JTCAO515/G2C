# PostgreSQL metadata repository — author acceptance

Independent follow-on to the receipt fix; not a replacement for its independent gates.

- Previous fixed: 9641b8a28a5342e4e1cb1c74d6180ecdbedad315 (original e16 HOLD/FAIL preserved).
- Source fixed: df86b5bea1c1113d283ed7ee2f61783cf983c0cb.
- Branch cj/024-cleanup; only backend/cleanup/** and contracts/cleanup/**.
- Date: 2026-10-22 Asia/Shanghai.

## Authorized private resource and actual result

Initial checks: suggested root absent, new shorter socket root absent, /tmp same-port socket absent and no 55457 TCP listener. Suggested socket path would be123bytes, too long for macOS; reported adjustment before creation to task-owned .local/c24s (98bytes full socket file). No existing instance was reused.

- Data: <local>/Documents/Codex/2026-10-21/cj-024-cleanup/backend/cleanup/.local/cj024-journal-20261022/data
- Socket: <local>/Documents/Codex/2026-10-21/cj-024-cleanup/backend/cleanup/.local/c24s
- Port55457; private bootstrap/test role cj024journal; database postgres, initial public table count0 verified.
- Explicit empty task passfile, PG/LIBPQ ambient variables removed, explicit connection kwargs; no ambientDSN, secrets or old data read.
- PostgreSQL16.15 installed /opt/homebrew/opt/postgresql@16/bin; Python3.14; installed psycopg3.2.10 reused read-only from CJ005's driver directory. No install/new dependency resolution.
- Actual SHOW listen_addresses = empty, SHOW unix_socket_directories = exact new path. Host auth reject; local trust only in private0700 directories.
- Sole public table: cj_cleanup_journal_candidate. No other domain schema/table applied, no RLS/identity policy or production permission change. Test bootstrap role is not production least-privilege/authorization acceptance.

12 real-PG transaction tests PASS (pg-tests.log): original-operation create dedupe/conflicts, same-scope CAS concurrent intent, original intent persistence, explicit recovery+original receipt bytes, strict invalid receipts leaving state/journal unchanged, precommit guard SQL rollback, actual COMMIT followed by lost ACK, conservative unknown when commit did not occur, create ACK/close failure, postcommit guard loss, autocommit rejected before SQL, partial failure/retention gaps, corrupt derived state rejected without rewriting original journal.

Actual COMMIT faults wrap the real psycopg connection and call its real commit before raising, rather than claiming a mocked commit proves database persistence. Unknown results have no success publication and are read by original operation with normal connections; no hook called/retried.

Same new instance stopped then started exactly once. Fixture had confirmed original revocation bytes and original tasks_stopped intent whose real COMMIT lost ACK; original operation, exact journal and original receipt bytes matched after restart. Explicit original-operation recovery committed revision4 with unknown task state, preserving confirmed revocation. Subsequent read-only query/journal remained unknown/unchanged; not complete. This is planned shutdown/restart + injected process-boundary ACK fault evidence, not OS power-loss/fsync hardware qualification.

Final stop complete: pg_ctl status exit3 no server running; no postmaster.pid/socket/socket.lock; no TCP55457 listener. See pg-inventory.json and pg-stopped-readback.txt. Private data/server.log/commands.log retained in .local; never delete or restart it automatically. Server/command logs checked to exclude the synthetic sensitive fault payload.

Reproduce only in a newly authorized absent resource root; runner intentionally refuses the already-preserved original paths:

```sh
/opt/homebrew/bin/python3.14 backend/cleanup/tests/private_pg.py --pg-bin /opt/homebrew/opt/postgresql@16/bin --driver <local>/Documents/Codex/2026-10-21/cj-005-foundation/.local-cj005-pg/driver
```

Original14 state tests and964 strict receipt2+3 evidence reused; only affected real transactions/faults/restart added, no other domain suites run. py_compile and git diff/check PASS.

## Remaining boundary

No destructive executor, public progress credential, AUTH access provider/revocation, actual account/other-domain deletion, business-data restore/recreation, offline device, provider or backup cleanup was implemented or exercised. Production integration/deployment/least-privilege/RLS/durable service operations and Issue27 I remain UNRUN/UNKNOWN. Candidate metadata table itself is unregistered private storage awaiting canonical owner registration, retention/cleanup/restore fence; no invented registry ID or root registry edit. State complete remains solely frozen-manifest synthetic metadata proof.

Author results do not replace independent Review/Testing; Main must route this new source separately from964.
