# RUN-USAGE-OPERATIONS@1 — original registered operations

Issue #242; JT scope approval6497345414, design revision2 reviewed before
implementation. This additive private ABI does not change STEP-BINDING@1,
MESSAGE-send.1, public RUN fields or migrations1–16. Producer stage only: consumers
and business integrations remain UNRUN until their own evidence is recorded.

## Identities and persistence

The accepted origin in this slice is an original MESSAGE-backed RUN. The trusted
host derives its Binding from the authenticated owner's original receipt; caller
principal, scope, ledger, attempt and a cached ALLOWED value are not authorities.
A future background origin needs its real producer/owner contract, never a fabricated
message or identity. Supporting the memory kind is not proof of a background job.

- `cj_run_metered_binding`: one immutable `(scope, run_id)` binds the original
  ledger, unit=provider_call and explicit period. Its source_abi is exactly
  RUN-USAGE-OPERATIONS@1. Canonical ledger ID is the existing compact UTF-8 JSON /
  SHA256 mapping; a DB CHECK also rejects mismatched scope/period/account pairs.
- `cj_run_metered_operation`: one immutable `(scope, run_id, operation_key)` contains
  registration_id, kind (model/tool/memory), attempt_id, operation_id, command_bytes
  and input_bytes, and references that RUN's fixed ledger. Attempts and operation
  IDs are unique within scope, including across periods/RUNs.
- The host owns stable operation keys. The two current model positions are stable
  logical phases; a retry cannot substitute a fresh random key. A future caller
  must prove stable logical-position provenance when it registers.
- command_bytes encode the canonical seven Command fields. input_bytes preserve
  the exact registered adapter's credential-free outbound input; SHA256 equals
  input_digest. Target/model/options that affect execution belong in that adapter's
  input ABI. Tokens, authorization headers and server keys never belong here.

Creation holds original RUN ownership/fence, verifies current original authority,
creates or verifies the RUN partition, inserts a NEW operation and obtains positive
commit acknowledgement before returning a prepared invocation. Existing-key replay
is read-only reconciliation even when bytes match. Changed bytes/kind/registration,
wrong period, hidden old rows, unique-key conflict or uncertain ACK never mint a new
attempt or authorize execution. This is an association, not another quota ledger.

Persistent bytes, version and redundant columns are validated once at repository
read boundaries against canonical Command and original input digest. Internal
consumers trust the resulting immutable value; they do not repeatedly deserialize
or replay its validation. Each fresh mutable AUTH/currentness/clock check remains.

## Activation and old consumers

`cj_local_metered_profile` records a sticky operator-owned registered-exit.1 scope
profile, anchored to existing M1 protection. Its INSERT trigger locks MESSAGE scope
and refuses first activation if ANY unacknowledged delivery (including inactive
chats) or queued/running RUN exists. It uses ordinary RUN reads, not a reverse RUN
write lock. Existing profile insertion is idempotent, not a second activation.
Operator code calls this boundary rather than duplicating its idle-work checks.

New-mode receipts have only `cj_message_metered_requirement` (registered-exit.1),
in the same transaction as receipt/NEEDS/outbox. Historical M1 requirements remain
unchanged. Deferred SECURITY INVOKER constraints require the new marker on every
new receipt in an upgraded scope and reject new M1 markers there. No marker or
mixed markers rolls back the whole acceptance transaction.

A previous M1 host cannot read a new execution requirement from its old table and
must refuse before RUN acceptance; its old writer cannot commit a new M1 receipt
in an upgraded scope. Safe original history is not dispatch authority. Upgrade
requires stopping unsupported binaries; this is not a sandbox for arbitrary code
or administrator SQL. Fixed previous-consumer probes must be labelled accurately.

## Permissions, deletion and rollback

All four new tables have ENABLE/FORCE RLS. Runtime has SELECT on profile and
SELECT/INSERT on requirement, binding and operation. Profile/requirement use the
nonempty MESSAGE scope; binding/operation require both MESSAGE and original USAGE
scope. No UPDATE/DELETE/TRUNCATE, no role attribute changes, no old RLS/ACL edits.

RUN deletion cascades new binding/operation private data; original receipt deletion
cascades its new requirement. RESTRICT relationships prevent removing protection
before its remaining origins/associations. These inherit existing parent deletion
authority, not a new user deletion API. Cleanup integration and currentness fences
must prevent revival; schema cascade probes alone are not whole-product cleanup.

Migration0017 creates new objects and guards; it does not backfill or rewrite old
operations. Empty up/down/up is required. Any new profile/requirement/binding/operation
makes down refuse. Retain original records and periods on code rollback; never
remove markers to allow an older executor to run new work.

## Positive / negative examples

| Input/action | Required result |
|---|---|
| New model/tool/memory operation, owned origin, matching registered descriptor and fixed RUN ledger | Persist one original association; execution still needs positive claim and current fence |
| Same key/bytes reconstructed in another process | Read original only, no renewed dispatch permission |
| Same key with another kind, digest, adapter or attempt | Conflict/unavailable; no quota or provider action |
| Same RUN with a different period/account, including RLS-hidden old binding | Refuse; uniqueness/FK cannot become an empty new RUN |
| Mixed MESSAGE owner and another user's ledger tag | RLS/canonical-account CHECK refusal |
| New receipt in upgraded scope with no/new+old/old-only requirement | Transaction commit refused |
| Legacy pending or active RUN while first profile activation is requested | Refuse activation; no automatic migration or reset |
| Empty metadata schema down | Allowed |
| Populated metadata down or premature protection deletion | Refused |

Schema fixtures test these on actual runtime PostgreSQL. They do not prove tool
business execution, background origin creation, real provider cost or cloud use.
