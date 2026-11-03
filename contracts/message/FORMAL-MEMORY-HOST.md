# Explicit consumer of CJ-MESSAGE-FORMAL-MEMORY@1

This B host installs the actual C factory provided by merged PR476 for the
already-merged MSG3/Memory consumers blocked by the former missing adapter.
It adds **no wire version**: POST `/v3/messages`, MESSAGE-send.3,
MESSAGE-accept.3, MESSAGE-trip-reference.1 and MEMORY-RUN-CONSUME@2 are unchanged.
It implements SEND-V3.md's explicit-adapter condition; it never infers an exit
from that condition merely because Memory rows or a Trip exist.

## Scope and actual blocker

An actual Typed2/Travel1 owner with saved Memory cannot activate message-trip.1
under the old M26 guard, and an activated Trip1 owner with Memory cannot submit
or run the old unconfigured MSG3 producer/worker. Both failures were reproduced
with the signed APIs, restricted PostgreSQL, the genuine C factory and original
worker. No Memory is deleted/disabled to upgrade. This does not upgrade legacy
Memory-only scopes lacking the existing registered Travel1/M2 prerequisites.

The opt-in host uses C's canonical `FormalRuntimeConfiguration`, ABI exactly
`CJ-MESSAGE-FORMAL-MEMORY@1`. JSON remains C's `local-memory-formal-run.1` with
exact `version`, `collection`, `selections`; see
[the owning C contract](../memory/FORMAL-RUNTIME-V1.md). Typed2 remains the active
ordinary/Travel consumer; EditRuntime/ScopedMemory remain the active MSG4
consumers. This host is their explicit formal-discussion alternative, not a
fallback, namespace conversion or replacement of those consumers. New code uses
the latest applicable factory. No adapter or new tests are added for unused old
versions.

## Installation

1. Keep old workers stopped. Reconcile original pending/queued/running work;
   never acknowledge it merely to activate a profile. The M2 quota and existing
   Travel1 profile are required, as before.
2. For a Memory-first owner, use `scripts/message_trip_profile.py` with the
   existing `MESSAGE-TRIP-CONSUMER@1` plus `--formal-memory-run-policy` and the
   existing local `--auth-dir`. The C policy file must meet its private-file
   requirements, including mode0600. The script obtains a real fresh local
   principal through runtime-only ACCOUNT-ADMISSION@2 and calls C's genuine
   `bind_readonly` with its canonical MessageContextAuthority before activation.
3. Supply `formal_memory_configuration=cfg` to `create_local_app` and original
   `run_worker.run_once`. Environment/CLI entry is
   `CJ_LOCAL_FORMAL_MEMORY_RUN_POLICY` / `--formal-memory-run-policy`, alongside
   the existing explicit `message-travel.1` and `message-trip.1` flags. Legacy
   `memory_configuration`/`--memory-run-policy` is mutually exclusive; scoped
   edit has its own configuration. Unknown/missing/expired policy never takes a
   Memory-less path.

M46 is local runtime only and replaces only the activation trigger function.
It changes no table, column, role, grant, RLS, applied migration bytes or frozen
wire. The default guard still refuses an existing Memory scope and unresolved
original work. The only additional activation branch requires the table owner
and its transaction-local C ABI selector, set only by the explicitly validated
initializer. The selector alone grants nothing: runtime and cleanup roles cannot
INSERT/UPDATE the profile, acquire initializer membership or self-activate by
setting it. It is not persisted and conveys no source/Memory/model authority.
There is no new registry object, device journal or service-session kind.

The configured API obtains the same canonical principal/scope/guard as existing
MESSAGE, binds C for the actual owner, then inserts exactly the original MSG3
bytes/receipt/reference through the same transaction. Its response is materialized
before the final fresh account/identity guard; a possible commit plus withdrawal
returns UNKNOWN without private fields and reconciles the original receipt.
Unconfigured receive_v3 and worker admission retain their hard refusals.

The worker holds the genuine C capture/history/Memory fence before actual model
admission and final publication, including later context augmentation. Trip/none
select long-term Memory only; only an actual original Travel reference selects
its own temporary namespace. Trip IDs are never treated as Travel IDs. Existing
original queued MSG3 work keeps its IDs, raw bytes and accounting, with zero
automatic resend. MSG3 still has creation_intent=none; legal source2/MSG2 and
scoped/MSG4 entry scopes are not mixed to manufacture a successful test.

## Validation and rollback

The existing travel_message group retains all old cases and additionally runs
`probe_formal_memory.py`: exact M46 empty up/down/up restores the original
function/ACL/search_path, then the actual signed host/CLI/Fake/Meter cases run.
They cover formal/Travel/none contexts, old default rejection, original queued
work, replay, policy expiry, encode-time withdrawal/UNKNOWN recovery,
Memory-first activation, foreign owner, runtime selector spoof rejection and
populated-down refusal. Full repository gates and independent exact-head review
are separately reported in the PR; real accounts/cloud/models/native/backup are
UNRUN.

M46 down conservatively refuses any coexisting formal profile/Memory scope. Do
not delete Memory or metadata, disable triggers, use cleanup credentials or
drop the selector checks to force rollback. Existing configured consumer support
and original recovery must remain available for those scopes. Empty-cluster
rollback restores the exact prior guard, with no permission change.
