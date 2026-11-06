# CJOfflineTrip

M3 #24 App integration candidate. `SnapshotCodec.appFactoryAvailable == true` now
means the explicitly configured device factory exists; it does not authorize a
read by itself. The old isolated candidate in [offline-trip](../../../contracts/offline-trip/README.md)
remains historical and its frozen bytes are unchanged. B's original account-cleanup
operation/device receipt (parent box 4) is not an input to the four App boxes below.
No cleanup operation ID or receipt is manufactured here.

## Source and runtime gates

Only original `AcceptedTripDetailSnapshot` or `AcceptedStructuredTripSnapshot`
handles from successful protected formal GETs may synchronize. Raw response bytes
are preserved in AES-GCM; format 1 stays readable and additive local format 2
supports `TRIP-structured-read.1`. No Proposal, displayed text, file fixture or
reencoded document can create a grant. One sealed source handle cannot renew the
period repeatedly; a fresh successful GET is required.

The trusted App root binds synchronization to the actual verified account,
canonical `SessionLifecycle`/operation and the exact saved opaque SDK material.
Its hash is checked again at the storage boundary; JWT claims never grant an
offline read. The device-only WhenUnlocked Keychain anchor binds backend/account/
Trip, key UUID, minimum formal version, exact response hash, sync/deadline and
kernel boot-session/monotonic clock. `OfflinePolicy.acceptedTrip` is 1,209,600
elapsed seconds; missing policy/time/key/material or a mismatching anchor denies.
The factory allows no policy longer than 14 days.

A network-free explicit read validates this persisted pair and updates only its
local security clock anchor. It never restores business access or dispatches a
message/Trip write. The same kernel boot and nondecreasing trusted wall anchor
are required; a new boot without online synchronization fails closed. A successful online
synchronization re-anchors the clock even when wall time is now below the old
anchor (for example after the user corrects a clock set ahead), so reading resumes
after online verification; an older server snapshot is still rejected. Monotonic
elapsed time expires the snapshot even if wall time stalls. Timers only deny or
expire an already displayed snapshot and cannot renew it.

For the explicitly provisioned M4 device build, `makeReader` prepares an
App-private non-secret continuity marker and an App Group named POSIX semaphore.
It then reads only that original kernel object and sleep-inclusive
`CLOCK_MONOTONIC`; timer reads do not write files. A process restart reopens the
same marker. A missing old semaphore creates a different domain during reader
preparation, so old anchors require a fresh signed synchronization. Corruption,
kernel denial, failed exclusive creation and uncertain marker writes never grant
a cached read. The semaphore name is never recreated from a missing old marker.
No business content or credentials enter the group container.

On iOS the directory walk starts at the physical OS-supplied App home, where
the sandbox grants access. It does not request directory reads of `/` or other
system ancestors. Every App-owned path component still uses `openat` with
`O_NOFOLLOW`; outside-home paths, symlink descendants, owner/mode mismatches and
changed directory identities remain rejected.

JT approved `group.g2c.offline` on 2026-11-06 for the two specified development
identities only. The local device generator adds its entitlement/Info choice to
Debug; Release and CI receive neither. Consumers without that explicit choice
retain the legacy reader for compatibility; iOS18+ denies its former kernel UUID
interface. That path stays unavailable when the interface is denied, and can be
removed after all consumers provision the new capability and pass device
restart/resynchronization verification. A legacy anchor does not match the new
domain. Cache/anchor formats, fourteen-day bounds and identity/crypto guards stay
unchanged. Platform references: [iOS18 deprecation](https://developer.apple.com/documentation/ios-ipados-release-notes/ios-ipados-18-release-notes),
[Apple DTS guidance](https://developer.apple.com/forums/thread/110044?answerId=754364022).

Synchronization first persists a denied exact-target anchor, commits the original
ciphertext, then marks the verified pair readable. An interrupted first file write
therefore cannot leave an untracked readable/orphan target; local cleanup keeps
that denied target across reopen until physical removal succeeds.

Files use 0700 account directories, exclusive 0600 ciphertext, AES-GCM AAD and
atomic fsync/readback. iOS sets and checks Complete protection through the
opened descriptor's published Darwin F_SETPROTECTIONCLASS/F_GETPROTECTIONCLASS
commands (class A=1). Native investigation found Foundation's protection attribute
nil on iOS 17 Simulator, while these descriptor commands set/read class A correctly;
no missing-attribute fallback or weaker read protection is used. Erasure still
checks the exact root/owner/mode/links/pending state, but need not accept a weakly
protected file for reading before deleting it. Dedicated canonical `localOfflineTripSnapshotV1` keys are created only after
an actual accepted source and confirmed empty local storage; a missing key with
existing files/anchor never triggers replacement.

## App lifecycle

The existing DEBUG simulator account root enables this only with explicit
`G2C_DEV_OFFLINE_TRIP=last-sync-v1` plus account mode. Release/unconfigured roots
remain unconnected. The normal Trips page exposes a local-only offline page;
formal-detail sync performs a fresh protected GET. Structured mode uses the same
controller and its sealed structured source, existing text/schedule/place readers,
and disables map loading on the offline page. Both languages share the same bytes,
version, sync time and fingerprint; no current road/opening-hour claim is made.

Local sign-out/account selection fences display immediately, persists a denied
anchor before using #421's exact file-removal primitive, then retains the original
target if cleanup fails. `SessionLifecycle` clears the ordinary saved session as
well. Read-only reopens cannot revive that grant. Observation/storage reentry and
late identity results are fenced by their original generation.

Only the signed verification path's explicit HTTP identity denial clears a cache
on reconnect. Local expiry guesses, 503, network failure and UNKNOWN keep the
original file and deadline. A successful identity check alone does not renew;
only another successful formal synchronization does. This local behavior is not
a whole-account cleanup result or a receipt for another offline device.

## Validation

Use the canonical sibling graph: `swift test --package-path ios/Modules/CJOfflineTrip`.
`ios/App/Acceptance/check_offline_trips.py` uses signed local identities, private PG,
unmodified worker/FakeProvider and the real App. No formal Trip is injected into
the database or App. Its test-only clock offsets are explicit DEBUG inputs;
maximum-font audits use the simulator's actual system category with all AX checks.
Prior closed-factory assertions are revised to the newly authorized factory;
all source, identity, encryption, time, unknown-write and file checks remain.
Historical compile/assertion/Observation failures stay in external evidence.
Native acceptance and exact-head CI remain pending until their actual reports.
Physical device/VoiceOver and actual lock-state behavior remain L3 #29 UNRUN.


## Known temporary-write erasure (#447)

`AtomicSnapshotStore.clearLocalTemporaryWrites()` clears only canonical
`.write-<UUID>` regular single-link files in the store's already held private
account directory. Empty/partial/unreadable owned ciphertext can be erased without
key lookup or a read-protection downgrade. The separate `snapshot.aesgcm` entry
is retained. Unknown names/subdirectories/links and replaced directory identities
refuse before the first unlink; each original file inode is checked again and the
directory is fsynced/verified after removal. It never recurses or scans siblings.

A pending uncertain write still requires its original reconciliation and cannot
be bypassed by this cleanup API. The host remains responsible for retiring every
writer, validating the original device call/namespace/state/key, invoking the
fixed and residue targets, verifying all stores empty before exact-key erasure,
and recording/reconciling its original result. The primitive grants no read,
renews no 14-day deadline and manufactures no device receipt. Device/lock/full App
composition remains #27/#29; this method alone does not close #24 box4.
