# MEMORY-lifecycle-adapter.2

Additive internal lifecycle version for MEMORY-STOP-USE@1, local runtime only.
`INTERFACE_VERSION`/LifecycleAdapter v1 remain unchanged with active/disabled
receipts. `INTERFACE_VERSION_2` and immutable LifecycleAdapterV2 use the same
three callables and existing canonical with_operation machinery, adding only
withdrawn to valid receipt states. Original exact action ID/hash, original ledger
readback, materialization, one-action identity, thread/lifetime, sticky failure,
precommit/final fresh guard, rollback and UNKNOWN invariants stay identical.

Trusted local management hosts with explicit collection policy assemble v2.
Legacy hosts using the fixed v1 adapter still reject withdrawal responses before
commit/private return. Neither version grants source authority, owner identity,
publication rights, background work or permission to escape the transaction.
The owner producer still performs canonical scope/source/item/history checks.

C #270's public wire and full delivery are pending; no existing frozen schema or
V1 consumer is widened by declaring this additive internal type.
