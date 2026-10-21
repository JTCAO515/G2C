# CJ006 local candidate evidence — 2026-10-21 Asia/Shanghai

Base 00769d7f793566887a8e192a6ca7b35d8c5fb46a. Initial contract/state candidate ce19590eeff68946a8a676b730d61eeb16713b84; final shell candidate is the commit containing this report. Owner: chat 01a15e71-9e73-7a02-85f5-de1081673c6d, branch cj/006-ui, independent clone --no-hardlinks. Current effective model UNKNOWN.

## PASS — author-local evidence only

- Contract check: BASE@1.0 read-only probe boundary; 7 positive/5 negative presentation samples (`contract-check.txt`).
- Swift 6.4 / arm64 macOS state tests: 5 passed (`swift-tests.txt`). Language survives a fresh ShellState initialization in the same preference suite, preserves tab/path/bilingual draft/opaque references; tab switching preserves draft/path; unsupported preferences are flagged and not overwritten; unknown outcomes rejected; send unavailable.
- iOS 17 arm64 simulator-target source typecheck passed with installed iPhoneSimulator27.1.sdk after allowing the Swift macro host. This is compile evidence, not iOS 17 runtime compatibility.
- Final native shell plus DemoApp compiled/linked/ad-hoc signed (`demo-build.txt`). `vtool -show-build` confirms IOSSIMULATOR / minos 17.0. No root Xcode project was created or modified.
- `git diff --check` passed. All changes limited to contracts/ui and ios/Modules/CJShell.

Initial sandbox-only typecheck failed because the Swift macro host could not execute; rerun with ordinary local build permission passed. Initial demo linkage emitted a mismatched default SDK warning; script now explicitly sets SDKROOT and selects iphonesimulator, then rebuilt successfully. These were local tool invocation failures, not runtime proof.

## UNRUN / remaining boundaries

- No simulator was running at discovery; no CJ006 simulator allocation was supplied. No existing CJ004/CJ005/VP device was used, booted or modified. Demo launch, bilingual screenshots, keyboard, rendered large text, VoiceOver, performance and physical-device acceptance remain UNRUN. Demo bundle and manual checks are ready for allocated-device testing.
- Real auth, messages, streaming, memory CRUD/source/time/receipts, trips, service/database integration and host identity-change cleanup: UNRUN / not implemented in shell. State/body slots do not freeze those domain contracts.
- Support contact and full product privacy terms remain unconfirmed; UI explicitly describes the gap. No invented operator/channel or deletion promise.
- CJ004/CJ005 final integration gates, independent Review/Testing, CI, publishing and device acceptance remain open. No ticket closed; no push/remote PR/merge/deployment, cloud, paid call or real account used.

Next: Main collects the fixed candidate, routes UI@1.0 to CJ007 for consumer confirmation and to existing Review/Testing. Subsequent domain rendering/actions require their own fixed contracts. This report is evidence, not a second project status authority.
