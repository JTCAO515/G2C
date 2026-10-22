# CJ-017 readonly manual-preview client — author evidence

Task: independent iOS editor/preview slice of original Issue #22, not the complete
manual-save/lock/feasibility feature. Owner branch `cj/017-manual-preview-client`.
Repository `/Users/jtsm5p/Documents/Codex/2026-10-21/cj-017-manual-preview-client`.
Base `33ea117c00f698a29814c60b75337374121f9973`.
Product source/test commit `e080fb7` (subsequent evidence commit does not change them).

Prep only, original-owner bytes, not product to cherry-pick:

- `36670fc`: shared3090777 and accepted Trip2b29918 imported unchanged.
- `e0f9f75`: Main-delivered Tripf931d583 c5 pin imported unchanged.

Product publish scope: only `ios/Modules/CJManualPreviewClient/**` after e0f9f75.
No shared source, Trip Package, CJShell, root API, Auth, backend, registry, HANDOFF or
Issue edit by this owner. HEAD contents of shared and Trip were compared against
their exact owner commits with `git diff --exit-code`: PASS, no differences.
Requested model per delegation: gpt-6.1-sol/medium, Standard/default; effective UNKNOWN.

## Actual results

- **PASS**: `swift test --disable-sandbox --package-path ios/Modules/CJManualPreviewClient
  --scratch-path /tmp/cj017-manual-preview-build` at final source; 18 test functions,
  39 cases counting parameterized inputs. `tests-final-callbacks.txt` retains output.
- **PASS**: final `xcodebuild -scheme CJManualPreviewClient -destination
  'generic/platform=iOS Simulator' -derivedDataPath /tmp/cj017-manual-preview-ios
  CODE_SIGNING_ALLOWED=NO build`; `ios-final-build.txt.xz` ends BUILD SUCCEEDED.
  This is an SDK module compile only, without signing/install/launch or rendered UI.
- **PASS**: dependency-graph traversal finds one unique CJFoundation path, exactly
  `.generated/c5ffafb5524c40c6c518bb7a9c00c2e74aeeec2a/CJFoundation` (`single-sdk.json`).
  Repeated graph references share the same identity/path; no old SDK was exported.
- **PASS**: source/test/package hashes in `source-sha256.json` and original-owner
  exact-byte dependency comparisons. No generated wire/Client source copied here.
- **FAIL preserved then repaired**: initial nullable-container construction, incorrect
  unlabeled nil construction, macOS-unavailable EditButton, and one projection-error
  classification assertion. All original logs are losslessly archived; final failures
  are zero. Raw xcodebuild/graph outputs caused an initial whitespace diff-check FAIL;
  those original bytes are archived instead of rewritten, then final diff-check passes.

Cases use real generated Client/Types and official `.memory` codec. Accepted handles
come through the actual closed Trip public prepare/detailSnapshot/guarded-access
API; only its existing internal transport initializer is used under @testable to
keep transport in-process. This module's interceptor initializer is also internal.
SessionLifecycle/SessionOperation are actual public AUTH APIs, with memory-only
synthetic persistence. There is no manual fake accepted handle, live account, secret,
Keychain, socket listener, provider, SQL or remote API traffic.

Covered: title-only/item-only/order-only/no-op; combined title/item/order; NFD UTF8
and exact source base64/version/Trip ID; frozen request bytes and actual null title/
order; explicit request and response limits; selected/unselected scope and position;
actual can_save=true refusal; changed original/version/scope/projection/diff refusal;
missing/null/duplicate/invalid enum/trace/no-store rejection; 409/503 retention and
explicit identical-byte retry; queued edit ABA; credential callback edits; transport
await and body-collection retirement; original session retirement; final host
callback retirement; five separate post-transport callback boundaries through the
last result-settlement check; old error cannot clear newer prepared work; cancellation
settles only original current work; explicit cancel, one-use and reentry.

Server response validation compares source-consistent values and scope, retaining the
server's exact diff bytes/order for display. It does not apply/recreate a patch,
prove signatures, certify feasibility/fixed-state, or claim remote freshness after
the last observation. Trip and canonical backend algorithm evidence is reused from
the fixed inputs, not rerun or relabeled as this consumer's result.

## Concrete shared dependency gate

**Current live preview dispatch: UNAVAILABLE.** Existing fixed
`CJMessageHTTP.NoRedirectTransport.send` rejects all POST/PUT before URLSession.
`existingLiveTransportGateIsVisibleAndRetainsDraft` exercises the actual public
editor/transport path: it displays unavailable and retains the draft, without making
a network request. Interceptor success does not remove that gate.

Required next dependency action: original shared owner supplies a fixed narrowly
scoped readonly preview operation/path/POST capability while retaining existing
write gates. This owner did not edit shared code, add a network fallback or bypass
the gate. After that exact fixed input arrives, only affected consumer checks need
rerunning. Main can review/test this fixed local candidate independently meanwhile.

**UNRUN**: rendered component interactions/screenshots/VoiceOver, CJ006 App factory,
live service, real accounts, physical device, network preview, saving, confirmation,
fixed-item persistence, feasibility, Issue #22 full I, deployment and publication.
No push/PR/merge/deploy was performed. Independent Review/Testing remain pending.

All archived logs are exact-byte xz compressions. `log-archives.json` records their
original SHA256 and byte lengths; use Python lzma or `xz -dc` to inspect originals.
