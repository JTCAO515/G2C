# CJ009 isolated PostgreSQL acceptance

Source under test: `cec92299aa77e74baafba473ecf9db7b926fbe4e`; parent of this evidence
delta is also cec92299. Existing domain/repository/AUTH boundary/SQL bytes unchanged.
Local macOS PostgreSQL **16.15 Homebrew**, Python **3.14.7**, psycopg **3.2.10** pure
Python package installed ONLY into `.local-pg-01/venv`. No global installation.

## Exact target and isolation

New previously nonexistent directory:
`<local>/Documents/Codex/2026-10-21/cj-009-message/backend/message/.local-pg-01`.
Private parent/socket directory mode 0700; data under `data`; only socket under `s`,
port identifier 55439, explicit user `cj009`, database `postgres` in this NEW cluster.
`listen_addresses=''`, socket mode 0700. No TCP listener, launchd or system changes.
Local trust authentication applies only to this task-private socket; it is NOT a
production auth/RLS configuration. No existing databases/Docker/VP resources used.
All PostgreSQL commands used a cleared environment and explicit paths/user/database;
the harness rejects PG environment variables and checks data_directory/listen_addresses
before any SQL. The generated cluster bootstrap files are local PostgreSQL internals,
not product migrations. No data or credentials imported.

First sandbox attempt: pip DNS failure and initdb shmget Operation not permitted;
no running instance resulted. Failure logs retained locally. Standard tool approval
then allowed the same scoped init/start/test operations. initdb itself removed its
failed initial data tree; subsequent approved initialization used --no-clean.
No manual cleanup/delete of cluster directories occurred.

## Applied candidate and actual results

Only module `sql/candidate.sql` applied to the empty temporary database as schema,
SHA-256 `44707ea75b7c48ebe8c6f7e51a29099a34bf66ea7ac79d0808de451ee5dd3790`.
Its source comment UNAPPLIED remains a warning for shared/target deployment: this
single disposable local application is now explicitly evidenced, not a migration
registration or application elsewhere. Environment query: pg-environment.json.

`tests/check_postgres.py` uses actual repository/service + actual psycopg connections.
No transaction/DB engine double and no SQLite. Six tests PASS (pg-tests.txt):

1. Real original bytea/receipt/delivery commit, exact duplicate readback and original run.
2. Exception injected AFTER actual receipt and delivery INSERTs but before COMMIT;
   actual PostgreSQL ROLLBACK removes both and sequence increment, next receive is seq1.
3. Actual COMMIT succeeds, then wrapper injects lost ACK exception; CommitUnknown reaches
   caller, independent new connections recover original receipt/run with only one obligation.
4. Two simultaneous connections with same ID/different bytes: one accepted, one conflict;
   one receipt/delivery pair, enforced through actual scope lock/constraints.
5. Two simultaneous same-ID/same-byte requests return the same original receipt/run.
6. Actual message pagination: append preserves high-water, epoch change rejects old page,
   same-ID recreation with new generation rejects old cursor. Recreation deletes only
   that test's explicitly new synthetic rows in the task database, under scope lock;
   this is not a production cleanup API. New generation has explicit empty history.

Then actual safe stop/start of this cluster, separate Python process original-action
query/duplicate/pending readback PASS (pg-restart.txt). No new run factory invocation.
This is a graceful PostgreSQL restart, NOT OS power loss, SIGKILL recovery, actual
network packet loss or provider exactly-once proof. Injected ACK error occurs only after
confirmed real commit, giving an exact known committed side for recovery validation.

## Stop and preservation

Final `pg_ctl -m fast -w stop` succeeded (pg-stop.txt). Verified no postmaster.pid and
no task socket after stop; data directory retained (pg-preservation.txt). Raw init,
install, server/restart logs and data remain under the ignored private directory.
No data directory deletion, other-instance stop, remote/config/URL changes or push.

Reproduction requires an explicitly authorized isolated instance at this exact task
path; `check_postgres.py setup` refuses already initialized tables. Do not blindly
rerun setup or start an existing environment. `tests/pg_requirements.lock` records
only the local test driver; runtime host dependency selection is still separate.

## Evidence limits

PASS is limited to this PostgreSQL16.15 cluster and tested source/SQL. Existing
cleanup-exception unit evidence remains separate; no broad old-suite rerun. Actual
AUTH verification/providers, policy/commit atomic revocation, production DB grants/RLS,
TTL/cleanup/backup restore, RUN dispatcher/model calls, target/cloud/API/device and
production performance remain UNRUN. Tests use synthetic scope/chat data and local
bootstrap superuser, so they do NOT prove real identity or cross-user authorization.
No product source repair was needed. Independent Review/Testing of this delta pending;
Issue #10 remains open.
