# CJ013 author validation — 2026-10-22

Fixed base: `8f2ff45519d1d09f178f1fa766b6829d81bda77a`.
Candidate: the local commit containing this report; independent Review/Testing pending.
Branch: `cj/013-needs`; clone: `<local>/Documents/Codex/2026-10-21/cj-013-needs`.
Only `backend/needs/**` and `contracts/needs/**` changed. No source-tree mutation,
root migration/lock/API/UI edits, push, PR, merge, deployment or Issue closure.

## Actual evidence

- **PASS** final 40 targeted tests, `pytest-final-40.txt`; Python 3.14.7,
  PostgreSQL 17.11 Homebrew, psycopg 3.2.13, pytest 9.0.2. Locked task-local offline deps.
- **FAIL retained then fixed** `pytest-first.txt`: 33 passed / 1 failed. Python 3.14
  accepted `24:00`; explicit hour/minute/second validation now rejects it without
  shifting the user's date. `pytest-after.txt`: 35 passed after correction.
- `pytest-final.txt`: 39 passed after original-query cancellation identity tests;
  final 40 adds validation of published positive/negative contract examples.
- Real private PostgreSQL transactions: exact bilingual original bytes and replay,
  same-action different-byte conflict, partial-budget correction without invented
  amounts/currency, immutable historical source bytes, stale-version refusal,
  concurrent CAS one winner, concurrent original replay, scope isolation,
  local companion referential isolation, user-provided fixed booking/locked intent.
- Failure/cancel checks: rollback before commit; synthetic lost ACK **after a real
  PostgreSQL commit**; cancellation during/after commit; late connection close;
  original-action query cancellation; caught failures cannot produce success bytes;
  AUTH flips before commit / after serialized result; changed resolver; expired
  operation handle; unconfigured/unknown AUTH; active caller transaction rejected.
- Restart check stops and restarts the same newly created test cluster, constructs
  a fresh host, then reads snapshot, receipt and exact original bytes successfully.
- Final cluster: `backend/needs/.local/pot0crglr`, new synthetic role
  `cj013_synthetic`, explicit port `56413`, private Unix socket, `listen_addresses=''`,
  no TCP listener, explicit empty password and empty 0600 passfile. No ambient DSN;
  inherited PG variables cleared only in the test process. All four run clusters
  (`po4lse3zg`, `pn0utjt4n`, `pxyzw152b`, `pot0crglr`) stopped with preserved data,
  server logs and STOPPED markers. No old databases or other instances accessed.

Fixtures are synthetic identities and user claims. Fault wrappers simulate transport
ACK loss/cancellation; persisted data itself is checked against real PostgreSQL.
This is local module/transaction evidence, **not** independent review, production
permission/RLS proof, real accounts, supplier verification or complete user journey.

## Fixed dependencies / integration requests

- AUTH public imports at the exact base: `backend/auth/cj_auth/interfaces.py`,
  `backend/auth/cj_auth/admission.py`; existing admission checker/principal only.
- Existing TRIP transaction/response lifetime pattern inspected at the same base;
  no private repository/source object imported, no TRIP write or schema reuse.
- **CJ005 pending**: owner-confirmed principal/environment → account-scope/fresh
  connection resolver, schema registration/grants/RLS/cleanup plan, official API
  mapping of four methods and existing BASE errors. No root wiring performed.
- **CJ035 pending**: confirm fields, required-input policy and candidate version.
  Unknown conditions block only computations requiring them, never partial saving.
- **MESSAGE/RUN pending**: owner-confirmed public source/ownership/version/current
  context binding before adding either source mode. Both rejected by this candidate.
- **UNRUN**: production account/DB, HTTP/App, device, model extraction/provider,
  long-term Memory lifecycle, formal Trip, solver, root migration, deploy, CI,
  original Issue 14 I dependencies and complete acceptance. Issue remains open.
- `NEEDS@1.0` is **not frozen**. No consumer ACK is implied by author tests.
