# CJ006 explicit-capability server draft UI evidence

2026-10-22 Asia/Shanghai. Source **9629da3f7310a03239d4ccd3a487519934305d9f**; authored baseline **3d6ad58d4ee5c330a5c17205db43c7629eb3d6df**, the normal fixed625b66d dependency intake. Prior c3d7524 readonly delivery preserved. Evidence commit contains no executable change.

## Input / implementation boundary

Read fixed CJ009625b66d DRAFT-PUT-CLIENT.md and exact public saveDraft/validateDraftConfirmation/reconcileDraft/DraftSaveRecord code before implementation. Entire tracked CJMessageClient subtree remains byte-identical to625b66d. CJAPI2f8 and generated exports reused; no wire/receipt/type copies, Auth/API/client or entitlement modifications. Own changes limited to CJShell/contracts/ui.

ServerHistoryBinding defaults to no write capability. Only explicit interceptedTestOnly + synthetic binding permits test saves; the real client's live PUT/POST guards remain unchanged. GET permission/null observation alone cannot provide write capability. Default Demo/App never injects write capability and never reports save success.

Save freezes original scope/binding/selection, editor UTF8/revision, CAS and operation epoch before dispatch. It uses the actual canonical local editor registration + save/confirmation chain. Query uses canonical original pending CAS, not a replacement revision/body. UI never copies server response into editor or treats a matching/null GET as confirmation. Unknown records from another selected server generation are hidden/blocked; old-account actions cannot query replacement bindings. Local cancellation is not remote rollback. See contracts/ui/SERVER-DRAFT-SAVE-HOST.md for exact responsibilities/remaining live gates.

## PASS — bounded local evidence

**25 test functions PASS in four affected suites**: ServerDraftSaveHostTests10 + ServerHistoryHostTests9 + IndependentHistoryActionTests4 + IdentityCallbackReentryTests2. Some functions are parameterized (empty/nonempty editor, null/matching readback, existing five-entry stale read cases). Exact output server-draft-save-host/tests.txt.

New tests verify:

- GET-only binding cannot produce write context or PUT.
- Actual canonical success sends exact original bytes, including empty bytes; only the original editor revision is saved-current. Language leaves revision unchanged.
- Edit during PUT is preserved; A→B→A does not revive original saved-current marker. List refresh during a pending save issues no GET/selection change.
- Unknown retains original DraftSaveRecord; matching-content and null GET observations preserve it and never allow replacement PUT. A consumed query context cannot reissue GET.
- Stale editor/identity contexts issue zero PUT; later old-account unknown query issues zero replacement-account request.
- Local cancellation after dispatch retains unconfirmed CAS and denies resave;409 conflict preserves original bytes and has no automatic retry.
- Identity invalidation cancels local task/hides outcome, preserving a newer editor; pending record from old server generation is not displayed or writable.

Tests use concrete CJMessageHTTP/CJAPI code, memory-only SecureMessageStorage and in-process ClientTransport with synthetic metadata/material. Interceptor observes GET/PUT in memory; this is NOT actual network PUT or a fake default product success. No real key/session/user values entered or logged. The one initial compile failure was Swift Testing #require around a throwing getter; split into explicit try then require, without weakening any assertion.

**iOS compile + link/ad-hoc sign PASS** for actual package/UI and standalone Demo, source9629da3, server-draft-save-host/ios-build.txt. Swift6.4 / installed simulator SDK27.1 / arm64 iOS17 target. Build process exited0. No app installation, device run/display, provider, Keychain or network probe. Older actual UI/runtime evidence is not relabelled as runtime proof for this new slice.

`git diff --check` PASS. No unrelated full suite repeated. Reproduce after original exact generated exports:

```sh
env CLANG_MODULE_CACHE_PATH=/tmp/cj006-clang-cache SWIFTPM_MODULECACHE_OVERRIDE=/tmp/cj006-swift-cache \
  swift test --disable-sandbox --package-path ios/Modules/CJShell \
  --scratch-path /tmp/cj006-history-host --cache-path /tmp/cj006-spm-cache \
  --filter 'ServerDraftSaveHostTests|ServerHistoryHostTests|IndependentHistoryActionTests|IdentityCallbackReentryTests'
bash ios/Modules/CJShell/scripts/build-demo.sh /tmp/cj006-draft-save-demo
```

## Remaining

Independent UI Review/Testing pending. Live PUT/POST remains unavailable; no activation/antirollback/reconciliation bypass. Real server CAS/credentials/provider, device persistence/key ownership, Keychain, actual rendered UI and full end-to-end acceptance remain UNRUN. No automatic retries, force save, key conversion, server receipt invention or model/message send introduced. No remote push/PR/merge/deployment.

Brand handoff is separate coordination: after source9629da3 and exited build, AssistantShell.swift, own Package.swift and scripts/build-demo.sh were clean and no longer needed by this slice. BrandAvatar.swift/target Resources were absent. Exact writer release was reported in the owner chat for Main's sequential assignment; this evidence does not give a new owner permission to write before Main allocation.
