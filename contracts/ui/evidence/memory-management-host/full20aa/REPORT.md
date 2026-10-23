# Fixed 20aa complete Shell graph — author evidence

Repair source is fixed at `58c68ae2b078ebfd3cf3b800cd7e9a032ad8f1d5`, parent fca5.
The two P2 regressions and all prior source are unchanged by this graph/evidence
increment. Review/Testing must independently accept the repair; this report does
not lift the original HOLD. The final delivery commit contains this report and
preparation script extension. Original fca5, its logs and the independent REPRO
remain preserved in history and p2/.

## Actual complete graph

`python3 scripts/prepare_memory_management_host.py /Users/jtsm5p/Documents/Codex/2026-10-21 --full`
exports `.local/memory-management-host/a74b83a198f64e0d` using exact Git objects:

| Module | Fixed commit |
| --- | --- |
| Shared CJMessageClient | cc9e2c3ba1fb8fe7582e5e4664a924b1c6b93f71 |
| Memory | ea85fe080e926b7c569883588486b8795a18d4ab |
| Auth | 4eac0ad8db0ac33c89c7cc5b88d66b58d0fd6a7e |
| Trip | b3485ef02bbe4cc9bfcebfc1f9c61a1a67670ce5 |
| Needs | e03da1b2f1c22a28da5b8c9110166108a44af936 |
| Feedback | 5548e6bd9375f4a46fa3d1a56a5fc233897a8acd |
| RUN | b1b5edf15ec84d1a1a1a4dede1b705958c9f8469 |
| Usage | 205fb479b89c7252dc2ad7587d327c578475c2fc |
| Cleanup | d749fdc3ca4a25c78e5f9cc0eba3f55113255798 |
| Manual Preview | a56105628f062e0a8b00db10f649b26751382d48 |
| Offline Trip | 8694d958ae038880cce84da70251af69cf9b9587 |

Official SDK is `20aa50ed5c8449e6026155a6151f22041dee7fd4`, validated against
shared cc9's generated-pin.json. All peer Package.swift/Package.resolved and
Sources/Tests are original bytes, without local manifest substitutions. The
actual CJShell manifest/Sources/Tests/Demo are exported from this owner. No
SyntheticShell is included in this full graph. Normal relative sibling resolution
is used, with CJ_SHELL_ISOLATED_DEPS unset. There is one CJFoundation path; all
package identities have one path. `graph.json`, `checks.json` and `inputs.json`
record paths, exact commits, all 248 byte hashes and resolved dependency versions.

Fixed main `5281beb099bd730434e04af1c11433352c329878` is inspected read-only through
the publish Git object store. Every non-owned Shell Source file (28 files,
including all six main-retained host files) is checked byte-equal to it; owned
exceptions are only MemoryContainerHost.swift, MemoryContainerViews.swift and
MemoryManagementHostViews.swift. Accepted Auth 4eac's entire Sources tree also
matches this main. Preservation hashes are in inputs.json. No main, sibling tree,
canonical backend or tracked dependency source was changed/imported into this
branch. The full graph is a clone-local build preparation, for Publish to consume
through the original owner fixed commits; it is not a separate implementation.

## Validation

- PASS: complete actual Shell package graph compiles and 19 Memory host test
  methods / 28 parameter-expanded cases pass with the REAL ShellState. Includes
  original 9 methods, 8 original management methods and 2 P2 methods. Synthetic
  intercepted reader/journal fixtures remain explicit; no client 41-test/PG rerun.
- PASS: unsigned `xcodebuild -scheme CJShell -destination 'generic/platform=iOS Simulator'
  -derivedDataPath ../../../../ios-full20aa-build -disableAutomaticPackageResolution
  -onlyUsePackageVersionsFromResolvedFile CODE_SIGNING_ALLOWED=NO build`.
  Actual arm64/x86_64 CJShell and transitive Offline/Cleanup compile. Both fixed
  original management controls/recovery and repaired presentation-lifetime views
  are included.
- PASS: public-only PublicConsumer.swift macOS and arm64 iOS Simulator typecheck,
  using actual full CJShell modules, without internal capability/selection creation.
- PASS: original Demo/DemoApp.swift links with the compiled full graph into an
  arm64 Simulator executable `.local/full20aa-demo`; no install/launch/sign.
- PASS: repeat exact preparation; all exported bytes including all peer locks
  still match recorded SHA256 after final frozen builds. SwiftPM and Xcode actual
  checkout revisions are compared to the original CJShell lock in checks.json.
- PASS: diff whitespace and Python syntax checks.

Frozen host command: `swift test --disable-automatic-resolution --package-path
.local/memory-management-host/a74b83a198f64e0d/Modules/CJShell --scratch-path
.local/full-memory-build --filter 'MemoryManagementHostTests|MemoryContainerHostTests'`.
The frozen graph resolves swift-collections **1.7.3**, original exact version.

All failures/deviations are retained, losslessly gzipped with original-byte SHA256
and byte count in logs.json:

1. Initial full graph build/tests returned PASS but automatic resolution changed
   swift-collections to 1.7.4. That attempt is NOT accepted as fixed-input proof.
   Original lock was restored in this owner's ignored export, and final tests,
   iOS build and graph read used frozen-resolution flags. The changed lock is
   preserved as resolved-drift.json; no tracked lock was altered.
2. First standalone Demo link failed from host SDKROOT plus missing coverage
   runtime when linking Xcode instrumentation objects. Final command supplied
   the Simulator SDKROOT and `-profile-generate`; final executable linked. This
   was a local command repair, not a product-source or dependency change.
3. Prior fca5 test compile/iOS visibility failures and Review P2 REPRO remain in
   their earlier evidence directories; none are overwritten by these passes.

UNRUN: runtime navigation, rendered controls/VoiceOver, simulator execution,
physical device, real account/session, actual HTTP query/POST, Keychain/probes,
DB/provider/model, next-answer/context/whole Issue acceptance, CI, independent
Review/Testing of this candidate, merge/publish/deployment. Public management
capability and root factory remain CLOSED. Source compile/link does not create
source approval, current eligibility or live write/query permission. The original
f87/main acceptance remains separate. No Issue was closed or externally updated.
