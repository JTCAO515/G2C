# CJ006 Trip container candidate

## Dependency gate update after fixed container3f51ba8

**HOLD: TripClientc782 has two independent Review P2 families**, reported in `cj-review/CJ015-client-c782339/review-summary.json`: (1) queued view actions lack original selection capture and same-binding key callbacks can overwrite a newer pending selection; (2) the last binding callback may replace the pending directory before fixture POST dispatch. Main returned both to the original producer owner. Public production POST remains closed, and CJ006 has not edited producer source. Container3f51ba88f59bd41dbd983f88b30be27cf088b50e and the author positives below do not waive this dependency gate.

The host already captures queued origins and uses read-only canonical cards, but this is not a claim that all producer entry points are fixed. Added one targeted host test after the Review event: during pending key lookup, invalidate A and install a distinct B presentation; the old selection returns false, cannot navigate/overwrite B, and B can still list. `key-reentry.txt`:1 test PASS. The prior102-function run and iOS build remain valid for unchanged product source; only this test/evidence was added. The case covers root binding replacement, not the producer same-binding selection or final directory dispatch bugs.

Next dependent step: consume the original owner's exact repaired TripClient fixed commit, preserve container source and old evidence, run affected origin/recovery checks and final graph/compile only as needed. No real credential, Keychain, PG, network, App/device or permission action is needed/authorized by this gate.

Starting clean fixed cd09d04a3e4e969b5b802ecd7fc7f6c5528918fb; Memory40cc and clear480 preserved. Imported exact owner changes only:

- AUTH6fe045cf9c6851eb4076a31da20eea0eb6aed10c → local f9b414a (Trip purpose only).
- TripClientc782339b6c91a80b3d156f59ee7c06b15eb6d50b → local dda2db2 (27 module files only).

Used exact commit cherry-picks instead of merging the Trip client's unrelated base/preparation ancestry. Full CJAuth and CJTripClient subtrees match the respective fixed owner heads byte-for-byte. No domain edits, extra wire, storage, root/App/lock/signing/brand changes. Existing sole shared export4fb/API9dc retained.

Authored source is limited to TripContainerHost, TripShell, ShellState/ShellView hooks, necessary CJShell dependency and related tests/docs. See ../../TRIP-CONTAINER.md for composition and current constraints.

PASS: 102 test functions in15 CJShell suites (`tests.txt`);11 new Trip container functions include parameterized accept/reject, null/malformed/cancel and account/background cases. Existing91 Memory, SDK/session, clear/load, message/history/draft and reentry tests remain PASS. The shared ShellState hook justifies this complete affected module run.

New tests use the producer's fixed action.json fixture directly, canonical generated models/client/TripPresentation, intercepted HTTP transports and ephemeral synthetic encrypted pending records. They verify no default/invented context, keyset reads, exact original proposal bytes/hash and pending facts, missing vs invalid response, original session retirement, old queued/read/callback A→B isolation, language stability, old query after selection switch, receipt version1 vs later formal version7, unknown cancellation settlement, and missing store/key with failed selection reread. All invoked transport operations are GET. No real network sockets, platform Keychain or account credentials.

PASS: unsigned arm64 iOS17 simulator-target module build (`ios-build.txt`). This compiles actual bilingual SwiftUI components; no App launch, simulator/device runtime, screenshot or VoiceOver acceptance. A first structural ShellState subset (6 functions) and Trip subset (11 functions) also passed; final full run follows the additional same-ID failed-store-reread guard.

PASS: resolved CJShell graph still uses one unique physical CJFoundation9dc path. The provenance records occurrence count (transitive references are not duplicate packages), raw graph hash, exact producer trees and unchanged lock/resource hashes. Final diff check clean.

Production POST/confirmation issuer, trusted live root, real accounts, Keychain, physical-device UI and full Trip acceptance: UNRUN/unavailable. Independent producer/container Review and Testing are Main's gates; these author checks do not claim them PASS. No publishing, external messaging, deployment, signing or permission change was performed.

Commands use the established CLANG_MODULE_CACHE_PATH=/tmp/cj006-clang-cache and SWIFTPM_MODULECACHE_OVERRIDE=/tmp/cj006-swift-cache:

```sh
swift test --disable-sandbox --package-path ios/Modules/CJShell --scratch-path /tmp/cj006-sdk-host-build --cache-path /tmp/cj006-spm-cache --disable-automatic-resolution
# SDKROOT unset for manifest compilation:
swift build --disable-sandbox --package-path ios/Modules/CJShell --scratch-path /tmp/cj006-memory-ios --cache-path /tmp/cj006-spm-cache --disable-automatic-resolution --triple arm64-apple-ios17.0-simulator --sdk /Applications/Xcode.app/Contents/Developer/Platforms/iPhoneSimulator.platform/Developer/SDKs/iPhoneSimulator27.1.sdk --target CJShell
swift package --disable-sandbox --package-path ios/Modules/CJShell --scratch-path /tmp/cj006-sdk-host-build --cache-path /tmp/cj006-spm-cache --disable-automatic-resolution show-dependencies --format json
```
