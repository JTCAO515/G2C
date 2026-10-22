# P2 final close fence — original owner repair

- Previous fixed source df86b5bea1c1113d283ed7ee2f61783cf983c0cb, evidence1c5377732b6c0c863b6122afccd2e401119db304 remain historical HOLD.
- Repair source b92afdf8bfd74095edf706551f0e1fccc970aae9.
- Only backend/cleanup/** and contracts/cleanup/**; no AUTH, root registry or other domain edits.

Original independent sources read-only: /Users/jtsm5p/Documents/Codex/2026-10-21/cj-testing/CJ-024-cleanup-postgres/REPORT.md, IndependentCloseFenceTests.py, independent_pg_runner.py, pg/tests.log. Exact probe file copied verbatim to tests/IndependentCloseFenceTests.py, cmp PASS. Original14-method log (12PASS/2FAIL) retained in pg-close-independent-before.log; original FAIL is not overwritten or reclassified.

Fix: move final captured-context guard check after successful final external conn.close. Compare captured connect/scope/guard/scope_bytes before and after the host guard. No connection cleanup runs after that check. Successful committed write whose close callback invalidates context throws CommitUnknown; query refuses private publication. Earlier body/commit exceptions are preserved; rollback/close errors cannot mask Conflict, Denied or CommitUnknown. Close failure after otherwise successful commit remains CommitUnknown for a write and Unavailable for a read. No hook retry/new ID or permission source added.

## Actual affected validation

New absent task-private resource paths were reported before creation, no same-port socket/TCP listener found:
- data /Users/jtsm5p/Documents/Codex/2026-10-21/cj-024-cleanup/backend/cleanup/.local/cj024-close-20261022/data
- socket /Users/jtsm5p/Documents/Codex/2026-10-21/cj-024-cleanup/backend/cleanup/.local/c24c
- Unix port55458; rolecj024close; PostgreSQL16.15, Python3.14, existing psycopg3.2.10 read-only driver.
- Empty public schema checked before applying sole cj_cleanup_journal_candidate table. listen_addresses='' verified. Explicit empty passfile; PG/LIBPQ ambient env removed; no ambientDSN.

10 actual PG methods PASS in pg-close-tests.log:
- Original exact two probe functions, unchanged, operate on real psycopg COMMIT/close with synthetic close callback guard loss. Write withheld as CommitUnknown while original intent is queryable; private read withheld.
- 5 new affected controls: conflict over rollback+close errors; COMMITunknown over close errors; query Denied over close error; query close error withholds private value; four captured context fields mutated during close all withhold read.
- 3 prior affected methods reused verbatim: postcommit guard loss, lost create ACK+close failure, precommit guard rollback atomicity.

Original12 transaction and restartPASS evidence reused; no unrelated core/domain tests rerun and no author55457 or Testing56134 instance restarted/read. New55458 cluster started once and stopped once, no additional restart needed for this close-boundary family.

Final actual pg_ctl status: no server running (expected exit3). pg-close-inventory.json records stopped=true, no postmaster.pid/socket/socket.lock. Data/server.log/commands.log retained under new private .local root; fault sentinel text absent from logs. No TCP listener configured; final lsof55458 has no listener. py_compile, cmp exact probes, diff/check PASS.

```sh
/opt/homebrew/bin/python3.14 backend/cleanup/tests/private_close_pg.py --pg-bin /opt/homebrew/opt/postgresql@16/bin --driver /Users/jtsm5p/Documents/Codex/2026-10-21/cj-005-foundation/.local-cj005-pg/driver
```

Runner rejects the now-existing preserved paths. Do not restart/reuse them automatically. Reproduction requires a separately authorized newly absent private resource.

This is real metadata transaction evidence with a synthetic host guard callback. It does not establish real AUTH revocation, account deletion, production durability/security, physical cleanup, public progress credentials or Issue27 I. Destructive executor/public query remain closed. New metadata store canonical registration/retention/cleanup/restore fence remains unresolved; no production activation. Independent repair Review/Testing pending Main routing.
