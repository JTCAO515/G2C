# CJ006 fixed f87 public composition

Base: 3f4051d7114d90187921f60e223683ffde171c60. Scope: only CJShell manifest, own ignored preparation script/ignore entry, README and own UI evidence. UI/Help/Demo/host Sources are unchanged. This candidate does not claim independent producer approval or real App/service readiness.

## Exact inputs

| Module | Original fixed |
| --- | --- |
| Shared MESSAGE | 5075bcf604e959d5c4592071a1e9de39d8687395 |
| Memory | 1734971c7606a346cfb73609eab6a06c16e8791a |
| Trip | a5cc42005c69811ccb05754793107141fb4a9f02 |
| Needs | f8ce99b916f1fd15f06ad534e44d3d2ce55dc1a6 |
| Feedback | 978df94db9c452fc0d24e50514ba1e4295e8a1ea |
| RUN | a09fa5cdf229a21d5f51fa22d437a5164b57732e |
| Usage | 7a1d4783d434fe69c62e954db93157a54f6e4182 |
| Manual preview | 46581fc954771ad9b388b0c600aee4dc74524730 |
| Offline | 2772d896db33344126eae2d025cd7d378dff1c8e |
| Cleanup | 6d5e318e95ab5f2be25b21569f26b37df23546f9 |
| Auth, exact dependency explicitly pinned by Offline2772 | 4eac0ad8db0ac33c89c7cc5b88d66b58d0fd6a7e |
| Official SDK | f87a78a9d8984c59905e385483f17dddd8144d8a |

Auth4eac Sources tree 616635d39995013bc5b7efb77647c6db9a47d57e is identical to published b331's Auth Sources, including all pending/snapshot key purposes. No Auth or other tracked sibling was edited. The Auth reference comes from Offline2772's checked-in prepare_f87_validation.py and evidence/f87-pin/inputs.json, not an inferred moving head. No shared20aa or moving Memory lifecycle source is consumed.

`prepare_fixed_dependencies.py` reads exact Git blobs into CJShell/.deps/f87... only. Build inputs (original Package.swift/Package.resolved, Sources, Tests) remain byte-exact; generated SDK has 16 hash-verified files. `prepared-provenance.json.xz` records all 184 file hashes and input tree IDs. `preservation.json` records matching hashes, unchanged 3f UI/Demo/Help and no tracked sibling delta. Preparation repeat PASS; conflicting existing bytes are refused rather than overwritten. Default manifest uses canonical siblings; explicit CJ_SHELL_ISOLATED_DEPS=1 uses this same ignored fixed composition. Integration must prepare matching canonical modules/SDK before removing that verification-only flag; no fallback or silent SDK substitution.

## Actual checks

- graph.json.xz + graph-check.json: actual CJShell dependency graph PASS. 23 Foundation references resolve to exactly one f87 path; every identity has one path. Offline and Cleanup are now root-reachable. No second SDK, shared20aa, current Memory head or old sibling manifest selected.
- ios-build-link.txt.xz: actual CJShell arm64 iOS17 simulator target build and existing standalone Demo link/local signature PASS, using installed iPhoneSimulator27.1 SDK. This compilation includes the real fixed Offline and Cleanup targets. No install, launch or UI input in this task.
- offline-ios-build.txt: explicit CJOfflineTrip target build in that same actual root graph PASS. Incremental reuse is expected; no independent Offline test suite rerun claimed.
- PublicConsumer.swift + empty public-api-compile.txt: iOS public composition typecheck PASS against actual built CJShell/Cleanup/Offline modules. Compile-only function takes existing values, never runs, creates no operation/store/transport, and is not a product wrapper/entry point.
- affected.txt.xz: 28 existing host functions in three suites PASS: OriginalUsageContainerHostTests, ShellStateTests, AccountSDKSessionHostTests. Synthetic intercepted/memory-only tests; no native Keychain, real account/network or provider. Prior unaffected domain tests are reused, not rerun or counted again.
- git diff --check PASS. Generated unused-import and restricted user-cache warnings retained. No dependency lock changes.

## Preserved failures and correction

Initial graph invocation lacked task-local compiler cache variables and failed to write the restricted home clang cache; corrected invocation used existing task caches. graph-initial-cache-failure.txt preserves that setup failure.

First preparation incorrectly selected Auth incidentally present in shared507, whose old enum lacks pending-key purposes; iOS/test compile failed on localMemoryPendingV1. Second tried this shell's older accepted Auth and failed on localOfflineTripSnapshotV1, which was previously dormant because Offline was not root-reachable. Both initial ignored combinations are retained separately; original compile logs remain in ios-initial-auth-failure.txt.xz, tests-initial-auth-failure.txt.xz, ios-old-auth-offline-failure.txt.xz and tests-old-auth-offline-failure.txt.xz. These were author preparation mistakes, not f87 producer incompatibilities. Final preparation uses Offline2772's explicit Auth4eac pin; no producer source was repaired or changed to pass. Initial public consumer invocation incorrectly used --sdk rather than swiftc's -sdk; its command failure is retained separately. Nothing relabels the old failures as a pass.

## Authority and remaining gates

Cleanup is linked only. This work adds no UI, factory, empty host wrapper, cleanup-operation creation, guessed original operation/actor, deletion, access grant or postlogout lookup. Without an existing trusted original operation source and current allowed credentials, cleanup remains unconnected/unavailable. Offline linking creates no cache, expiry policy, key or offline permission. Canonical MESSAGE/Usage two explicit reads and all 3f help/focus/source semantics remain unchanged.

Independent source gates remain Main-owned; this is author compile/selected-test evidence only. App runtime, two-step real-service integration, actual dispatch, Keychain, offline persistence, real cleanup, device/VoiceOver and I are UNRUN. Prior unknown/rejected input attempts are not retried. The already existing dependency bytes are resolved from prepared local caches; no runtime/service network is used.

## Reproduction

Run own preparation script with the existing checkout parent directory. All SwiftPM commands use env -u CJ_CLEANUP_ISOLATED_DEPS CJ_SHELL_ISOLATED_DEPS=1, --disable-sandbox, --disable-automatic-resolution and /tmp/cj006-spm-cache. Graph/tests also set CLANG_MODULE_CACHE_PATH=/tmp/cj006-clang-cache and SWIFTPM_MODULECACHE_OVERRIDE=/tmp/cj006-swift-cache.

Build/link: bash ios/Modules/CJShell/scripts/build-demo.sh /tmp/cj006-f87-demo. Tests: swift test --package-path ios/Modules/CJShell --scratch-path /tmp/cj006-f87-tests --filter 'OriginalUsageContainerHostTests|ShellStateTests|AccountSDKSessionHostTests'. Graph: swift package --package-path ios/Modules/CJShell --scratch-path /tmp/cj006-f87-graph show-dependencies --format json. Offline: swift build --package-path ios/Modules/CJShell --scratch-path /tmp/cj006-f87-demo/package-build --triple arm64-apple-ios17.0-simulator --sdk /Applications/Xcode.app/Contents/Developer/Platforms/iPhoneSimulator.platform/Developer/SDKs/iPhoneSimulator27.1.sdk --target CJOfflineTrip, with SDKROOT unset and compiler caches at /tmp/cj006-f87-demo/module-cache.

Public typecheck: env -u SDKROOT xcrun --sdk iphonesimulator swiftc -disable-sandbox -typecheck -swift-version 6 -target arm64-apple-ios17.0-simulator -sdk /Applications/Xcode.app/Contents/Developer/Platforms/iPhoneSimulator.platform/Developer/SDKs/iPhoneSimulator27.1.sdk -module-cache-path /tmp/cj006-f87-public-cache -I /tmp/cj006-f87-demo/package-build/out/Products/Debug-iphonesimulator contracts/ui/evidence/f87-combination/PublicConsumer.swift. Archives preserve exact original bytes and SHA256 in archives.json.
