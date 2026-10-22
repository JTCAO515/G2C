# CJ006 original MESSAGE → USAGE association host

Author integration candidate. No real service, account, provider, App launch or device acceptance is claimed.

## Fixed input and graph

`input-preservation.json` verifies exact full tracked module trees against each supplied owner fixed, including shared 693, Usage d3, and all seven final 33 inputs. No producer Sources/Tests/locks were changed. Exported SDK33 has 16 byte-exact hash-verified files. CJShell changes only its own direct Foundation path to 33. Actual SwiftPM graph has exactly one Foundation at 33; Offline is prepared but not reachable from CJShell root. Legacy SDK exports and evidence remain intact.

## Behavior

Actual current accepted MESSAGE recovery record + original lease are captured opaquely. The original Usage client alone captures its closed accepted message and validates the association. Mandatory trusted-root actor bytes/session/operation have no default; no actor or attempt is guessed from an account, UUID, message or run. Root resources remain externally supplied, so default UI stays unavailable.

Action 1 synchronously prepares association before Task/read and runs only its GET. Source-ready presents stored linkage only. Action 2 separately prepares status from the closed resolved source before Task/read. Missing/invalid/503 association cannot query status. Selection ABA, root/session/receipt retirement and background remove authority; bounded callback fences and ownership tokens preserve newer work through reentry and late response. Old compatibility UsageSource host remains unchanged and cannot feed the official path.

## Actual checks

- `targeted.txt.xz`: first complete typecheck + 10 original-source test functions PASS (12 parameter cases).
- `affected.txt`: 35 functions / 5 suites PASS: MESSAGE, ShellState, identity callback, legacy Usage and original Usage. This includes the first 10 new functions.
- `targeted-final.txt`: final 11 original-source functions PASS (14 parameter cases), adding root and original-session retirement checks. Only tests changed after the affected run.
- `ios-build.txt.xz`: CJShell arm64 iOS 17 simulator-target compile PASS with iPhoneSimulator27.1 SDK. Source unchanged after compile. No App or simulator launch.
- `ui-contract.txt`: 7 positive + 5 negative existing UI presentation samples PASS.
- Actual dependency graph + `graph-check.json`: unique SDK33 PASS. Graph cache warnings preserved.
- `git diff --check`: PASS. Generated unused-import warnings retained in archived logs.

All HTTP exchanges in host tests use the canonical client's injected test transport and synthetic actor/credentials/receipts. Tests traverse actual MESSAGE stage/submission/query/accepted recovery capture, then the generated GET operations; they do not establish real server or dispatch acceptance. Unit/decimal/null semantics are consumed from the public Usage view with no arithmetic. RUN's current original-association writer remains synthetic-only; production Root wiring, real association source, dispatch and I remain UNRUN. Owner d3 and aggregate independent Review/Testing gates remain separate.

## Reproduction

From this checkout, prepare exact SDK33 using the shared module's existing prepare_generated.py and fixed foundation checkout. Use local-only SwiftPM caches and disabled automatic resolution. Commands used:

```sh
env CLANG_MODULE_CACHE_PATH=/tmp/cj006-clang-cache SWIFTPM_MODULECACHE_OVERRIDE=/tmp/cj006-swift-cache swift test --disable-sandbox --package-path ios/Modules/CJShell --scratch-path /tmp/cj006-sdk-host-build --cache-path /tmp/cj006-spm-cache --disable-automatic-resolution --filter OriginalUsageContainerHostTests
```

Affected filter: `AssistantMessageHostTests|ShellStateTests|IdentityCallbackReentryTests|UsageContainerHostTests`. iOS compile uses `env -u SDKROOT`, same caches, scratch `/tmp/cj006-memory-ios`, `swift build --disable-sandbox --package-path ios/Modules/CJShell --disable-automatic-resolution --triple arm64-apple-ios17.0-simulator --sdk /Applications/Xcode.app/Contents/Developer/Platforms/iPhoneSimulator.platform/Developer/SDKs/iPhoneSimulator27.1.sdk --target CJShell`. Graph command: `swift package --disable-sandbox --package-path ios/Modules/CJShell --disable-automatic-resolution show-dependencies --format json`. UI: `python3 contracts/ui/check_contract.py`. Archives retain exact uncompressed bytes and SHA256 in archives.json. Old partial/FAIL evidence is neither removed nor relabeled by these results.
