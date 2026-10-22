# CJ006 outer identity cleanup reentry P2

2026-10-22 Asia/Shanghai. Base **e1857ac2f0a3b02a8172420c4e968d5573d1dd80** → source **954e66de80d8be3d30cab0261e334e523c4896c0**. This evidence commit adds no product code. Only ShellState, directly affected AccountHost fence call sites and a focused test file changed. Prior two P2 fixes, local-list source and original 17-test evidence remain untouched.

## Exact evidence consumed

Read Review chat 01a15e23-aac4-7c81-9a9d-1f0bc02aa775 through official read_thread. It reported original two P2s independently passing but overall HOLD for resource-callback reentry. Read exact current artifacts read-only:

- cj-review/CJ006-e1857ac/HostCheck.swift
- cj-review/CJ006-e1857ac/independent-host.log

The final counterexample in that executable is: outer AccountHost.clearLocalSession → ShellState.invalidateIdentity → A invalidateResources callback → nested local cleanup and bind B → set B editor → old outer ShellState rotates generation/clears editor afterward. Review log showed rebound=true, BHostCurrent=false, BEditorPreserved=false. No report filename/line was assumed.

## Before / after

Added IdentityCallbackReentryTests using that exact public-method sequence, plus assertions for B generation, body, navigation and no second storage clear. Added normal invalidation check that old private UI/generation are already fenced when the resource callback executes.

Before on e1857ac: **2 tests FAIL / 6 issues**, retained identity-callback-p2/before.txt. B binding/current generation/editor/body/path were lost, storage was cleared again, and normal clear-before-callback condition failed.

Repair:

1. ShellState publishes its new generation, message-binding block and empty private editor/path/presentation BEFORE calling message/resource invalidation. It performs no old-lifetime mutation after that external callback.
2. invalidateIdentity returns that invocation's ShellGeneration with @discardableResult; existing ordinary call sites may still ignore it. This return is a local stale-call token, not authorization. Package source consumers were searched and compiled.
3. AccountHost retires its own old task/channel/flow/state before the shell callback. Clear/restore/cancel/new-identity submit compare the returned generation to the current shell before continuing. A callback-installed B therefore causes old outer cleanup to return, rather than re-clear B storage or rewrite B navigation/state. Clear success/error also checks the original generation after the persistence call. Unknown barriers are not removed.

After: **27 tests PASS across five directly affected suites** (identity callback2 + existing independent reentry4 + account6 + local session9 + shell state6; prior parameterized save case retains its two argument cases). Exact log identity-callback-p2/after.txt. B's original lease validates; its editor/body/path/generation survive, only nested cleanup writes storage once. Normal invalidation still blocks message binding and rejects late old-generation presentation. Existing old-save/query/load and unknown/clear-failure regression checks remain green.

`git diff --check` PASS. No source change to list views, message client, session library, generated exports or root configuration. No independent review approval inferred from author tests. Original 17-test/list-preview artifacts are preserved, not relabelled as freshly rerun; no new simulator/device/UI run for this state-only delta. No Keychain/network/provider/real credentials accessed. Existing real-service/device limitations remain.

Reproduce targeted checks:

```sh
env CLANG_MODULE_CACHE_PATH=/tmp/cj006-clang-cache SWIFTPM_MODULECACHE_OVERRIDE=/tmp/cj006-swift-cache \
  swift test --disable-sandbox --package-path ios/Modules/CJShell \
  --scratch-path /tmp/cj006-message-host --cache-path /tmp/cj006-spm-cache \
  --disable-automatic-resolution \
  --filter 'IdentityCallbackReentryTests|IndependentHostReentryTests|LocalSessionHostTests|AccountHostTests|ShellStateTests'
```

Next: Main routes this exact e1857ac-based delta for Review/Testing. Overall HOLD is not closed by this author report. No push/remote PR/merge/deploy.
