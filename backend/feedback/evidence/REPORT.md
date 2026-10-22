# CJ023 first internal candidate evidence

Historical core `fc55f6cb69cbd8d5cd2ead53165698c434c7d066`; superseded for current
source integration by [SOURCES-REPORT](SOURCES-REPORT.md). Original results preserved.

2026-10-22, author checks only. Fixed base
`8f2ff45519d1d09f178f1fa766b6829d81bda77a`; independent clone
`/Users/jtsm5p/Documents/Codex/2026-10-21/cj-023-feedback`, branch
`cj/023-feedback`. Candidate source is fixed by this report's containing Git
commit and `source-sha256.json`. Source clone was read-only; all new tracked files
are under `backend/feedback/**` and `contracts/feedback/**`.

## Results

| Check | Result / limits |
|---|---|
| Original Issue | Read-only `gh issue view 15 --repo JTCAO515/Go2China --json number,title,body,state,url`; OPEN; plugin fetch returned null body so no inference from it |
| Initial interpreter | FAIL preserved in `initial-environment-failure.txt`; accidental Xcode Python 3.9, repaired by selecting supported cached Python 3.14.7 |
| Initial private PG | 28 tests PASS, restart original receipt PASS, logs sentinel check PASS; stopped; `initial-inventory.json` |
| Final private PG | 28 tests PASS (6 parser/domain, 22 persistence/boundary); restart original receipt PASS; `final-tests.txt` |
| Final runtime | Python 3.14.7, psycopg 3.3.4, PostgreSQL 16.15; explicit new unprivileged runtime role; Unix socket only, no TCP listener |
| Final restart | Same original action and receipt after actual fast stop/start; no replacement action |
| Scope checks | Service-level A/B and environment isolation; same action IDs independent across scopes |
| Concurrent submit | Same bytes: 4 callers, one durable row and receipt; different bytes: one submit, one conflict |
| Cancellation/ACK | Commit-before/after cancellation and lost ACK withhold response; original query distinguishes observed durable row from absence; close interrupt preserves original receipt |
| Authority/return | Existing AUTH interface with synthetic verifier/facts; entry/transaction/commit/return and final encoded projection checks; account/resolve changes and escaped operation rejected |
| Minimal content | Only exact voluntarily submitted action bytes + scope/action/hash/database time stored; query returns receipt only; no copied source ledger or diagnostic text |
| Log privacy | Secret sentinel absent from actual PG server/command logs; provider exception text sanitized; close-failure warning is fixed text |
| References | Structurally valid message/message+run refs uniformly unavailable; Trip/Memory/proposal and run-only rejected. Positive owner-confirmed source reads NOT YET IMPLEMENTED |
| Final stop | PASS; both preserved data roots have no postmaster.pid; commands log includes actual stop output |
| Independent Review / Testing | PENDING, Main routes fixed candidate to existing roles |
| Real accounts/provider/App/physical device/deploy | UNRUN; original Issue I and both UI entry points unchanged |

The final run includes the original parser/receipt/PG checks plus small same-scope
repairs: no closing/taking over rejected caller-owned connections, run-only rejected,
opaque reference IDs retain Unicode bytes, and the runner removes ambient PG/LIBPQ
configuration in its own process as well as child processes. Only these changes
motivated repeating the bounded suite in a second new empty private PG; no old
instance was reused. Existing domains' suites were not rerun because source was
unchanged and reference consumption remains disabled.

`final-inventory.json` records the preserved private cluster, socket, new roles,
empty passfile and stopped state. They contain fixtures only and remain outside
Git under `.local`. No old DB, Keychain, provider, real account, cloud, remote Git
write, production policy or cleanup migration was used. A new task-private role
and explicit test-only SELECT/INSERT grant are local fixture provisioning only.

## Remaining exact integration needs

- CJ009 fixed owner implementation of protected `ctx.query_message(message_id)`
  with same principal/scope and final guard; main's consumption confirmation is
  recorded in `contracts/feedback/README.md` but fixed code has not arrived.
- CJ010 fixed owner whitelist read for Receipt-derived complete Binding. The raw
  `Service.snapshot` is deliberately not consumed. Unknown versions/tool outcomes/
  failure stage remain unknown; no timestamp or historical outcome is invented.
- After both pins: compose under the owner-defined lifetime/freshness fence,
  implement minimal refs only, test positive and foreign/missing/changed/expired
  source paths, then obtain consumer confirmation. Current test PASS cannot stand
  in for these future source tests.
- CJ005 owns formal FEEDBACK wire, error mappings, root migration/storage/cleanup
  registration and deployment database privileges/RLS. No root files were edited.
- Real AUTH/DB atomic revocation, cleanup/restore fences, retention and actual App
  entry points are UNRUN. No Issue closure, PR, push, merge or release requested.
