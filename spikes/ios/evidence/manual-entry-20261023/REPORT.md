# CJ-004 fixed fixture: human listening entry / runtime preparation facts

2026-10-23; base `abf79f38169c361fd755c84f8f86c59513c7af65`; branch `cj/004-ios`. Only `spikes/ios/**` changed. This is preparation, not new simulator acceptance. No runtime download/install, device creation/boot, UI operation, VoiceOver change, recording, rebuild, test suite, signing, account or Keychain action occurred. Latest Main relay says JT confirmation is pending for iOS18 download/install; that explicit constraint supersedes the briefly broader preparation authorization.

## Actual read-only results

- Available runtime inventory remains iOS17.5 and26.5; no18. Own26 device `B80AD40D-F779-4FE3-A36D-CFD4C4A19D83` remains Shutdown. Current preflight exits0 and verifies source, cached app and installed binary hashes. Full preflight exits4 for missing18 runtime/approved18 target. Both JSON files have empty `side_effects`.
- `simctl get_app_container` on Shutdown returns SimError405, “Unable to lookup in current state: Shutdown”. This is a query limitation, not a missing-build conclusion. The helper reads only the validated device's bundle metadata and binary hash instead; no boot/reinstall is used to answer preflight.
- Data volume `df -h /Users/jtsm5p/Documents`: 926Gi size,885Gi used,13Gi available,99% capacity. This is a snapshot, not a guarantee that download+staging+installed18 fits. Do not delete old runtimes/caches automatically.
- Bounded cache inspection used `find -maxdepth 4` under `/Library/Developer`, `~/Library/Caches/com.apple.dt.Xcode`, `~/Downloads`, then maxdepth5 under `/Library/Developer/CoreSimulator`, `/Library/Developer/Packages`, `~/Library/Developer/Packages` and the same cache/download roots, matching `*iOS*18*`, `*simruntime*`, `*simulator*18*`. Only17.5/26.5 dyld entries were found; both Packages directories do not exist. No18 cache was found in those locations; this is not an exhaustive whole-disk absence claim.

## Official technical preparation route — Main owns execution after JT confirmation

[Apple: Downloading and installing additional Xcode components](https://developer.apple.com/documentation/xcode/downloading-and-installing-additional-xcode-components) documents a selected OS version download to an export directory, then `xcodebuild -importPlatform <simruntime.dmg>`. Local Xcode27.1 `xcodebuild -help` confirms `-downloadPlatform iOS [-exportPath <destinationpath> -buildVersion <osversion> -architectureVariant <universal|arm64>]` and `-importPlatform <simruntimedmgpath>`. [Apple's simulator runtime instructions](https://help.apple.com/xcode/mac/current/en.lproj/deva7379ae35.html) also provide the Components UI route.

The next narrow technical action, **not executed**, is Main choosing the available official iOS18 version (18.0 is the exact candidate floor) and requesting that specific arm64 asset into a task-private export directory, after JT permits download/install and fresh free-space verification. Example command shape: `xcodebuild -downloadPlatform iOS -exportPath <task-private-export> -buildVersion 18.0 -architectureVariant arm64`; then import the actual returned DMG path, without updating Xcode, deleting old runtimes, accepting an unapproved account agreement, changing trust/security/global settings or using another owner's simulator. Create a CJ004-only target only after successful approved preparation. No claim is made that Xcode27.1 currently offers18.0, that its asset fits13Gi, or that download/import needs no further authorization: actual catalog/compatibility, size, login/agreement/privilege behavior remain UNKNOWN until the authorized operation is attempted. Do not probe availability by starting an unauthorized download.

This is a technical Main task, not a runtime/tool choice for the listener. Product minimum OS and conditional Textual adoption are unchanged. An18 patch version record must state its exact version; do not call it18.0 evidence.

## Human-only short path

The repeatable entry is `scripts/cj004-human-check.sh`; stdlib helper `scripts/cj004-human-check.py`. Main supplies/coordinated target identity; listener supplies actual speech/focus/activation observations. The runner verifies fixed source and cached/installed binary, requires Shutdown, rechecks before boot, starts only validated CJ004 targets, opens Device Hub, and saves a fresh `evidence/manual-acceptance/run-*/` directory. It never downloads/installs runtimes or creates devices. Future all-mode may install the already-fixed fixture app into an empty approved18 target; mismatched installed builds block instead of being overwritten.

From the repository root:

```sh
# Read-only, usable by Main now; current=0, all=4 in this snapshot.
spikes/ios/scripts/cj004-human-check.sh --current-vo --preflight
spikes/ios/scripts/cj004-human-check.sh --all --preflight
# Actual listener only, after Main coordinates own26 window:
spikes/ios/scripts/cj004-human-check.sh --current-vo
# Future: after Main prepares and supplies an approved CJ00418 UDID:
spikes/ios/scripts/cj004-human-check.sh --all --minimum-device <CJ00418-UDID>
```

The fixed app is `spikes/ios/.cache/performance-post-p2/CJIOSSpike.app`, bundle `space.go2china.cj004.spike`. Source SHA256 `eb1b4fab47051d0322e7ff419da49dba1569fa010b1070374d66affb8f1f0cd0`; binary SHA256 `532860895903c76afe6e482197655885ef3ff5d42788f0085c7a91579f6966ab`. No rebuild is needed for the current entry. Cached build absence/hash mismatch blocks and returns to the original owner.

Listener stages: real observer code → actual bilingual speech and right/left focus sequence → activation → restore VoiceOver off/readback. Short path is floating History/Muse/Gift, mixed Chinese/English body/list/link, composer, four Tabs. Every opened local notice must be dismissed with **好 OK** before continuing. Record actual utterances, order, activated target and resulting behavior; use UNKNOWN when unobserved. Future18 mode adds dynamic type and text selection only; current26 functionality/performance evidence is reused. No full App/Auth/database/provider or extra FPS gate is added.

`observations.fields` stores non-secret human input, parsed with `shlex` without source/eval. `receipt.json` separates each human PASS/FAIL/UNKNOWN, observer, source/binary identity and final device state. Interruptions shut down only a device successfully booted by this runner; VoiceOver restoration stays UNKNOWN if not confirmed. Current-only results always leave18 UNRUN. Even all human PASS is `OBSERVER_PASS_REVIEW_REQUIRED`, never automatic ticket acceptance or Issue close. No microphone/host audio permission is requested; silent simulator video or AX labels cannot stand in for actual listening.

## Validation and remaining work

`validation.json`: Bash syntax PASS, Python syntax PASS, byte-identical wizard library PASS; direct current/all read-only behavior PASS. Shellcheck UNRUN (not installed; no installation). Guided execution UNRUN because the skill's human-listening path requires an actual observer; no speech or focus PASS is claimed. Existing builds/tests/P2/performance and26.5 scroll correction remain reused, not rerun. Requested model6.1-sol medium; effective model UNKNOWN.

Original Issue4 remains incomplete:18 actual dynamic type/selection/major VO row UNRUN; actual major VO speech/focus/activation UNKNOWN. Main handles approved runtime preparation; real listener handles only actual listening/interaction. Original Review/Testing and unique Publish retain closure authority. No cross-chat message, Issue edit, push, PR, merge or deployment was sent. Historical reports/manifests were not rewritten.
