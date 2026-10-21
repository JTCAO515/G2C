# CJ009 internal message transaction slice

Candidate `message-domain.1`; standard-library core. Integrated runtime declaration
is Python `>=3.12,<3.15` (repository/AUTH intersection; consumer tested on 3.14.7 only).
Ownership is exclusively
`backend/message/**` (and pre-existing `contracts/message/**`). No shared route,
OpenAPI, root lock, migration registry, auth module or old VP resource is modified.

Source baseline: local parent `482c8351c95403df52351e2087272129021a37f8`.
Read-only integration source `7cd587bf1476cbdbbee433068fcc7f8fd79427a8` fetched and
checked: applicable AGENTS/contracts rules unchanged; no message backend existed.
The integration tree was not merged/copied over unrelated local paths. Source
contracts are semantics only: no imports from `contracts/message/model.py`.

## Package boundary

- `cj_message/domain.py`: immutable original UTF-8 parsing, duplicate/conflict rules,
  receive/query, message paging with scope/creation/data generation and high-water
  sequence, readout of pending original run obligations.
- `cj_message/postgres.py`: injected DB-API PostgreSQL transaction/repository source.
  No driver import, DSN, connection establishment or routing. A future trusted host
  supplies a NEW non-autocommit connection per transaction. No SQLite substitute.
- `sql/candidate.sql`: UNAPPLIED PostgreSQL candidate, not a migration. No automated
  application command. Scope/chat provisioning, production privileges/RLS, TTL,
  physical cleanup and recovery tombstones are deliberately not supplied here.
- `tests/`: injected transactional and recording DB-API doubles. They execute Python
  behavior, not PostgreSQL SQL, constraints, concurrency or real durability.

`scope` is an internal storage partition key, NOT a proposed TrustedPrincipal field
or an authorization claim. Service/repository constructors are internal composition
primitives, never request handlers. They do not authenticate or authorize anything.
No caller owner/user_id is accepted in message input. AUTH fixed interface is still
pending from Main/CJ007; no guessed principal adapter or permissive fallback exists.
This package must not be exposed until CJ007/CJ005 wire the real verified gate and
scope mapping, recheck authorization at commit/dispatch, and enforce DB privileges.

## Transaction behavior

Receive validates original bytes, then locks the provisioned scope row before any
idempotency lookup. This deliberately serializes a partition, including duplicate
IDs used across different conversations; lock throughput optimization is out of scope.
It returns an old receipt only after matching exact bytes and current active chat
creation generation. Otherwise it reads/locks the active chat, assigns the next
sequence, inserts immutable raw input/receipt and an obligation with the SAME run
ID, and updates sequence, all inside one transaction. Receipt leaves Service only
after commit succeeds. No external run/provider call takes place under the lock.

The SQL candidate also constrains per-scope message ID, per-chat-generation sequence,
per-scope run ID, and delivery-to-original-receipt identity. These constraints and
lock behavior have NOT been tested on PostgreSQL. Query/index/locking decisions were
checked against [PostgreSQL INSERT](https://www.postgresql.org/docs/current/sql-insert.html)
and [explicit locking](https://www.postgresql.org/docs/current/explicit-locking.html).

Commit exception becomes CommitUnknown; no automatic commit retry or new action/run
is attempted. Caller retains original bytes and ID and queries later. A query `None`
only denotes absence in this repository ledger; future retention/cleanup policy must
establish whether that is authoritative before enabling retries. No unlimited dedup
window or TTL is claimed. A missing/recreated/inactive chat is Unavailable, never a
new empty successful replay of the old action.

Paging captures high-water sequence, creation generation and data epoch. Append does
not change an existing page boundary. Wrong binding, stale generation or missing
sequence rejects with ResyncRequired, not silent partial/empty history. Cursor is an
internal Python value; no public token encoding/signature or client parsing exists.
Returning original message text/drafts/conversation-list/summary integration is outside
this transaction slice; prior contract fixtures are not production implementations.

`pending()` returns persisted ORIGINAL run IDs and receipt associations. It neither
creates replacement runs nor calls RUN. No ACK mutator/worker is exposed until RUN
has a fixed idempotent accept/query receipt and AUTH/USAGE dispatch gates are wired.
Repeated reads can return the same obligation (at-least-once recovery intent).
Actual dispatcher ordering, provider unknown charges, cleanup revalidation and durable
worker crash behavior remain unimplemented, not simulated as service success.

## Candidate data/cleanup obligations

Private raw bytes and receipts live in receipt candidate rows; pending associations
live in delivery rows, creation/data generations in chat rows. CJ009 owns their
future cleanup hook; CJ005 registers final stores/migrations/privileges; CJ024 governs
revocation, physical deletion and backup replay. No grants, security-definer functions,
owner bypass, destructive migration, TTL or deletion API is provided. Candidate foreign
keys intentionally prevent silently detaching receipts from their chat generation;
future cleanup must design retention/tombstones and serialize with the same scope lock.
Non-null Trip is explicitly unsupported; no pretend Trip authorization is supplied.

## Run and remaining gates

From repository root:

```sh
PYTHONPATH=backend/message python3 -B -m unittest discover -s backend/message/tests -v
```

`requirements.lock` states the zero third-party dependency set. PostgreSQL driver
selection/pinning belongs to later host integration, not an installed runtime claim.
Before production use: fixed AUTH interface + gate/scope integration; CJ005 unique API
and migration registration; actual PostgreSQL transactions/concurrency/commit-loss/
permissions tests; RUN/USAGE dispatch contract; retained-action recovery and cleanup
policy; deployment authorization and real end-to-end evidence. None are waived by
these local tests. No server, database, socket, cloud resource or model was started.

## Fixed AUTH candidate consumption (additive)

The pending-interface statement above describes the original transaction slice.
`auth_boundary.py` now provides an internal candidate consumer of fixed CJ007
`79f88b6552da1bd3d4b27e22f64a158bddf2853b`, without importing the moving JWT tree.
See [AUTH-CONSUMPTION](AUTH-CONSUMPTION.md) for the original six checks plus two repair-delta checks, exact runtime declarations and untested versions,
server mapping and revocation/commit consistency gaps. It does not enable routes or
turn test providers into production authorization. Domain/repository/SQL remain unchanged.

## Transaction cleanup priority

Rollback/cursor-close/connection-close failures cannot replace the primary body error,
CommitUnknown, or successful commit. Both closes are attempted. Secondary failures are
reported through fixed stage/outcome warning labels only, with no exception text or SQL.
If the logging handler itself fails, primary outcome preservation takes priority;
logging availability is a host concern. A failed rollback is not reported as completed,
and no cleanup/commit automatic retry occurs. Targeted injected evidence is in
`evidence/cleanup-after.txt`; this is not real PostgreSQL cleanup acceptance.
