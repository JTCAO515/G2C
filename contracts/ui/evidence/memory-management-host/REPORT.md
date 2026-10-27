> Later repair and full-graph evidence: [P2 lifetime repair](p2/REPORT.md) and
> [complete fixed 20aa graph](full20aa/REPORT.md). The following is the preserved
> original fca5 local-candidate report; its binding-only exit claim was disproved
> by Review and superseded by the P2 repair, and its graph-pending status is historical.

# CJ019 Memory lifecycle Shell host — local candidate

Base: `0d1e7b76217ea1325ad3dbc694282aa65308cf47` (original CJ006 f87 candidate, untouched).
Branch/root: `cj/019-memory-shell`, `<local>/Documents/Codex/2026-10-21/cj-019-memory-shell`.
Local commit is the commit containing this report; delivery receipt reads its exact head/tree.
Only this integration owner writes the leased paths. No push, PR, merge, Issue close or HANDOFF edit.

## Implemented

The existing MemoryContainerHost now requests the sealed `managementSelection` only after its actual accepted detail reader returns an item. The client supplies item version, source version and source ID; the host has no selection constructor/default version/cast/SDK alias. A list row alone never mounts detail management. Detail embeds the original `MemoryManagementControls`; the existing manual/recovery page embeds `MemoryManagementRecoveryView` for records returned by the original encrypted management journal. Recovery is action-only and retains original UTF8/action ID/hash; no apply/resend/replacement-ID wrapper was introduced.

Every accepted new host read, group/row change, view exit, background or host invalidation retires management presentation and invalidates the client generation. Detail reads use the host epoch and binding after awaits. A mismatched trusted account/environment/session/selection binding clears the host rather than resurrecting an old selection if the old identity returns. Outgoing views carry their binding ID, so a late disappear cannot clear a replacement binding. One validated tuple supplies each child's client/binding/selection. Language changes do not generate actions.

Pause/resume remain explicit confirmed user intent in the original controls. Source permission and resume eligibility remain server decisions. Historical receipts never overwrite current detail/list/qualification. Missing journal is failure, not an empty or submitted operation. Null receipt remains not observed, not permission to resend. The public client still has `managementAvailable == false`; original buttons show unavailable and cannot dispatch. No public/test enable flag, new framework, placeholder product host or live permission was added.

## Exact inputs and graph boundary

- Memory client: `ea85fe080e926b7c569883588486b8795a18d4ab`.
- Shared: `cc9e2c3ba1fb8fe7582e5e4664a924b1c6b93f71`.
- Official SDK: `20aa50ed5c8449e6026155a6151f22041dee7fd4`.
- Auth: `b24cc77c307bbb1dd9c552aeb92a148213534541`, the already accepted exact Auth input used by ea85's isolated graph.

`inputs.json` has the source commits, SDK export-manifest digest and every exported file's SHA256. `scripts/prepare_memory_management_host.py` reads Git blobs, checks SDK hashes, preflights existing bytes/symlinks, and exports into this root's ignored `.local` only. All three peer package manifests are byte-exact; no peer manifest rewrite. Exactly one CJFoundation path, under the official 20aa export. The new harness package contains the exact three owned host/view files and an explicitly SYNTHETIC surrounding Shell fixture. That fixture is test evidence only: it neither replaces product ShellState nor proves its whole-App behavior.

Final localized graph: `.local/memory-management-host/303ec949a053f5db`.
Passing macOS test graph: `.local/memory-management-host/c1f68f21a5e680c5`.
Only the two `#if os(iOS)` view files changed between these graphs (language helper visibility repair); host, tests and fixed dependencies are identical. Exact reuse comparison: `test-evidence-reuse.json`.

The canonical CJShell dependency line now requires 20aa. The full canonical graph is NOT prepared or compiled here. The old `CJ_SHELL_ISOLATED_DEPS=1` f87 preparation belongs to the fixed 0d1e candidate; it is not a valid mode for this follow-up. Do not merge this dependency line alone into an f87 consumer graph.

## Actual author checks

- PASS: 17 host test methods in 2 suites: existing 9 MemoryContainerHost methods plus 8 new MemoryManagementHost methods; parameterized cases add null/malformed and four binding-change dimensions. This is the LOCALIZED synthetic-Shell macOS graph. Internal intercepted-reader and encrypted-file initializers occur only in explicitly synthetic test fixtures, never product composition or a claim of management permission. No client 41-test rerun and no PG run.
- PASS: actual iOS Simulator SDK unsigned build for both arm64 and x86_64, including exact owned iOS views and original client controls/recovery. `xcodebuild -scheme MemoryHostHarness -destination 'generic/platform=iOS Simulator' -derivedDataPath ../../../../ios-memory-host-build CODE_SIGNING_ALLOWED=NO build`.
- PASS: public-only external typecheck, macOS and arm64 iOS Simulator, `PublicConsumer.swift`; no `@testable`, internal initializer or synthesized selection in that consumer. Empty public-api logs mean successful exit, not skipped execution.
- PASS: `git diff --check`; source/diff inspection confirms original controls/recovery calls and no ShellState/peer tracked writes.
- FAIL preserved: initial macOS compilation used await inside a boolean autoclosure; split into separate assertions. No assertion weakened.
- FAIL preserved: initial iOS compilation called client-internal `MemoryLanguage.text`; repaired using existing public ShellLanguage text method. Original client sources unchanged.

Full logs are losslessly gzipped, with byte counts and pre-compression SHA256 in `logs.json`. No earlier failure was deleted. Compiler warnings in the generated SDK are retained in those logs.

## Pending canonical graph and real acceptance

All following owner manifests need a mutually consistent single-20aa graph, then full CJShell/App compilation and independent gates. Their tracked source in this base may still contain older 33 snapshots; 0d1e's accepted isolated fixed graph uses f87. Neither constitutes a 20aa consumer acceptance:

- `ios/Modules/CJTripClient/Package.swift` — Main reports Trip owner still preparing fixed 20aa input.
- `ios/Modules/CJNeedsClient/Package.swift` — Main supplied fixed `e03da1b2f1c22a28da5b8c9110166108a44af936`.
- `ios/Modules/CJFeedbackClient/Package.swift` — Main supplied fixed `5548e6bd9375f4a46fa3d1a56a5fc233897a8acd`.
- `ios/Modules/CJRunClient/Package.swift` — Main supplied fixed `b1b5edf15ec84d1a1a1a4dede1b705958c9f8469`.
- `ios/Modules/CJUsageClient/Package.swift` — Main supplied fixed `205fb479b89c7252dc2ad7587d327c578475c2fc`.
- `ios/Modules/CJCleanupClient/Package.swift` — Main supplied fixed `d749fdc3ca4a25c78e5f9cc0eba3f55113255798`.
- `ios/Modules/CJManualPreviewClient/Package.swift` — original owner waits for fixed Trip; then must consume it with shared cc9/SDK20aa.
- `ios/Modules/CJOfflineTrip/Package.swift` — same Trip prerequisite and original-owner boundary.

The five newly supplied pins are preserved as Main-provided candidate pointers, NOT consumed or independently verified in this localized graph. No moving heads were substituted. Main coordinates their independent gates. Also integrate exact Memory ea85 and shared cc9 original packages/official export, plus this Shell increment, before asserting a complete single-SDK graph.

Main's task input records root20aa+82f merged as PR109/main `094dca15418a93d551e88db65980a08030a43f7d`; ea85's older document statement that root cohosting had not passed is superseded by that coordination evidence. This session did not independently rerun that root gate. The public root factory remains closed; no implication of true source permission or live activation follows.

UNRUN: canonical full CJShell/App graph, real navigation/rendered controls/VoiceOver, simulator execution, device, real account/session, HTTP query/POST, Keychain (including CJ007 probes), DB/provider/model, next-answer/context/whole Issue12/17/7 acceptance, CI, independent Review/Testing, publish/deploy. Tests show host wiring and synthetic negative boundaries only. All three Issues remain open; no release claim.
