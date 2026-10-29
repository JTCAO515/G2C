# Local execution protection metadata (0016)

Scope: [#170 design revision 2](https://github.com/JTCAO515/G2C/issues/170#issuecomment-6493556104),
JT approval to design/review then implement. This schema producer does **not**
activate the host consumer. It adds no public request field or wire version.

`cj_local_run_protection` is an immutable local account activation record.
`cj_local_run_requirement` ties the protected execution requirement to the original
MESSAGE receipt. Both use only the existing MESSAGE scope for RLS visibility, so a
missing budget/NEEDS configuration cannot hide the fact that protection is required.
Runtime can SELECT activation, SELECT/INSERT requirements, and cannot update,
delete or truncate either table. Activation remains operator-owned.

During upgrade, stop the host processes. 0016 holds exclusive locks while it finds
existing selection/binding/step scopes and matches provider_call ledgers to MESSAGE
scopes with the exact existing compact UTF-8 JSON/SHA256 mapping. Every receipt in
a matched scope receives a requirement, including ordinary messages with no first
step. Unknown mapping format, malformed periods or unresolved owners abort the
transaction. A ledger initialized before its original MESSAGE scope exists must be
reconciled by the trusted local operator before upgrade; it is never discarded.

Only ownership mapping is validated in SQL. Full attempt/receipt semantics remain
with the existing USAGE codec. A ledger with a provable owner but corrupt attempt
content is preserved and marked protected; the runtime codec must still refuse it.
No ledger, original message bytes, step or candidate is rewritten by this migration.

The later host consumer must implement these conditions before activation:

- Operator first activation locks MESSAGE scope and requires no unacknowledged
  delivery, then records activation and the explicit ledger atomically. It must
  verify original keys after unknown commit acknowledgement, never reset them.
- A protected message's receipt, requirement, NEEDS capture and outbox commit in
  one transaction. Missing configuration refuses new work and dispatch; history
  reads are separate from execution qualification. No legacy bypass switch.
- First execution of queued work without started/step evidence may use an explicit
  current profile. Started/step recovery uses the original profile and never
  redispatches or substitutes the new period.
- Both activation/send lock orders, ordinary pre-step work, lost API/worker config,
  unknown ACKs and semantic-corrupt ledgers require real runtime-PG probes.

Rollback must stop workers and retain records. Populated 0016 down refuses rather
than erase protection. Do not reinstall an old worker that ignores the markers and
claim it preserves protection. Migrations1–15 and their existing policies/grants
remain unchanged.

Schema evidence: `scripts/pg_suites.py local_protection_schema` (also in the default
PG gate). These are migration/permission fixtures on real PG, not formal host or
native App acceptance. Host downgrade regressions remain pending in the consumer.
