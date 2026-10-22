# Process-local once-only action authorization candidate

Delta parent c79da94c94315dd3b63db0fcc001dda3afa7403b. Same Issue10 safety fix;
no external ledger, service, schema, key change, file deletion or live POST activation.

## Rule and stress result

Persisted phase staged is not authority. All loaded staged records become queryRequired;
other restored phases also have no send permit. Only stage of a genuinely new-to-this-
process original action can mint a PRIVATE FreshAuthorization AFTER successful save.
The authorization binds current instance/activation lease and original body digest,
lives outside Snapshot, is not Codable and has no public initializer/export/import.
It is consumed BEFORE saving the send-intent transition, so injected synchronous store
callbacks or overlapping async transport requests cannot consume it again. Any
invalidation destroys permits. Repeating stage of an existing record does not remint.

A process-local denial-only observed set remembers IDs and body hashes per exact
account/environment binding across coordinator replacement and account switching.
It records before the first save attempt and when loading records. Thus clearing or
copying a snapshot cannot make an already observed ID or original body fresh in the
SAME process; a replacement ID with the same bytes is also refused. No clearing API,
TTL eviction or granting behavior exists for this memory. It is not persisted and is
not a new AUTH or durable ledger authority. Long-session memory budgeting remains a
host concern; silently evicting it to regain permission is not an accepted solution.

The state layer rechecks the captured lease after synchronous storage callbacks too.
An old save may have affected its explicitly bound old partition, but cannot overwrite
new in-memory account state. If old save fails after a callback activates another scope,
it must not invalidate that newer lease. Unknown save consumes/no longer grants fresh
permission; no blind retry or silent success is introduced. Drafts remain independently
editable without modifying original actions or their permissions.

## Before/after evidence

New pressure tests first reproduced 3 failures / 1 pass on the previous implementation
(evidence/fresh-before.txt): cleared snapshot restaging/new coordinator re-key, synchronous
submission reentry, and unknown save followed by empty snapshot restaging. Copy/decode
of staged Snapshot was already query-only and remained passing.

Final Swift6.4/macOS targeted checks:
- 5 FreshAuthorizationTests +1 RollbackTests +9 affected RecoveryTests PASS.
- 12 affected TransportTests PASS (same run evidence/fresh-after.txt).
- 1 additional overlapping asynchronous submit test PASS (fresh-overlap.txt): exactly
  one fresh authorization and one intercepted request. No real HTTP call.

Tests now allocate independent synthetic environment UUIDs rather than pretending that
independent stores are the same real identity/partition; this avoids deliberate process-
wide denial memory crossing unrelated test scenarios. Within-scenario same identity,
rollback and replacement-coordinator cases remain intact and explicitly tested.

## Unsolved cases and live activation remains unavailable

If an entire action record is removed/rolled back BEFORE a new process starts, this
process has no evidence it ever existed. It cannot distinguish a new intent from a
replayed one. If an actor changes BOTH ID and body, semantic equivalence also cannot
be established by exact byte/ID comparison. No guarantee is made against malicious
host code or separate concurrent processes; single-writer ownership remains required.
There is no safely inferred account/environment remapping either.

An independently non-rollbackable original-action/epoch source and its exact lifecycle,
unknown-write, retention and restore contracts remain the required material before
production sending. No such source is currently available. Therefore BOTH existing
live gates remain unchanged: MessageHTTPClient liveReadTransport rejects submit before
credentials; NoRedirectTransport rejects POST before URLSession sends. Named test-only
interceptors are the sole execution seam used here; they are not product activation.

Query null does not grant permission. No new key, cleared file, rewritten payload or
new ID is used to erase uncertainty. Old valid encrypted records and all prior evidence
are preserved. True host/Keychain/service/device/anti-rollback acceptance remains UNRUN;
this is a locally testable fail-closed candidate, not a claim to solve rollback globally.

Activation reentry correction: evidence/ACTIVATION-REENTRY.md documents an independent
load-generation check so old activate cannot replace a callback-activated account or
reactivate after invalidation. Four targeted cases pass; no new send authority is granted.
