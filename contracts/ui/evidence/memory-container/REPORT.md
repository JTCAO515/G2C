# CJ006 Memory container evidence

- Base before authored container: e1a94d8ae25b9400a6de9e668aaf339d5f2a0dbf. Includes unchanged producer MemoryClient884a070ab51653776e17f77afb8b3628fd89e994 plus separate clear repair480c21b; producer sources were imported by normal merge, never edited by CJ006.
- This first container candidate uses the existing sole shared CJFoundation573 export. The requested later 9dc pin alignment is a separate follow-up after this fixed commit, not silently mixed into this evidence.
- Actual source: MemoryContainerHost/Views, MemoryShell, ShellState/ShellView and minimal Package product dependency. Brand/avatar/resources/signing/App code and dependency locks unchanged. No domain wire or fake production store/client was introduced.
- 91 test functions in 14 CJShell suites PASS (`tests.txt`), including 9 new container functions with parameterized cases. Canonical client and generated API execute against intercepted transport; test-only internal seams seed synthetic encrypted original records in disposable 0700 temp directories. No platform Keychain or sockets are used.
- New cases: default unavailable/closed writes; actual groups/global keyset pages and source/detail fields with candidate and distinct NFC/NFD subjects; real empty vs invalid response; stale queued action; late response after account/background and B binding; synchronous current-binding reentry; missing store; unavailable original key; original byte-exact operation query with saved/candidate/null/malformed response and no resend.
- Existing identity/reentry, message/history/draft, load/clear/SDK and local session tests remain PASS. Full suite is justified by the shared ShellState invalidation hook.
- Unsigned arm64 iOS17 simulator-target CJShell build PASS (`ios-build.txt`), including reusable SwiftUI components. This is compile-only; no simulator was booted or App launched. Help/privacy copy was updated afterward; final pin build will cover those copy-only changes.
- Initial test-only compile expressions were simplified for Swift Testing macro compatibility before execution; no failing runtime behavior was hidden. The earlier 8-function subset passed, then missing-key control was added before the recorded full run.
- Real accounts, live network, Keychain, device/rendered UI/VoiceOver, production POST, deployment and real end-to-end memory/next-answer acceptance: UNRUN. Independent Review/Testing handled by Main; author results are not those gates.

Commands:

```sh
env CLANG_MODULE_CACHE_PATH=/tmp/cj006-clang-cache SWIFTPM_MODULECACHE_OVERRIDE=/tmp/cj006-swift-cache swift test --disable-sandbox --package-path ios/Modules/CJShell --scratch-path /tmp/cj006-sdk-host-build --cache-path /tmp/cj006-spm-cache --disable-automatic-resolution
env -u SDKROOT CLANG_MODULE_CACHE_PATH=/tmp/cj006-clang-cache SWIFTPM_MODULECACHE_OVERRIDE=/tmp/cj006-swift-cache swift build --disable-sandbox --package-path ios/Modules/CJShell --scratch-path /tmp/cj006-memory-ios --cache-path /tmp/cj006-spm-cache --disable-automatic-resolution --triple arm64-apple-ios17.0-simulator --sdk /Applications/Xcode.app/Contents/Developer/Platforms/iPhoneSimulator.platform/Developer/SDKs/iPhoneSimulator27.1.sdk --target CJShell
```
