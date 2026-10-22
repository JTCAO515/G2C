# CJ006 server history read-only candidate evidence

2026-10-22 Asia/Shanghai. Source **73c742ca94a11d010197f21119cdb0236b8ddc40**; authored diff base **562767b39e5c5ba0897aeef3c9bc0a88e73d9379** (normal intake of fixed CJ009 94bad80fdca10e68391022a7593f709c77ccefb4). Prior fafa218 retained. This evidence commit does not alter source.

## Fixed consumption / scope

First read 5885a18 HISTORY-READ-CLIENT.md and actual public types/methods via git show. Prepared canonical CJAPI2f8 fixed export using unchanged producer script, with absent new output path and non-symlink ancestors checked. All 15 hashes verified. Then Main reported 5885 cursor String equality P2; no client edit or ASCII restriction was made. Updated only by normal exact-object intake of 94bad80. Entire tracked CJMessageClient subtree matches that fixed commit, including unchanged generated-pin evidence; no producer PUT or moving dirty source consumed. CJShell references the same canonical exported CJAPI product, not copied types.

Own changed paths are CJShell and contracts/ui only. Root iOS project/shared API/CJAuth/key namespace/entitlements unchanged. Existing generated-output lease was used only for the canonical fixed export; no extra tracked producer delta. `git diff --check` PASS.

## PASS — bounded author checks on final input

**11 test functions PASS**: ServerHistoryHostTests9 + prior IdentityCallbackReentryTests2. Exact log server-history-host/tests.txt. Uses concrete MessageHTTPClient, generated schema decoding and validateRead with injected memory storage and in-process ClientTransport. No live URLSession/Keychain/provider/real account.

- Unconfigured differs from a successful empty first page.
- Repeated identical opaque cursor produces resync and discards chain; load-more cannot issue another request after this state.
- UTF8-distinct NFC/NFD cursors continue successfully through three pages on fixed94bad80; no normalization/ASCII workaround in host. Stale prior-page row-selection token is rejected.
- Delayed A history is discarded after selecting B; only B messages appear.
- Null server draft and positive-revision empty saved draft are separate; neither overwrites local unsaved editor text.
- Invalid generated response becomes failed, not empty success.
- Language does not rotate read lifetime; identity invalidation hides and discards late read results.
- History continuation preserves same selected conversation/server sequence; exhausted page cannot fetch again.
- History generation differing from selected summary requires resync.
- Previous resource callback reentry P2 checks remain green with the new server projection fence.

**iOS compile/link/ad-hoc sign PASS** via scripts/build-demo.sh, server-history-host/ios-build.txt. It builds the actual SwiftPM package graph for arm64 iOS17 simulator with installed SDK27.1, then links Demo against compiled modules. New SwiftUI sheet, generated types, and final94 client compile together. This is compile evidence only: app was NOT installed/launched and no device/probe retry occurred. Default server binding is absent; no fixture response is installed by default.

Process failures corrected before final evidence: Observation macro rejected a multi-variable stored-property declaration; split the request IDs into separate declarations. One held-response test used a wrong operationID and was corrected after reading canonical readMessageHistory. Initial cross-compile set SDKROOT globally, making the macOS manifest use an iOS SDK; cleared SDKROOT for SwiftPM and passed SDK/triple only for target compilation. Generated unused-import warnings remain upstream output, no source edited to hide them. Final tests/build are green; unrelated old suites and device checks were not rerun.

Reproduce after exact producer exports:

```sh
env CLANG_MODULE_CACHE_PATH=/tmp/cj006-clang-cache SWIFTPM_MODULECACHE_OVERRIDE=/tmp/cj006-swift-cache \
  swift test --disable-sandbox --package-path ios/Modules/CJShell \
  --scratch-path /tmp/cj006-history-host --cache-path /tmp/cj006-spm-cache \
  --filter 'ServerHistoryHostTests|IdentityCallbackReentryTests'
bash ios/Modules/CJShell/scripts/build-demo.sh /tmp/cj006-server-read-demo
```

## Pending / truthful boundary

No live server/history/draft reads, real credentials, Keychain, physical devices or newly rendered UI evidence. Independent producer review and combined Review/Testing remain pending; final94 cursor integration test does not imply independent acceptance. Existing local recovery list remains a separate source and is not used to fake server records. GET-only consumer methods are wired; no PUT/POST method or automatic draft merge/write. Read-only server draft does not modify local editor.

Main may route this fixed UI candidate with exact94 + CJAPI2f8 dependencies. Source/interface/lifecycle detail: contracts/ui/SERVER-HISTORY-HOST.md. Prior HOLD for5885 is not silently treated as passed. No push/remote PR/merge/deployment; local dependency merges only.
