# CJ010 PostgreSQL repository slice

Repository implementation began at 930236d64697f2d78d67b8046f0881fafb0d167a.
Delivery parent is the separate P2 repair 8a5c81aaf438325988a77b114bf7a2baebca1d8e.
This repository delta makes no further core/fixture changes. Scope: backend/run/**,
contracts/run/** only. Independent review/testing are pending.

## Result and boundary

- PASS: 11 task-private PostgreSQL checks (pg-tests.txt), including two-connection
  terminal race, concurrent original-ID acceptance, same-chat ordering/missing
  predecessor/UNKNOWN blocking, committed cancel/text/effect recovery, identity
  conflicts, scope revocation, expired run and cursor epoch, fixed highwater,
  gap detection, SQL single-terminal constraint and commit-success/ACK-loss.
- PASS: 6 injected DB-API lifecycle checks plus 14 existing core tests
  (unit-tests.txt). Cleanup failure cannot replace body error or committed result;
  uncertain commit is not rolled back/retried. No provider calls.
- PASS: explicit clean PostgreSQL restart and read of original cancelled run,
  partial text and committed synthetic receipt (pg-restart.txt). This is a real
  local database restart, not worker crash/abrupt DB crash/power-loss evidence.
- PASS: private PG16.15 was started with listen_addresses='' and an absolute
  task-private Unix socket. Tests asserted it. Cluster safely stopped after readback;
  data/postgres log retained under backend/run/.local, not committed or deleted.
- UNRUN: real AUTH/MESSAGE/USAGE composition, provider/tools, worker recovery,
  production privilege/RLS policy, cloud/old databases, device, deployment.
  Issue 11 remains open; no new permissions/roles/grants or formal migrations.

Evidence attribution: the PG11/restart and unit20 logs were captured before the
P2 repair with core at 930236d and the same PostgreSQL adapter/SQL bytes shipped
here. They are retained as pre-P2 repository evidence, not final combined-head
PG validation. Per Main instruction, the stopped cluster was not restarted for
the core repair. P2 has separate five-group/14-core regression evidence; combined
PG after the repair is UNRUN. Independent review must assess the added post-hook
read and existing PostgreSQL serialization before integration.

Runtime: core/lifecycle tests Python 3.9.6; PG tests Python 3.14.7, psycopg 3.3.4,
PostgreSQL 16.15 Homebrew. Driver was resolved with uv --offline from local cache;
no registry/provider network requested. No generic Python-minimum claim is made.

## Repository behavior

connect factory is injected: NEW non-autocommit connection per transaction,
READ COMMITTED; explicit statement/lock timeout milliseconds and timezone-aware
expires_at are mandatory, with no default production TTL/limits. The expiry is
persisted once at acceptance; replay does not extend it. Expired identity stays
occupied and yields ResyncRequired, never absent/re-dispatch. Internal trusted
scope must already exist, active, with explicit epoch. This does not authenticate
callers. A caller-supplied scope is not an acceptable production composition.

The scope row serializes all operations in that partition. This conservative
scope lock is intentionally simple (less concurrency across chats of one scope),
not a generic queue. Unique run/message/chat-sequence keys, event ID/sequence keys,
single-terminal and single-effect indexes back the adapter. Each append locks,
reconstructs prior committed events, checks exact transition/prefix and commits
new event plus projection together. Binding changes and gaps fail explicitly.
Database invariants do not replace the repository: arbitrary direct SQL mutation
can corrupt history; get detects projection/gap inconsistencies. Real privilege
policy must prevent bypass and is not created by this slice.

recover(binding) returns original immutable state, fixed-through Cursor and a
non-authorizing action: query_only for running/unknown, queued_no_dispatch for
queued, terminal otherwise. It neither schedules nor resets a run. events(cursor,
limit=explicit) checks identity/epoch and expiry under the same transaction. A
transport consumer must still authenticate and implement a protected wire codec.
The first implementation reads the retained run event log for integrity checking;
large-log bounded/paged storage optimization is future work with explicit limits,
not an unlimited production scaling claim. No events are pruned in this slice.

Context validation remains the existing Service hook; production hook must check
current trusted versions within the write fence and must not make provider calls
under the database lock. AUTH/USAGE atomic claim/cancel integration remains pending.
Post-terminal actual side-effect settlement belongs to its authoritative ledger;
this repository does not fabricate new terminal events or fees.

## Reproduction

Ordinary unit checks (no database):

```sh
PYTHONPATH=backend/run python3 -B -m unittest discover -s backend/run/tests -v
```

The explicit PG script only targets backend/run/.local/socket, ignores environment
DSNs, asserts no TCP listening and PG16.15, then applies candidate.sql. Run ONLY
against a new empty authorized private cluster; a rerun on an existing schema
fails rather than dropping/rebuilding it. Start/stop must be explicit. Original
cluster was retained stopped; do not reset it to rerun tests.

```sh
PYTHONPATH=backend/run uv run --offline --no-project --with psycopg==3.3.4 python -B backend/run/tests/pg_checks.py -v
# After explicit clean restart of that same private cluster:
PYTHONPATH=backend/run uv run --offline --no-project --with psycopg==3.3.4 python -B backend/run/tests/pg_restart_read.py
```

No root lock, sharedAPI, MESSAGE/AUTH/USAGE source or existing migration changed.
No production service registers this module. dispatch remains unconditionally disabled.
