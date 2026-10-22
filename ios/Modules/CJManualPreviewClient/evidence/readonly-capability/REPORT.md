# CJ-017 fixed shared readonly capability consumption

Original candidate: `036de8de060ea8d84dc976862907ec5fe9c978c7`.
Shared input delivered by Main: `f4c17b59213828543cef042d127c56d8467963d8`
(parent3090777), imported byte-for-byte in separate local prep `287db1f`.
No descendant shared fix/evidence commits are imported. SDK identity stays c5.
This consumer's product delta is only `CJManualPreviewClient/**` after prep287db1f.
The original `evidence/REPORT.md` and 036 unavailable/failure evidence are preserved.

## Concrete host entry

```swift
// Original trusted selection: these are the SAME Trip source/session operation.
let editor = try PreviewEditor(
    trip: originalTripClient, source: originalAcceptedSnapshot,
    endpoint: explicitEndpoint,
    session: originalSession, operation: originalSessionOperation,
    credentials: trustedCredentialCallback,
    previewRequestTimeout: explicitRequestTimeout,
    previewResourceTimeout: explicitResourceTimeout)
ManualPreviewView(editor: editor, language: .chinese) // or .english

// A custom host calls this synchronously at its original Preview click:
let work = try editor.preparePreview()
Task { await editor.perform(work) }
```

Timeouts must be positive finite values and have no default. No new URL, identity,
credential, SessionOperation, accepted source or empty validation callback is created.
The editor creates the existing shared `readOnlyManualPreview` transport for each
immutable original work. Its mandatory validator captures that original source,
session, editor lifetime, draft revision and work ownership. The editor also rechecks
immediately after the factory callback, then retains its own independent outer
transport, generated-model validation and final response settlement guards.

The old `liveTransport:` initializer remains compatible. Passing a generic default
NoRedirectTransport still refuses preview POST. No blanket write switch was added.
The new explicit constructor enables only the shared official readonly operation;
Trip action/save, PUT, expanded paths and query scope remain forbidden.

## Actual results

- **PASS**: complete affected consumer suite: 24 test functions / 48 cases including
  parameterized inputs, in `tests-after.txt`. Existing 18 functions / 39 cases still
  pass; six new functions / nine cases cover exact fixed consumption.
- **PASS**: final no-signing generic iOS Simulator SDK module build:
  `xcodebuild -scheme CJManualPreviewClient -destination 'generic/platform=iOS Simulator'
  -derivedDataPath /tmp/cj017-manual-preview-ios CODE_SIGNING_ALLOWED=NO build`.
  Original output `ios-build.txt.xz` ends BUILD SUCCEEDED.
- **PASS**: `git diff --exit-code f4c17b5 HEAD -- ios/Modules/CJMessageClient` and same
  check against Tripf931d583: both exact owner bytes. This owner only imports fixed
  dependencies as prep; it does not author shared/Trip changes.
- **PASS**: c5 Package/Package.resolved unchanged from036. Existing single-SDK graph
  evidence is reused; no second SDK/export or new library was introduced.
- **FAIL preserved then repaired**: first new NFD assertion incorrectly expected a
  no-op request's base64-contained title to appear in plaintext. Fixture now explicitly
  selects the original NFD title, so both the generated plaintext field and exact
  original-content base64 are checked. No production code/guard was relaxed. The
  initial failure output is retained in `tests-first.txt.xz`.

New checks run the actual generated c5 Client through this editor's checked transport
and the actual shared NoRedirectTransport capability branch, with only its existing
internal in-process transport initializer under @testable. The required validator is
the editor's REAL original-work guard, not a no-op; all three shared validation points
are observed. Frozen outgoing UTF8 matches work.bytes exactly, original NFD/content/
version remain unchanged, and returned can_save stays false. No fake accepted handle
or alternate wire/patch implementation is introduced.

Additional cases: three shared validator points each invoke a real Trip currentBinding
callback that performs edit ABA; old work is denied before outflow or before result
use while the new draft remains. Shared transport await/body collection retirement,
original session retirement, factory callback source retirement, action/save/path/PUT
refusal and public explicit finite-timeout construction are checked. Default generic
transport still displays unavailable and retains input. Earlier source/diff/409/503/
can_save/projection/old-error/cancellation/settlement tests are reused and pass.

All traffic is **in process only**. No external request, actual preview network,
real credentials/account, provider, Keychain, SQL, service startup, permission change,
signing/install or deployment took place. Public explicit constructor compiles and
is instantiated without performing it; its real URLSession dispatch is UNRUN.

Shared independent Review/Testing is a separate pending gate. CJ006 actual host factory,
rendered UI/VoiceOver, real service/network, physical device, saving/confirmation,
fixed-state/feasibility and Issue22 full I are UNRUN. This source change supplies the
host-usable readonly seam; it does not open save or claim real networking acceptance.

`source-sha256.json` identifies current affected inputs. `log-archives.json` records
original SHA256/byte counts for exact-byte xz archives. Original036 artifacts remain
unchanged and attributed to that earlier candidate. No push/PR/merge was performed.
