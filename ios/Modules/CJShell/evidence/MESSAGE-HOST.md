# CJ006 assistant recovery host evidence

2026-10-22 Asia/Shanghai. Source **c99ca5fa1449388f1d7f188d7d9dcedf2308134a**, base **98fcc07faf57a9e7bab055d9148466c6783aa2a4**. This commit adds evidence only. Prior 34ebd46 session delivery preserved; source intake of c79da94 remains the prior normal merge 7342a39. Authored product delta stays in CJShell/contracts/ui.

## Dependency gate resolved in exact added lease

Before preparing: git clean, .generated absent, target and ancestors checked non-symlink. Unchanged prepare_generated.py/prepare_keys.py exported fixed CJAPI312a69ca and message-key interface f1ce075e directly from original CJ005/CJ007 git objects read-only. Verified all 15 exported CJAPI SHA256 values and exact key-interface SHA256. Reproducible pin files match committed producer bytes; `git diff c79da94 -- ios/Modules/CJMessageClient` is empty. Ignored exports remain local; no need to commit unchanged pins. No producer script, manifest, wire type, key type or other evidence modified. No original CJ009 checkout written.

Core dependency build now PASS (message-host/dependency-build.txt), closing the documented missing-export blocker. CJShell own lock adds three graph dependencies; its prior pins are unchanged. Integration owner must reproduce fixed exports before package build; the script paths and input commits are recorded in contracts/ui/MESSAGE-HOST.md.

## Author-local checks

- **8/8 AssistantMessageHostTests PASS** (message-host/tests.txt): default no send/storage; original bytes/ID and current draft preserved through language switch; repeated query click one invocation; canonical notObserved never send-enabled; unknown vs opaque synthetic receipt with no assistantBody; cleanup failure immediately invalidates client/display and blocks rebind/late callbacks; storage save unknown invalidates projection; wrong namespace/same-generation rebind rejected; prior lifetime stopped before reopening staged as queryRequired with exact original bytes/ID.
- Initial package integration also ran six affected ShellState tests PASS. Existing account/session suites and producer receipt/parser tests are reused, not rerun as if new independent acceptance.
- Final standalone iOS Simulator arm64/iOS17-target compilation/sign PASS (message-host/ios-build.txt). This compiles original adjacent CJMessageClient core as a separate static module; no real storage/HTTP/provider instantiated. Swift6.4 / installed Simulator SDK27.1; no iOS17 runtime claim.
- `git diff --check` PASS. Initial test compile exposed Foundation.Operation/CJMessageClient.Operation ambiguity; fixed with explicit module qualification. No assertions were weakened. Tests reran only after focused fixture/scope checks were added.

Focused reproduction after fixed exports:

```sh
env CLANG_MODULE_CACHE_PATH=/tmp/cj006-clang-cache SWIFTPM_MODULECACHE_OVERRIDE=/tmp/cj006-swift-cache \
  swift test --disable-sandbox --package-path ios/Modules/CJShell \
  --scratch-path /tmp/cj006-message-host --cache-path /tmp/cj006-spm-cache \
  --disable-automatic-resolution --filter AssistantMessageHostTests
bash ios/Modules/CJShell/scripts/build-demo.sh /tmp/cj006-message-demo
```

## Actual bounded preview

Own CJ006-Shell-20261021, iPhone17 Pro/iOS26.5, UDID 824A7623-8882-45C9-94A7-7BD2F758B685. Reused device, installed local.cj006.shell.demo and launched --message-demo. Tools initially had reset/missing defaults; those unsuccessful calls were not counted. Restored exact CJ006 profile, then checked actual snapshots/screenshots.

- query-required.jpg: explicit synthetic-local-state/not-service-reply label, original result needs checking/query only/do not resend, original synthetic draft visible, send disabled.
- Tapped Check original action, read back not-observed.jpg: no receipt observed, explicitly not proof of unsent and not permission to resend. Original draft still visible and send disabled. The Demo transition uses real recovery types with a memory store, no HTTP parser or transport; actual-null decoder correctness remains CJ009 evidence, not this screenshot.
- Screenshots were opened/visually inspected; actual target/text snapshots retained. No fixture appended as assistant reply, no model stream/history, no key/token/provider or real account. App stopped; device read back Shutdown. No other owner's device operated.

Snapshots and image/log hashes in message-host/sha256.txt. Only queryRequired→notObserved received new visual observation; staged/unknown/receipt and lifecycle negative behavior are local tests, not claimed real service/runtime coverage. Existing typography/navigation evidence reused.

## Remaining boundaries

Default product binding remains absent. Trusted production namespace/key capability and identity verification, real GET receipt transport, actual encrypted device storage/Keychain, non-rollbackable activation, physical devices and independent review/testing remain UNRUN/pending. No live POST activation or automatic resend method was added. Missing key cannot mean empty state; session token is never a message key. Successful local session clear only removes a local cleanup block; a trusted current-identity predicate is still mandatory and AuthAttempt unknown barrier is unchanged.

No push/PR/deployment or domain-source edits. Whole CJ006 ticket not closed. Main may route this fixed delta to existing Review/Testing and CJ009 for consumer confirmation.
