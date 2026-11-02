# CJ-LOCAL-CLEANUP@2 — explicit C account-hook host composition

Additive local host configuration. The HTTP API@1, DEVICE@1/2/3, CLEANUP@1.0/1.1,
CJ-LOCAL-CLEANUP@1 and manual Configuration paths retain their semantics.

The JSON has exactly the same five keys as V1, with version2 explicitly selected:

```json
{
  "version": "CJ-LOCAL-CLEANUP@2",
  "key_file": "operator-provided-private-key-file",
  "key_id": "operator-provided-key-id",
  "lifetime_seconds": 3600,
  "inventory": ["the-independent-complete-leaf-inventory"]
}
```

The placeholder inventory is not a usable production manifest. Supply the same
independent complete inventory as the actual registry, including unavailable
device/external obligations. The loader preserves its exact list, key validation
and registry path; it does not derive, filter or shrink it to available hooks.
The existing key must be an owned mode0600 regular no-follow32-byte file. No key,
account, resource, permission or deployment is created by loading configuration.

Version2 selects the single code-owned factory
`cj_memory_withdrawal.account_cleanup.account_hooks(store, owner_scope)` from
C's ACCOUNT-CLEANUP-V1 contract. There is no configurable import path or plugin
selector. A missing dependency fails; it never falls back to V1 or an empty map.
V1 still leaves extra_hooks=None. Manual Configuration.extra_hooks remains explicit.

The same load_configuration function is consumed by actual app_from_environment
(CJ_LOCAL_CLEANUP_CONFIG) and cleanup_worker.main (--cleanup-config). Runtime's
existing binding appends the factory's exact three C targets to its B hooks:

- business/memory-management-actions
- business/memory-authoritative
- business/trip-authoritative

Existing memory-derived, message, Run/background, needs, usage, feedback, device
and cleanup-metadata hooks remain. No target is removed, replaced or silently
confirmed. Original retirement, physical-worker/usage preflight and dependency
order remain the existing B orchestration. The worker reconstructs the same
original binding; UNKNOWN only reconciles the original result, not redispatch.

Use only after C's hook implementation and registered local M41 are available.
These are account-only hooks; they do not implement #26's memory-item descriptor
or payload deletion. C owns scope locks, bootstrap fence, erasure, original results
and minimum column permissions. Ordinary organizer/runtime never receives cleanup
credentials. Local/private PG authorization does not enable cloud or real accounts.

Verification separates the full configured host from physical component evidence.
The full30-target registry/inventory stays intact and an unprovided external
obligation blocks before retirement. C's supplied account-hook fixture, with its
explicit component registry, is run through the real V2 loader to audit physical
C erasure/Bob preservation and original/race behavior. The actual worker main is
also exercised with the full configuration. Neither component nor installed hooks
are evidence of all-device, backup, external-provider or whole-account completion.
