# CJTripClient — Issue20 local client candidate

CJ Agent domain client and embeddable English / Simplified Chinese proposal,
formal-trip list/detail, and original-action recovery components. Local candidate;
not Issue20 closure, account/provider acceptance, or permission to perform live writes.
CJShell composition remains CJ006's scope.

## Fixed inputs and separate dependency preparation

- Repository base: `7b98f00e6b803d5dff351450390e490b468f00da` from local
  `cj-publish/Go2China`; source tree untouched.
- Formal producer: `5fd115fc97e542bc8776a445d8245fd272000e56`.
- API: `9dc67ced50a0cb7611a84b4adf97ab0b43c88bea`, source wire implementation
  `e40d703118fa647a28ddcb8c42c110499ccaba39`; `backend/cj_api/TRIP-WIRE.md`.
- Single official CJAPI export owner: CJ009
  `4fb05cc1f28382c5a4e97efdd833d5f079997c96`.
- CJSession: base's `ab37bae6f91796f9156e29a18213eb250f3fda0c` behavior.
- Trip key purpose: CJ007 `6fe045cf9c6851eb4076a31da20eea0eb6aed10c`,
  `MessageKeyPurpose.localTripPendingV1` / `local-trip-pending-v1`.

Local preparation commits `530d32b` and `2530a6e` only import owner-authored
fixed dependency bytes; they are **not product changes to publish**. Product diff
starts at `2530a6e`. Only `ios/Modules/CJTripClient/**` is the new product.
Do not cherry-pick dependency prep over another owner's integrated module.
Publish must first consume the compatible full official shared export and Trip
key-purpose change. This module uses the same CJFoundation identity/path:

`../CJMessageClient/.generated/9dc67ced50a0cb7611a84b4adf97ab0b43c88bea/CJFoundation`

Recreate that ignored export using CJ009's fixed `prepare_generated.py` with the
fixed CJ005 repository. No generated source, date parser, root lock, or wire schema
is copied into this domain module. Dependency resolution is recorded in this
module's `Package.resolved`; no new library was introduced.

Encrypted append-only pending mechanics are adapted from CJMemoryClient
`884a070ab51653776e17f77afb8b3628fd89e994`; generic duplicate-key validation is adapted
from base CJMessageHTTP. Those modules remain unchanged. Trip's namespace, records,
AAD and file extension are independent; there is no migration from Message/Memory.

## Host consumption

Create one `TripClient` per trusted session lifetime, supplying explicit endpoint
bounds, a credential callback, `currentBinding`, original `SessionLifecycle` and
`SessionOperation`, optional `TripPendingStore`, and `NoRedirectTransport`.
`currentBinding` must return a binding **only while the host's real identity,
environment and account policy remain verified**. Session operation ownership,
a caller-supplied UUID, proposal GET, and display are not authentication or business
permission. The client checks the original session operation and binding before
and after credential/transport/storage callbacks. It never creates or restores a
session, account, key, namespace, bearer, confirmation, or server scope.

`TripBinding` includes explicit environment/account plus host generation/selection.
The trusted composition root owns these lifetimes; they are UI fences, not wire IDs.
Retain one `TripPresentation` and synchronously call `replace(binding:)` before
logout, environment/account/selection replacement, or authoritative invalidation.
This fences pending completions and empties private UI. Construct the new domain
client/presentation for a new session operation or account-specific pending store.
Language changes only replace the view's `TripLanguage`, preserving state.
Do not recreate an old operation or label an old response with a fresh binding.

Embed `TripProposalCard`, `TripListView`, and `TripDetailView` with that state.
At the original synchronous lifecycle event or button click, call
`prepareProposal(id:)`, `prepareTrip(id:)`, `prepareTrips(limit:more:)`, or
`prepareReconciliation()`. Keep the returned opaque `TripPresentationWork` before
creating the Task, then call `await state.perform(work)`. Never prepare fresh work
inside an already-queued old Task. Work is one-use and bound to this presentation
instance, host lifetime/binding, and the original proposal/detail/list generation.
The earlier candidate's no-origin async presentation methods were removed; this
is a source change for CJ006 consumption, not a compatibility shim. For example:

```swift
if let work = state.prepareReconciliation() {
    Task { await state.perform(work) }
}
```

Preparing a newer operation synchronously invalidates the old work in that lane.
`selectPending` also captures its selection generation before storage/key callbacks;
older callbacks cannot replace a newer selection in the same account. The list's detail selection and optional original-action
selection call the same domain APIs. Components contain no CJShell/navigation root
or alternate Trip source. The host decides where to place the detail/card.

`TripPendingStore` requires an already-existing private 0700 directory, explicit
limits, expected key ID and the official `MessageEncryptionKeyProvider` with the
exact Trip namespace. It only looks up the existing key. Missing/unknown keys,
changed directory, namespace mismatch or malformed ciphertext fail visibly;
there is no plaintext fallback, new-key retry, automatic cleanup or deletion.
The host remains responsible for accepted private-storage registry/retention and
cleanup integration before activation. Never provide a shared/old account directory.

## Decisions and unknown results

Public `choose` always throws `liveWriteUnavailable`; `acceptsUserActions` is false,
and both decision buttons clearly show unavailable. The real confirmation issuer
and account policy have not been provided. There is no public switch to enable POST,
no `viewed` boolean, and no public confirmation-reference input.

Internal test-only `submitFixture` accepts an immutable proposal and an exact
synthetic server-held proof reference. `TripPending` freezes five validated ASCII
strings as compact JSON UTF8, matching public Python `Action.raw()` byte-for-byte.
It is encrypted and fsynced **before** credential lookup or request dispatch. An
existing action/proposal cannot be resubmitted, even after receipt success. Multiple
clicks never create an ID; this module never generates business action IDs.

All uncertain or failed attempts remain pending. Reopening only permits
`query(actionID:)`, using the original durable action and bytes. Null means not
observed, not noncommit; no new-ID retry or latest-version inference is offered.
Before dispatch and settlement, the original record is authenticated and its exact
ciphertext is captured. After the final host binding callback, a callback-free
check revalidates the canonical directory and the same ciphertext at the original
filename. Displaced/deleted/replaced storage prevents outflow; nothing is restored,
cleared or resent automatically. This is a callback-boundary check, not a lock
against arbitrary external processes.

A receipt is checked against action/kind/proposal/hash/trip and original expected
version+1 for accept. Reject requires actual null; nonnull generated oneOf fallbacks
are rejected for receipt, version, detail and cursors. Receipt version remains
historical; formal list/detail are independently read current records.

Pending content/hash/basis/expectedVersion are preserved, as are pending facts.
Terminal candidates remain readable. Elapsed pending displays its deadline without
claiming server retirement. Rejecting a candidate is distinct from canceling RUN;
there is no generation-cancel API in this package.

The list follows C byte-order keyset semantics, exact last-ID cursors and bounded
limits. A nonempty short page still has a cursor; only an empty page ends that
traversal. No cross-page snapshot or complete-inventory claim is made.

Local files alone cannot prove absence of an old entirely deleted/rolled-back ledger.
Append-only persistence and directory fences do not solve hostile same-UID races,
backup rollback or authoritative cleanup. This is an additional reason live writes
remain disabled. No migration, production storage activation, product API network call, SQL,
Keychain access, paid provider, permission change or deployment was performed.

## Verification

```sh
swift test --disable-sandbox --package-path ios/Modules/CJTripClient \
  --scratch-path /tmp/cj015-trip-client-build
# From ios/Modules/CJTripClient:
xcodebuild -scheme CJTripClient -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath /tmp/cj015-trip-client-ios CODE_SIGNING_ALLOWED=NO build
```

See `evidence/repair-c782339/REPORT.md` for the current scoped repair and results;
`evidence/VALIDATION.md` preserves the original candidate evidence and limitations.
A simulator SDK build is not simulator UI, VoiceOver, real App or physical-device
acceptance. SwiftUI task cancellation is cooperative; state ownership is rechecked
separately so a canceled original-action read returns to unknown instead of staying
busy ([Apple task cancellation](https://developer.apple.com/documentation/swift/task/cancel())).
