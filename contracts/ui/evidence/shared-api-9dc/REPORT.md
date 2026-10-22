# CJ006 final shared API alignment

After the independently fixed Memory container40cc0e8, imported exact MemoryClientab8cf3eae5c79537ca05c800cad7f559b6187e86 and its unchanged shared export4fb05cc1f28382c5a4e97efdd833d5f079997c96 ancestry by normal merge9ced92b. Authored product delta in this follow-up is only CJShell/Package.swift's single CJFoundation path573→9dc; brand resources, locks, domain code and container business behavior are unchanged.

Ran the exact imported CJ009 `prepare_generated.py` against the verified fixed9dc commit in cj-005-foundation, within the already granted local generated export/evidence lease. All16 exported files equal canonical hashes; all16 old573 export files remain unchanged. No generated rewriting or second package identity. Producer modules diff clean against their fixed heads.

PASS: SwiftPM CJShell show-dependencies actual graph has4 transitive CJFoundation references, **one unique physical path**, all9dc. `provenance.json` records unique path, raw graph hash, exact source commits and export hashes. The existing CJShellDemo build script consumes this CJShell package graph. CJProbeApp's separate historical root package is not linked into it; no claim of a new formal product App composition or runtime launch.

PASS: affected MemoryContainerHost9 + ServerHistory/ServerDraft20 =29 functions in3 suites (`tests.txt`), no HTTP sockets, platform Keychain or credentials. Existing91-function full CJShell run remains valid for the unchanged host/container sources; this dependency change repeats only directly affected API-consumer suites.

PASS: final unsigned arm64 iOS17 simulator-target CJShell compile (`ios-build.txt`) includes all final source/copy and sole9dc export. Not App signing, launch, rendered UI, device or end-to-end acceptance. Production Memory POST remains closed; no Trip operation was invoked. Independent gates are Main's responsibility and not replaced by these author checks.

Initial graph command without `--disable-sandbox` could not start its manifest sandbox (Operation not permitted); using the same established local compile flag as all other package checks succeeded. No permissions/configuration change or live fallback was used.

Commands are the previous Memory container commands with the test filter `MemoryContainerHostTests|ServerHistoryHostTests|ServerDraftSaveHostTests`; graph command is `swift package --disable-sandbox --package-path ios/Modules/CJShell --scratch-path /tmp/cj006-sdk-host-build --cache-path /tmp/cj006-spm-cache --disable-automatic-resolution show-dependencies --format json`, with the same local module-cache environment.
