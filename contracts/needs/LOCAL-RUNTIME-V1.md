# CJ-LOCAL-NEEDS@1 — explicit manual runtime

Local runtime only, owner B / #305. Set CJ_LOCAL_NEEDS_PROFILE=manual-v1 to enable
the existing four frozen NEEDS HTTP methods in the existing canonical local app.
Missing profile preserves the old closed endpoints; unknown profile fails closed.
Existing HTTP shapes/Command grammar and NEEDS@1.0 data versions are unchanged.
No production/real identity, model, cloud or credential/resource approval follows.

Manual create/correct/read/revision/original-action recovery do not require a
paid-model quota context. When @2 is configured, its period/ledger remain intact;
manual edits neither spend nor reset provider_call units. Model preview is separate
and requires the explicit registered @2 worker/Meter profile.

Canonical principal maps to the existing local message scope, then `n` plus SHA256
of that scope for NEEDS. No client owner/scope/provisioning argument is accepted.
Only the first actual manual act may provision its own empty scope, in the same
transaction as record/history/receipt. GET/projection never provisions a scope.
Absent scope is unavailable, not proof of a missing/rolled-back original action.

The new RuntimeRepository uses the legacy SQL/CAS/exact-byte receipt/history
implementation. Its transaction entry installs LOCAL owner settings on a fresh
validated runtime connection, takes the existing exclusive NEEDS advisory fence
**before** any row/write, and uses a plain scope SELECT. It needs no scope UPDATE
permission/SELECT FOR UPDATE. Existing legacy Repository setup/default behavior is
retained for its original consumers; no accepted safety check is removed.
All canonical entry/transaction/commit/serialized-return checks remain. Strict
close failure withholds output; possible commit always reconciles the original
action, never a new ID, automatic retry, fake rollback or compensation deletion.

The appended local migration grants only INSERT on scope/record and the explicit
revision input columns, plus record(version,content) UPDATE. Existing forced RLS,
immutable scope/write triggers and source constraints remain. No DELETE/TRUNCATE,
new role, BYPASSRLS, SECURITY DEFINER, mutable history or recorded_at INSERT grant.
Write policies additionally require transaction-local `cj.needs_runtime_abi` =
`NEEDS-MANUAL-RUNTIME@1`, installed only by the explicit new writer. The old scoped
runtime therefore retains its tested read-only behavior; an ABI marker alone is
not identity or permission. Fresh checkout/transaction entry rejects retained ABI
settings, and LOCAL removes them on commit/rollback.
Its down refuses any retained NEEDS scope/record/revision before revoking rights;
applied old migration bytes are unchanged. Disable the new producer to roll back
behavior while retaining recognized records, consumers, original actions/history.

For C's protected consumption, use `cj_api.local_needs.protected_reader(database,
checker)`, then its unchanged `read(token, fixed_projector)` lifetime. The resolver
requires local environment, derives current canonical scope, and uses a new
ReadOnlyRuntimeRepository with READ ONLY/shared NEEDS fence/plain SELECT, no writer
permission or scope provision. Encode NEEDS@1.0 snapshots/revisions inside that
lifetime. Read bytes alone are not a global atomic currentness/publication lease.
Without a registered @2 context, explicitly construct the local database with
`needs_context=True`; an unconfigured NEEDS scope is unavailable, with no fallback.
Do not nest a new NEEDS connection under an already-held publication lease; read
and evaluate first, then use the original RevisionLease/current captured reference
for the final publication path. No lease is held over model IO.

MESSAGE-send.2 consider_trip uses the explicit owned/current needs_reference, not
the old conversation selector. The original RUN→NEEDS→TRIP publication protocol
is retained across actual proposal plus RUN commit: correction first rejects the
old result; publication first commits its original proposal/receipt before the
manual correction. New record versions are never overwritten by old runs.
No proposal is automatically accepted as a formal Trip. A's display/correction
client and C's FEAS combination remain separately owned acceptance.
