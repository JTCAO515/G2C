# Protected original usage association read

Parent/source base: 414e5c19d8470ac2fbdc645ddfaedeee8dd6039f. Original
414 display code, historical FAIL logs, SQL and owner worktree were clean and
retained. This slice changes only backend/run/** and contracts/run/**.

## Exact public source interface (not yet root wire)

```python
from cj_run.original_usage_read import (
    OriginalUsageAssociationReader, UsageAssociationReadConfiguration,
)
reader = OriginalUsageAssociationReader(
    message_boundary, resolve_run_repository,
    configuration=UsageAssociationReadConfiguration(max_response_bytes=EXPLICIT),
)
body: bytes = reader.read(token, original_message_id)
final_body: bytes = reader.read_projected(token, original_message_id, project)
```

Only token and original message ID are request inputs. The trusted host resolver
has signature `(current_trusted_principal, current_trusted_scope) -> Repository`,
where Repository is exactly the canonical cj_run.postgres.Repository. Environment
and storage mapping are server configuration; caller scope, attempt, period,
unit, principal or run ID cannot configure this reader.

project is trusted synchronous host code: verified minimal bytes -> final validated
encoded envelope bytes. It receives no context, repository, State, UsageBinding,
input bytes or digest. CJ005 validates its generated model and server request_id /
complete body INSIDE project. It then sends these exact returned bytes without
post-context decode/re-wrap. Header/no-store and formal wire are CJ005's scope.

## Whitelist and semantics

The inner JSON has exactly seven fields:
`conversation_id`, `generation`, `message_id`, `message_sequence`, `run_id`,
`attempt_id`, `operation_id`.

The first five come from the original authenticated MESSAGE receipt (sequence ->
message_sequence), with run ID verified against the original stored Command. The
last two come from that RUN row's immutable canonical Command, not a login
attempt, synthesized identifier or caller value. Internal scope never leaves the
reader. Neither do original raw input, usage_input_bytes, command bytes,
input_digest, reserve/output limits, kind, period, status, effects, event values,
text or any other private metadata. This source does not call Meter.query, claim,
reserve, settle, cancel, or any RUN mutator.

An association is not evidence of a USAGE ledger row, reservation, dispatch,
execution, fees or current status. A committed association may remain readable
when RUN status is unknown; it grants only original reference discovery, never
retry/dispatch. Uncertain association reads/commit/cleanup fail, not a guessed
association or successful null. Missing message/RUN/association, legacy unbound
rows, malformed bytes/fields/hash/run linkage, expiry or changed source all fail.
No missing association is backfilled and no new attempt or RUN is created.

## Audited actual source and producer limitation

- Service.accept_with_usage / Transaction.accept atomically insert the original
  Binding and UsageBinding into one existing RUN row before any synthetic reserve.
- candidate.sql pairs nullable usage_command_bytes + usage_input_bytes; original
  binding trigger prevents updating original refs/association or backfilling NULL.
- UsageBinding requires original bytes, the seven canonical Command fields,
  duplicate/unknown-field rejection, IDs <=200, valid kind/digest/positive ints,
  and SHA256(original complete outbound input bytes) == input_digest. It never
  assumes that digest equals MESSAGE input_sha256.
- canonical recovery reconstructs State from contiguous stored events and validates
  the original row; the new reader revalidates the exact association's bytes/hash
  and run ID before deriving the whitelist. It reads again before publication.
- In this audited module source, the only executable producer consuming
  accept_with_usage remains SyntheticFirstStep.create_fixture. There is no real
  dispatcher/worker producer linked here. This is a valid persisted-source read
  candidate, NOT proof of production association creation or real execution. No
  synthetic association is silently inserted to make an account appear supported.

## Lifetime, strict close and final callback repair

The actual fixed MESSAGE bf79 Boundary.with_history_context creates the context.
ctx.query_message validates original raw/receipt under current AUTH and scope.
Only that callback's principal/scope and original receipt build the complete RUN
Binding. After resolving the canonical repository, the reader checks original
source and freezes the selected scope/connect/expiry/timeout object fields.

Canonical Repository.recover gains an optional `require_clean_close=False` flag.
This reader explicitly uses True: recover commits and closes both resources, then
withholds on cursor/connection close failure. Read cancellation is propagated.
Legacy callers retain the default behavior; their already accepted close semantics
and nine-field display wire are not changed by this slice. Close errors are fixed
safe diagnostics, never private SQL/credential/byte logging.

Order: original source -> exact stored association -> whitelist/project/final byte
bound -> second canonical strict recovery and full result/association comparison
-> current original source check after its storage/close callbacks -> outer
MESSAGE final AUTH callback and original context retirement -> **callback-free
publication check** -> return exact bytes.

The final check uses only direct object fields from the selected canonical
repository and frozen reader/configuration. It compares reader boundary/resolver /
configuration identities, configured byte limit, and repository scope/connect /
expiry/statement/lock timeout references. It calls no checker, resolver, SQL,
projection, context property or external callback. The retired context is never
revived. This explicitly avoids the known USAGE last-AUTH-callback P2 publication
window, whose original FAIL evidence remains in its original owner's tree.

Sequential source reads are not a new distributed transaction or revocation
protocol; data can change after a completed read. Trusted injected Python is not
an adversarial sandbox. Current authority remains solely MESSAGE/AUTH and the
server-owned storage mapping; no extra principal, boolean permission or policy.

Nonbytes and awaitable/deferred projection returns are rejected; coroutines are
closed without awaiting. Errors/cancellation propagate. Explicit positive byte
limit applies both to the inner whitelist and full projected envelope. Exceeding
it fails rather than truncating. The limit does not promise bounded database
log reconstruction/input-memory work.

## Evidence and pending work

- original-usage-read-tests.txt: 12 targeted groups PASS on Python3.14.7 using the
  actual fixed AUTH AdmissionChecker + MESSAGE Boundary/query_message and exact
  canonical RUN Repository/Transaction/codec over injected DB-API callbacks.
- Positive original refs and complete final envelope; no private sentinels; no
  SQL DML/mutator; missing/corrupt/foreign identity/full Binding/old generation /
  inactive/expired; source/association/epoch changes; project reentry/deferred /
  exception/cancel; connect/cursor/execute/fetch/commit/close failures.
- Last outer AUTH callback changes scope/connect/config/resolver/boundary/expiry /
  timeout or frozen limit: all withhold. Test confirms there are exactly four
  post-close provider callbacks, then publication uses no new external callback.
- original-usage-recovery-compat.txt: six existing affected transaction lifecycle
  checks PASS; original-usage-display-compat.txt: one actual old read/projected
  nine-field compatibility case PASS. No unrelated suite rerun.
- Prior RUN usage-known-gap.txt and p2-before.txt FAIL evidence is byte-identical
  to parent. display_snapshot.py and candidate.sql unchanged. Existing producer,
  core/USAGE/private-PG evidence is reused only in its original bounded scope.

```sh
PYTHONPATH=backend/run:backend/message:backend/auth uv run --offline --no-project --with psycopg==3.3.4 python -B backend/run/tests/original_usage_read_checks.py
```

The existing cached Python environment includes psycopg; tests create no sockets,
servers, providers or live accounts. No old PG instance was restarted, no DB was
applied/rebuilt, no network/resource/payment/permission operation occurred.
Independent Review/Testing, root generated wire/header/no-store integration and
real account/worker acceptance remain pending/UNRUN. Shared real dispatch fence
remains unimplemented and disabled; Issue11 stays open.
