# USAGE internal candidate 0.1.0 (not frozen USAGE@1.0)

CJ008 / Issue9 local slice. Fixed consumed base:
`d30cbc5200f8fdaa59558a07984049caa5ba5999`.
No new API, root dependencies, generated clients or production migrations.

## Main / AUTH / BASE confirmation required

Read `contracts/auth/SERVER-INTERFACE.md`, `backend/auth/cj_auth/interfaces.py`,
`admission.py`, MESSAGE's existing boundary and `contracts/api/openapi.json` at
that base. Expected AUTH identifier is `CJ-AUTH-SERVER@0.1.0-rc.1`; it is not
full AUTH@1.0. Current core deliberately imports neither AUTH nor MESSAGE.

Before a real adapter/route can consume this candidate, Main must route:
1. AUTH confirmation: fresh `AdmissionChecker.check(token)` before dispatch;
   only ALLOWED plus verified principal is usable; DENIED/UNKNOWN never dispatch.
   Background tasks must reacquire authoritative identity/admission, not persist
   ALLOWED as a capability. No caller-provided principal or mock principal in host.
2. Server-owned mapping from stable issuer/subject + authorized environment to
   one budget repository. Token iat/exp must NOT create fresh budget partitions.
   No caller-selected scope; account/session revocation atomicity remains open.
3. BASE owner mapping of internal blocked/unknown/conflict outcomes into existing
   ErrorResponse, request_id and recovery. No fabricated request_id or
   invented public error codes; no edits to shared OpenAPI in this slice.
4. Configured budget, integer unit, period, output/step/tool/time limits and trusted
   provider receipt conversion. No actual prices, dollar/token units or defaults.

AUTH owner bounded confirmation was relayed by Main for `2520bca6e86f75e54fb969c9f45a81e894561bb0`:
- Stable issuer/subject plus authorized environment maps to one budget partition;
  token timestamps, refreshes and caller scope must not create new partitions.
- Recheck before dispatch; only ALLOWED with a trusted principal permits dispatch.
- Entry UNKNOWN permits safe reads only. Unknown claim/execution/cost retains the
  original attempt and reservation for `reconcile_original`, never redispatch.
- A late receipt reconciles only its original scope; it grants no new dispatch.

This confirms these AUTH consumption semantics only. BASE uses the actual field
`recovery` (verified in the fixed OpenAPI); final outcome mappings and real
composition/configuration remain pending. LocalExit stays synthetic-only;
real Auth/host/DB/provider integration and real permission/cost acceptance are
not established by this confirmation.

## State and idempotency

`Command` binds attempt ID, operation ID, run ID, kind, original input SHA256,
reserved integer units and output ceiling. Input digest must cover all immutable
provider/model/tool inputs; compute inside future trusted composition, not accept
an unverified caller digest. No prompts, tokens, secrets or provider bodies stored.
Same attempt + exact command returns prior record; changed input conflicts.
Different attempts consume additional limits. Counts are cumulative per run,
including cancelled attempts (conservative; cancel cannot reset loop limits).

`reserved -> unknown -> settled`; reserved can instead become `released` on run
cancellation. Claim is durable and one-shot BEFORE execution. The unknown state
also covers the crash window after claim but before actual call; never automatically
retry an unknown attempt. An exception or timeout holds its full reservation.
Cancellation releases only unclaimed work; in-flight unknown remains held. A late
trusted receipt may settle cancelled/expired work but must not publish/revive its
result. Read query remains possible after cancellation and deadline.

Receipt binds attempt/receipt ID, unit, actual units and output. Exact repeated
receipt returns original result, differing receipt conflicts, receipt reuse across
attempts conflicts. Real receipts must come from a trusted adapter/reconciliation
source, never client billing values. Synthetic tests do not establish actual fees.
A cost/output overrun records the full actual amount, marks exceeded and stops the
run; it is never clipped into a false within-budget success. Future providers must
honor reservation/output caps before claiming strict real-spend bounds. No unknown
cost is converted to zero. Same unit required; no conversion or guessed price.

## Limits and persistence boundary

Configuration and clock are mandatory. All unit amounts/counts are nonnegative
integers (bool/floats rejected); reservations/limits positive. Budget period is
explicit `[start, end)`, clock is explicit finite seconds and rejects regression.
Clock must be a trusted server clock; no caller clock. Run deadline checked on
reserve and claim. Output is aggregated across the run (actual settled output plus
outstanding ceilings). Model/tool/memory foreground and background share exposure.

A repository instance represents exactly one trusted user/environment/budget scope.
Transaction must serialize the entire scope, rollback errors and commit before
returning; concurrent runs cannot independently read an old balance. Config is
bound in ledger and cannot silently reset limits. Production rollover/retention
is NOT implemented: unknown reservations must carry across period changes, and
stable IDs/run counts must not be dropped to evade limits. Do not provision a new
scope on expiry; deny until an accepted rollover protocol exists.

SQL remains a module candidate, not a registered migration. It was applied only
to fresh task-private PostgreSQL clusters. The candidate itself grants no runtime
access and keeps deny-all RLS. `PostgresRepository` now implements the protocol
using an injected new idle non-autocommit DB-API connection; it locks one entire
scope row at READ COMMITTED, validates codec/version/counters/receipt binding,
updates atomically, and commits before returning. It never creates a missing row.
Trusted provisioning must explicitly supply the initial `Ledger(config)` once;
missing state, corruption and changed config cannot reset budgets. No DSN/default
connection, role creation, policy or retry is built into the runtime repository.

`CommitUnknown` means original-attempt reconciliation only; even an exception
before actual commit is conservatively unknown until readback. Cleanup errors use
fixed diagnostics and cannot replace successful commit or the primary exception.
Tests inject commit ACK failures over real PostgreSQL connections. This establishes
local behavior, not network-partition or production failover evidence.

The private harness uses synthetic roles/policies and verifies a non-superuser,
non-BYPASSRLS runtime plus cross-scope denial. Those policies are test fixtures,
not canonical product authority. Product RLS, schema rollout, trusted provisioning,
retention/cleanup and Auth composition remain UNRUN. The test-only transaction
fake remains separate. Real server stop/start recovery and concurrent connections
are recorded in `backend/usage/evidence/postgres-tests.txt`.

`LocalExit` is a single injectable **synthetic-only** exit for both foreground and
background. Default executor is absent and rejects before reservation. It contains
no network, provider credentials, real-provider enable switch, route or auth stub.
Injecting arbitrary Python is trusted test composition, not a security sandbox.
Runtime hard timeout, streaming stop/output enforcement, authoritative revocation
and every future external exit's integration need real adapter tests later.

## Safe bilingual status candidates

| Internal state/reason | English | 中文 |
| --- | --- | --- |
| limit_exceeded | Usage limit reached. No new call was started. | 已达到用量上限，未发起新的调用。 |
| configuration_required | Usage configuration is unavailable. | 用量配置不可用。 |
| run_stopped | This run is stopped; existing records remain available. | 本次运行已停止，已有记录仍可查询。 |
| unknown | Usage is awaiting reconciliation; do not resend. | 用量待核对，请勿重新发送。 |
| released | Unstarted work was cancelled and its reservation released. | 未开始的任务已取消，预留额度已释放。 |
| settled | Usage was recorded from the receipt. | 已根据回执记录用量。 |
| provider_disabled | External calls are not enabled. | 尚未启用外部调用。 |

These are domain copy candidates, not official wire errors or financial statements.

## Reproduce

`cd backend/usage && uv run --offline --frozen python -m unittest discover -s tests -v`

All amounts in tests are **synthetic-unit**, not USD, token prices or measured
provider fees. See `backend/usage/evidence/core-tests.txt` and `README.md` for exact
local coverage and remaining UNRUN layers. Issue9 remains open.
