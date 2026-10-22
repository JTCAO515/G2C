# CJ-017 completed9d consumer graph after fixed Trip input

Previous partial candidate: `febea42a511c0b89eaaa94d95ccf9c8371aea83f`.
Consumer product pin: b5b9963 (one Package.swift path line, c5→9d); businessdb48855.
Shared input: `e450e3828577feb211467e63177254f909b06b91`, local prep
`f6db923528cce1ee37b22470a89f983b98cc1877` (historical94 artifacts retained).
Main-delivered Trip input: `ba61baa2cd18ae9d13bc9733c1175b936512a786`, imported
byte-for-byte as separate prep `269ec9ae69cf87f6130be9267f4a13e57faa9331`.
Official single SDK: `9d0f4b4c1e89b28d01de18092b5bf695de5bcde7`.

Exclude both dependency preparations from the product diff; consume original-owner
fixed inputs through their own integrations. No shared or Trip runtime/manifest was
authored by this consumer. Previous partial/conflict evidence stays intact at
`evidence/9d-api-pin`; its historical HOLD is superseded only by the new exact input
and the checks below, not hidden or deleted.

## Completed affected checks

1. **PASS actual complete module dependency graph**:
   `swift package --package-path ios/Modules/CJManualPreviewClient --scratch-path
   /tmp/cj017-manual-preview-9d-build show-dependencies --format json`.
   Four CJFoundation references resolve to ONE exact9d path. No conflicting identity
   warning remains. Raw output/diagnostics archived, summary in graph-check.json.
   This is the module graph, not the final CJShell/App graph.
2. **PASS module compilation plus minimal consumer checks**:
   `swift test --disable-sandbox --package-path ios/Modules/CJManualPreviewClient
   --scratch-path /tmp/cj017-manual-preview-9d-build --filter
   'exactOptInRunsOfficialClientAndPreservesFrozenNFDRequest|IndependentPreparationTests|PreparationOwnershipTests'`.
   Five functions / three suites pass. Real generated getTrip through the original
   closed source API obtains each accepted handle; official generated preview through
   the actual shared capability passes frozen NFD/original bytes/version, three actual
   work validators and can_save=false. Exact independent preparation repro and both
   source-callback positions, newer single-use success, old unused caller, cancellation/
   edit retirement remain correct. No fake accepted handle or live request is used.
3. **PASS normal-import public API typecheck**: PublicAPIConsumer.swift compiles
   against the built9d module with xcrun swiftc, Swift6/macOS target. It checks public
   original-source/session constructors (explicit readonly timeout entry and supplied
   transport compatibility), synchronous prepare→Task.perform and the Chinese SwiftUI
   component. The file is compile-only and never invoked. Exact command/exit/hash in
   public-api-check.json; no @testable import is used in this public probe.
4. **PASS preservation**: every Sources/Tests/Package.resolved byte matches e292f20;
   hashes in preservation.json. This completion adds no runtime/test/lock changes.
   The sole product runtime-adjacent delta remains the original manifest pin.
   All16 current SDK files still match exact official9d source blobs/hashes. Old
   schemas/affected generated blocks and old c5 export preservation results from the
   partial candidate remain valid and are reused, not rerun as broader business tests.

No unrelated24-function suite, backend/Trip/Auth tests or generic iOS build rerun.
The affected module is compiled by Swift test and its public API checked separately;
this report does not claim a new iOS SDK build. Earlier consumer iOS evidence and
Trip owner's9d iOS evidence retain their own scopes. No source or generated code was
modified to suppress existing toolchain warnings. SwiftPM dependency-resolution Git
messages are retained; no product API/provider request was sent.

## Boundaries and handoff

The previous concrete Tripc5 dependency gap is resolved in this exact local module
graph. This does not establish CJ006 App composition, a real usage attempt/source,
actual provider/network/account, rendered UI/VoiceOver, physical device, save,
confirmation, locks, feasibility, Issue I, CI or deployment. Those remain UNRUN.
No new readonly-attempt interface was guessed or consumed. Existing save gates and
original source/session/draft/work behavior are unchanged.

Shared/Trip/consumer independent Review/Testing are Main's separate fixed-input gates;
these are author pin-consumption results only. No push/PR/merge/main mutation.
Archive metadata records exact original SHA256/length; every compressed log roundtrips
unchanged. Worktree is clean after the final evidence commit.
