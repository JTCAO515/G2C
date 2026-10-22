# Lease-bound local recovery projection — candidate

Parent c5047f418366dcad5bff2180b2a0ae676b15ba1e. Additive CJMessageClient-only interface;
backend history/draft, CJShell, generated wire, transport and activation P2 logic unchanged.

## Exact host interface

- `localProjection(scope: StorageScope, lease: Lease) throws -> LocalRecoveryProjection`
- `validateProjection(_: LocalRecoveryProjection, scope: StorageScope, lease: Lease) throws`
- `LocalRecoveryProjection.actions: [LocalActionReference]`: messageID + local ActionPhase.
- `LocalRecoveryProjection.drafts: [LocalDraftReference]`: conversationID only.

Projection is a non-Codable point-in-time value with a private originating Lease, not
an authenticated account, server-history response, transport operation or send capability.
Host must use the existing trusted host scope/lease and validate projection after every
await BEFORE rendering/using references; on logout/switch it must clear visible copies.
Validation proves current account/environment/instance/activation binding, not that local
contents have not since changed within that lease. Re-enumerate for new phase/draft edits.
Use exact UTF8 IDs for identity/diffing; do not normalize opaque identifiers.

No raw original body, draft body, receipt, digest, key bytes/key ID, credential, timestamp
or server sequence is returned. Authorized body access remains a separate explicit call
to existing action()/draft() with current Lease. IDs and local phases are still private
metadata, not log labels or public analytics. Projection itself is not persisted or cached
by the package; consumers must not treat an old captured value as permission to display.

The current encrypted Snapshot dictionaries have no guaranteed persistent iteration
order. This first slice therefore returns a complete UNORDERED local projection, with no
paging/cursor/synthetic sequence or invented time. It does not promise server ordering or
stream completeness. No new persisted ordering schema/migration was introduced. Hosts
must not assume index stability. Storage/input budgets remain the approved host's concern.

## Safety and recovery

Enumeration validates scope/lease, reads in-memory snapshot synchronously, and performs
no dependency call, await, storage write or authorization mutation. Existing activate
still decrypts via explicit key provider and rejects missing/unknown/corrupt/legacy input;
there is no readable default store or key. Invalid draft-reference encoding is an explicit
invalidSnapshot error, not silent omission or empty history.

Loaded staged actions have already become queryRequired; listing does not mint or restore
FreshAuthorization. Current-process newly staged actions may appear as staged but their
one-use permission remains separate and private; projection does not create it. Live POST
remains closed. Snapshot rollback may hide local entries or show older phases; missing
records/empty projection are not authoritative server absence, send permission or complete
history. No external non-rollbackable authority has been added or claimed.

The existing activation/load generation fence is preserved. A load callback activating B
causes stale A activation to fail; B's projection contains only B references. Old account/
environment/instance/activation lease cannot enumerate or validate a captured projection.
No real Keychain/account or separate AUTH authority is inferred from local success.

## Evidence

Swift6.4/macOS: 6 ProjectionTests PASS in evidence/projection-tests.txt, covering reopened
reference enumeration/no new send permission/no writes/private payload exclusion; wrong
scope and old projection after switch/same-account reopen; load-callback B preservation;
malformed draft reference; missing external key; empty local snapshot plus invalidation.
All fixtures synthetic. Only these six new tests ran, prior activation/rollback/key/
transport/PG evidence reused. No Keychain/network/PG call or unrelated module modification.

Independent review/host integration, iOS device and full recovery/user acceptance remain
pending. This interface is ready for bounded host consumption, not a server history API.
