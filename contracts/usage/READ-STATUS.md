# Original-attempt status storage seam

Base CJ008 5c248ad22f449aef8e42d7f4256bfc19e6c346a2; inspected current main
8f2b3d64c0db0178e09b88b20276e61c144906da. Issue9 remains open.

`PostgresRepository.read_status(attempt_id, *, guard, max_response_bytes, project=None)`
returns bounded materialized bytes after a READ ONLY transaction, successful
cursor/connection cleanup and final original-binding check. No Meter/_bind,
reserve/claim/settle/cancel, FOR UPDATE, ledger/config write or revision increment.
It reuses canonical codec/Attempt/Config. Missing/corrupt state never resets.

Mandatory guard() is an existing canonical authority lifetime's synchronous throwing
check returning None; it is not authentication or caller-supplied permission.
Scope/connection factory are captured before callbacks. Checks follow connection,
cursor, SQL, fetch, projection, commit and all close callbacks. Cancellation, scope
change, deferred projection, close failure or unknown completion withholds bytes.
Primary failure/commit-unknown has precedence over cleanup errors. Projection must
finish the host's final encoding inside the original protected lifetime; no later
envelope callbacks. Trusted injected Python is not an adversarial sandbox.

Projection contains original attempt/operation/run, actual state
(reserved/unknown/released/settled), stored unit, original reservation, optional
confirmed receipt amount/output/ID, cancelled/exceeded, paired English/Chinese text.
Unknown amounts are null, never zero. Confirmed zero remains zero. No scope, whole
ledger, input_digest, prompts, budget ceiling, balance or other attempts. Unit is
opaque, not presumed money. Historical receipt is not current budget/permission.

## Historical AUTH public seam gap (at inspected main)

At inspected main AUTH only exposes single-check AdmissionChecker.check(token),
not a protected-operation context with captured current identity and final callback
checks. MESSAGE with_history_context requires its MESSAGE repository and scope
mapping; using it for independent/background usage adds an unaccepted dependency.
No new authentication wrapper/permission authority is introduced here.

Main must route a minimal public context/confirmation to AUTH owner, or explicitly
accept an existing context dependency. It must reuse AdmissionChecker and trusted
host environment + issuer/subject/audience + authorized budget-period resolver,
bind the same repository scope and keep original current admission/lifetime through
final bytes and cleanup. UNKNOWN/DENIED cannot return private status; missing host
config fails closed. No caller owner/unit/budget/period chooses storage. Refresh
cannot create new partitions. Historical period access is server-authorized.

Until then this is an internal SELECT/projection candidate, NOT the completed
canonical authenticated public seam. No HTTP schema/route/registry/JWT/dispatch
model or capability. Guard injection tests prove storage callback handling, not
real Auth, atomic revocation, shared exit fence or real fees.

## Fixed author evidence

Source `68763c44fddf2e6d11799d1311dbd497d9c657c9`: compile PASS.
13 targeted canonical-type/synthetic-authority/injected-callback tests PASS;
11 new private PostgreSQL checks PASS including SELECT-only privileges and exact
all-row revision/ledger equality. Evidence under backend/usage/evidence/read-status-*.
Current public authenticated reader, real AUTH/revocation, product RLS/host resolver,
fees, wire and deployment remain UNRUN. No old core suite rerun for these additive
read methods. Issue9 is not closed by the storage fallback.

## Later fixed AUTH consumer

This storage-only gap is subsequently addressed by the domain consumer in
[PROTECTED-STATUS.md](PROTECTED-STATUS.md), consuming AUTH8b6abb2's public context.
The earlier evidence and gap describe their exact source boundary; they are not a
claim that the newer composition has passed independent gates or formal wire/I.
