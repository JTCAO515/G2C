# CJ006 draft cancel origin P2

2026-10-22 Asia/Shanghai. Base **6773cb9e549dbd33a73d566613b99095ce75730a** → source **b16273b8b6c14ec6d4bd18a4b14d3ced9d72191a**. This evidence commit changes no product source.

Read exact Review artifacts under cj-review/CJ006-6773cb9: CancelOriginCheck.swift, independent-cancel.log and review-summary.json. Review reproduced completed A → saving B → retained A cancel closure targeting the current unbound task, cancelling B and leaving its CAS unconfirmed. This is wrong-operation cancellation, not a live write/authorization bypass.

## Red / green

Added the same controlled sequence to existing concrete canonical-client host tests. Before repair, the single parameterized function ran two cases and failed with three issues (draft-cancel-origin-p2/before.txt). It confirmed A successfully, retained A's exact old no-argument cancel closure, then showed that invoking it changed/cancelled B; the normal-B branch also failed to confirm revision2.

After repair, original binding ID, ShellGeneration, selection epoch, write epoch and Task are captured in a non-Codable ServerDraftCancelContext at control creation. Required-context cancel checks all origin fields plus active state before mutation; it targets the captured Task, never a later writeTask lookup. ServerHistoryView captures before its Button closure and disables a missing context. No unsafe no-argument overload remains. Existing current-cancel test is updated only to pass its current captured context.

**11 ServerDraftSaveHostTests PASS**, after.txt, retaining prior10 positive/unknown/conflict/default/identity tests and the new parameterized regression. For stale A, B remains saving and uncancelled, then confirms canonical revision2 and current B editor. In the alternate branch, B's own context cancels B and preserves its unconfirmed record/query-only barrier. Both branches retain B editor and only the original GET,GET,PUT,PUT intercepted method sequence. No assertions weakened or canonical source changed.

**iOS UI/demo compile + link/sign PASS**, ios-build.txt. Build-only, using the existing unchanged script and original existing ad-hoc configuration; no install/launch/device/network/Keychain/provider activity. Prior broader25-method evidence is preserved and not called a fresh full rerun. `git diff --check` PASS.

## Lease / delivery scope

Authored product changes only ServerHistoryHost.swift, ServerHistoryView.swift cancel wiring and ServerDraftSaveHostTests.swift, plus contract/evidence notes. AssistantShell.swift, Package.swift, scripts/build-demo.sh, BrandAvatar.swift and Resources paths were not edited; brand lease remains released. No SDK Session bridge work, new capability, live gate change, root/shared source or domain edit. Fixed625b66d dependency unchanged.

Independent P2 Review/Testing still required; author PASS does not close6773 SpecHOLD. Real server writes and full device/runtime acceptance remain unavailable/UNRUN. Main can apply this exact6773-based delta after its current source integration without taking a new feature slice.

Reproduce:

```sh
env CLANG_MODULE_CACHE_PATH=/tmp/cj006-clang-cache SWIFTPM_MODULECACHE_OVERRIDE=/tmp/cj006-swift-cache \
  swift test --disable-sandbox --package-path ios/Modules/CJShell \
  --scratch-path /tmp/cj006-history-host --cache-path /tmp/cj006-spm-cache \
  --disable-automatic-resolution --filter ServerDraftSaveHostTests
bash ios/Modules/CJShell/scripts/build-demo.sh /tmp/cj006-cancel-epoch-demo
```
