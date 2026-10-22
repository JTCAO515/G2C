# Protected proposal display candidate

Parent63bcf9c1fa520c41a7154f5a798cef818274ebaa. Independent additive feature; does
not replace or pre-approve the parent interruption repair gate.

ProposalDetail frozen snapshot and public Boundary.proposal_detail reuse canonical
AUTH checks and scoped repository integrity verification. Returns original content,
actual digest/basis/expected version/state/expiry without mutation or confirmation.
list_trips now enforces string cursor type and explicit C ordering/comparison; exact
limit/keyset/no-has_more/no-snapshot semantics in contracts/trip/PROPOSAL-READ.md.

Author PASS: 12 real-PG tests for exact immutable snapshot, read-not-confirm,
wrong scope/missing generic denial, all terminal states and elapsed pending display,
fresh AUTH denial at entry/transaction/commit/return, bounded multi-page mixed-ID
ordering and invalid cursor/limit rejection. Existing original fault probes and real
stop/start original-v1/latest-v2 read also PASS via preserved runner. Prior 30/14
results are not rerun or added to this feature's count.

Fresh private empty UTF8 PostgreSQL17.11 with explicit role/db/socket/port/passfile,
clean env, listen_addresses empty; identity in pg-results.json. Final PID/socket
absent, 0700 private paths, data/logs retained. No old instance started or changed.
Syntax/diff checks PASS. No formal API/schema, public write lifecycle, AUTH policy,
provider, real account or deployment. Consumer acceptance and independent gates
PENDING; App/CJ014/actual review evidence gates remain open.
