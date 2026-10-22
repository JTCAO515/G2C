# CJNeedsClient — NEEDS client candidate

Embeddable iOS 17+/macOS 14+ SwiftUI components for explicit journey needs and
corrections. This package baseline is not the product's minimum OS decision.
Issue: [CJ-013 / original #14](https://github.com/JTCAO515/G2C/issues/14).

## Fixed inputs

- Main base: `2ca62479d82c761272c4ad3f8357467f9e5eba8c`.
- Separate unmodified dependency preparation: `7fe71617e4d4c6ef15c658532f3909edeec87865`.
  CJMessageClient subtree from `165a0c0137e9baa59c1cf93df7a67d342b6d5b6a`;
  CJAuth subtree from `668d96b8e22227160991e2416dc547dacf12246b`.
  Those dependency commits' independent gates remain separate. Their imported
  source, tests and historical evidence are not NEEDS-authored changes or new
  Keychain/host acceptance. Do not publish this preparation wholesale as product work.
- Formal API `d688c01dc0fb18488a1e9c49414a039ce0126204`, using the sole shared export at
  `../CJMessageClient/.generated/d688c01dc0fb18488a1e9c49414a039ce0126204/CJFoundation`.
- Producer: `c821b34d607016c6dbc1020c203621841f1a60e8`.
  API author's real-chain evidence `a624cca6a3572c9a54adcc634311b1064d499a3d`
  is referenced, not repeated or represented as this author's independent run.
- Encrypted append-only storage pattern adapted from CJTripClient
  `12df1c1590174ab327d7d01782d736bd20ec199c`; only this domain's implementation is added.

## Host surface

`NeedsClient` requires a trusted endpoint, credential callback, current local
binding, existing `SessionLifecycle` and its original `SessionOperation`.
`NeedsBinding` is host lifetime metadata, not caller-supplied backend scope.
Public construction allows reads through the existing `NoRedirectTransport` and
**always disables POST**. The intercepted write transport is module-internal,
used only by `@testable` synthetic tests. No caller boolean enables live writes.

`NeedsPresentation`, `NeedsClientView`, `NeedsDetailsView` and `NeedsEditorView`
are public components. CJ006 owns shell wiring. Replace the model binding
synchronously before account/environment/selection lifetime changes. A language
change should retain the same model. The host supplies the selected NEEDS ID;
there is no assumed trip, city, date, amount, source or provider.

Capture work at the button or lifecycle event, **before** queuing its Task:

```swift
model.replace(binding: trustedHostBinding)
if let work = model.prepareDetail(id: selectedNeedsID) {
    Task { await model.perform(work) }
}
```

The same prepare/perform rule applies to `prepareRevision`, `prepareQuery` and
`prepareSave`. Work is opaque, owner-bound, one-use, and retains the original
binding/selection. New work revokes older work. Every external credential,
binding and key callback is followed by ownership checks. Old completions or
errors cannot adopt a new target or overwrite its UI state. Cancellation settles
reads to cancelled and possibly dispatched actions to unknown.

A trusted host can explicitly start new local input with `beginNew(id:)`, or
use the loaded snapshot's draft. `NeedsDraft.freeze(actionID:)` creates an
immutable official `NeedsCommand` encoding once. The source statement is actual
user text; no extraction is fabricated. Re-reading latest detail preserves an
existing draft and its original expected version. After an explicit user review,
the host may replace `model.draft` with a new draft based on the chosen current
snapshot; this is never automatic CAS retry/version substitution. The source
binding, real collection policy and actual save activation are still unconnected.

## Semantics

- Omitted fields differ from explicit missing, unknown, uncertain and known.
  Only fields the user edits are included in `NeedsChanges`; no empty questionnaire
  is filled with null, zero, dates, or inferred party size. Nested events and
  collections follow the fixed whole-field replacement contract. New event parts
  need explicit states; the optional "mark unrecorded details missing" button is a
  user action, not a default. Explicit empty collections remain different from absence.
- Money remains decimal text, including trailing zeroes. No exchange, averaging
  or implied paid amount. Local date/time are strings; the device timezone never
  transforms them. Timezone strings retain the fixed wire nonempty constraint; only the producer
  validates IANA membership. No device timezone list or alias rewriting is used,
  and no instant or DST resolution is synthesized.
- Companions, applies-to subjects, locked intent, user booking claims and temporary
  conditions remain explicit. A user claim is never supplier verification. Server
  resultant-reference validation may reject a partial removal; no related fields
  are silently changed to make it pass. No Memory/Trip writes or solver results.
- Receipt has no input hash. Both POST success and original-action query must read
  the receipt's exact public historical revision, check identity/version and compare
  its base64-decoded original input **byte for byte**. Latest detail is never proof.
  Null/error/invalid oneOf remain unobserved or failed; they do not permit a new ID.
  Every persisted original has at most one POST attempt, even if the attempt failed
  before transport. Reopen is query-only until the exact original is reconciled.
- The original body and ID are encrypted with the existing same account/environment
  `localNeedsPendingV1` key before outflow. Lookup only: no key creation, replacement,
  plaintext fallback or cleanup. Records use exclusive append, fsync, canonical
  directory identity and a final callback-free exact ciphertext durability check.
  Confirmed originals remain on disk; no retention/deletion policy is invented.
  No claim is made against arbitrary hostile same-UID filesystem races or backup rollback.

## Reproduce locally

Prepare the already-fixed shared export in this isolated clone (do not create
another CJFoundation package):

```sh
python3 ios/Modules/CJMessageClient/scripts/prepare_generated.py /path/to/cj-005-foundation
swift test --package-path ios/Modules/CJNeedsClient
cd ios/Modules/CJNeedsClient
xcodebuild -scheme CJNeedsClient -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath .build/ios CODE_SIGNING_ALLOWED=NO build
python3 evidence/check_producer_fixture.py /path/to/cj-013-needs
```

The package locks its own resolved graph; other modules' locks are untouched.
Tests use only synthetic bindings/key persistence and intercepted HTTP. The public
no-write test constructs the existing URLSession transport but proves rejection
before credentials, persistence or dispatch. No product network request is sent.

See [evidence/REPORT.md](evidence/REPORT.md) for exact checks and limitations.
