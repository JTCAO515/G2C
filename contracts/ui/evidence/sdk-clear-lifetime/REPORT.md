# CJ006 clear verification lifetime repair

- Review source: `cj-review/CJ006-8bfa233/review-summary.json`, remaining clear-path P2. The accepted load repair is unchanged.
- Before this repair: `6ad2dfa106f69baafffe37671f0793c759bbbba0` (8bfa host source plus unmodified MemoryClient dependency intake). CJShell Memory container edits are in progress and deliberately excluded from this repair commit.
- Reproduction: persistence clear callback performs a canonical nested clear, changes trusted verification generation/user ID, then actually saves B through SupabaseSessionBridge. B's exact bytes and current saved operation survive. The old clear throws staleOperation; old host falsely blocks both restore and account submission. `before.txt`: replacement test FAIL (2 assertions); genuine storageUnavailable/staleOperation failures and normal clear retirement PASS. An initial test-only macro compile typo was corrected before this behavior run; it is not counted as reproduction.
- Repair: capture trusted verification generation and verified ID before clear; recheck after return/throw, plus the existing shell generation fence. Displaced verification lifetime retires the old UI result to stale/idle only. No B storage/token is touched or adopted, no authenticated/business permission is granted, no use of ownsOperation(false) or error name as replacement proof.
- `after.txt`: 27 test functions in 4 suites PASS: new clear 3, existing load 4, SDK host 11, local session 9. Parameterized controls include same-original storageUnavailable and staleOperation named errors, which still block. A successful original clear remains cleared despite normal operation retirement.
- Executed locally with intercepted/synthetic SDK sessions and in-memory persistence; no account, network, Keychain, simulator/device, signing or release action. Tests compiled alongside the preserved in-progress Memory container model; Memory UI has separate pending validation and is not claimed here.

Command (from CJ006 root):

```sh
env CLANG_MODULE_CACHE_PATH=/tmp/cj006-clang-cache SWIFTPM_MODULECACHE_OVERRIDE=/tmp/cj006-swift-cache swift test --disable-sandbox --package-path ios/Modules/CJShell --scratch-path /tmp/cj006-sdk-host-build --cache-path /tmp/cj006-spm-cache --disable-automatic-resolution --filter 'IndependentSDKHostClearTests|IndependentSDKHostLoadTests|AccountSDKSessionHostTests|LocalSessionHostTests'
```
