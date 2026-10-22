# CJ006 deferred server-read action P2

2026-10-22 Asia/Shanghai. Base **fdbbbf57ded5e7e99bd0b153f3f25139108f334f** → source **896b79525e8e7e98fb620acb688686be98ab39bd**. Evidence commit adds no product change. Exact Testing input read-only: cj-testing/CJ-006-server-history/REPORT.md and IndependentHistoryActionTests.swift. Producer94bad80/CJAPI2f8 are unchanged.

## Reproduction

Copied Testing's exact two state-level counterexamples into owned test scope and ran them before repair. Both failed with four assertions (read-origin-p2/before.txt): an old A history action issued B history GET and populated B; an old account list action issued a replacement-account GET and populated the new list. Original transport count and idle/unread assertions retained. This is stale explicit-read intent, not evidence of server authorization bypass or old A response published as B.

## Repair

- ServerReadContext captures original canonical binding, selected canonical summary/cursors, selection epoch and per-read request IDs before Task creation. ServerHistoryView creates it in body and every read/retry/next/draft button closes over it.
- All public load methods require explicit context, with no unsafe no-context/default overload. Tests/callers were updated to capture before deferred closure construction; assertions were not weakened.
- Entry validation precedes loading/page mutation and GET. Stale actions return without acquiring credentials or using replacement state. Request uses captured binding/selection/cursor.
- Completion still calls canonical validateRead before guarded settlement, now also checking original selection epoch. Selection retires old list continuation identity and clears a logically obsolete loading flag without appending its page. Existing error/resync/identity/local-editor boundaries remain.

## After / coverage

**15 test functions PASS in three suites**, read-origin-p2/after.txt: original ServerHistoryHost9 + identity callback2 + supplementary action4. The all-entry test has five argument cases, covering conversation first/retry, conversation next, history first/retry, history next, server draft. Every stale selection case issues zero additional requests and leaves B idle/unread with unchanged pages. Original stale-account case issues zero requests on both A and B transports. Reusing a completed read context does not retry or change the new page.

Prior positive paging, exact UTF8 cursor behavior, resync, late response fencing, null/empty draft and local editor preservation remain green. Actual SwiftUI buttons compile against required context signatures. **iOS package/demo compile + link/sign PASS**, read-origin-p2/ios-build.txt, arm64 simulator iOS17 target with installed SDK27.1. This was build-only: no device/probe, actual service, Keychain or provider action. No unrelated whole-suite repetition.

`git diff --check` PASS. Client/transport/generated/domain source unchanged, no ASCII restriction, PUT/POST, new wire type or auth authority. API migration documented in contracts/ui/SERVER-HISTORY-HOST.md. Existing fdbbbf evidence preserved as historical; this author result does not close UI HOLD without independent Review/Testing.

Reproduce:

```sh
env CLANG_MODULE_CACHE_PATH=/tmp/cj006-clang-cache SWIFTPM_MODULECACHE_OVERRIDE=/tmp/cj006-swift-cache \
  swift test --disable-sandbox --package-path ios/Modules/CJShell \
  --scratch-path /tmp/cj006-history-host --cache-path /tmp/cj006-spm-cache \
  --disable-automatic-resolution \
  --filter 'IndependentHistoryActionTests|ServerHistoryHostTests|IdentityCallbackReentryTests'
bash ios/Modules/CJShell/scripts/build-demo.sh /tmp/cj006-read-origin-demo
```

Next: Main routes exact fdbbbf-based delta to existing dual acceptance. No remote write/deployment; real service/device acceptance remains UNRUN.
