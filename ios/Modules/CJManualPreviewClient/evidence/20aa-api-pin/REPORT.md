# CJ-017 post-f87 20aa module compatibility — isolated exact inputs

Starting/preserved f87 candidate: `46581fc954771ad9b388b0c600aee4dc74524730`.
This is necessary dependency preparation for the new CJ006 host, not new feature
behavior. Existing f87 Git objects, full ignored dependency copy and evidence remain
unchanged; this task does not replace its release input or relabel its results.

Main-delivered immutable inputs:
- Shared `cc9e2c3ba1fb8fe7582e5e4664a924b1c6b93f71`, from original cj-009-memory-api-pin.
- Trip `b3485ef02bbe4cc9bfcebfc1f9c61a1a67670ce5`, from original cj-015-trip-client.
- Official SDK `20aa50ed5c8449e6026155a6151f22041dee7fd4`, from cj-005-foundation.
- AUTH: this consumer's already accepted46581fc tree, exact Git bytes, no new source.

Separate local preparation/evidence commit:
`a2720ed2fb4403a23501cad4eb67f3aba9caa1b8`. Exclude local prep from product delta.
The product changes only its own Package.swift SDK path f87→20aa and adds evidence.
Sources, Tests and Package.resolved remain byte-identical to46581fc. No factory,
permission, action/save or other business code is enabled/modified.

## Exact preparation and preservation

prepare_isolated.py derives its module/repository paths and reads only the fixed Git
objects above, rejects non-regular Git entries, and refuses an existing output root.
New graph resides in this module's ignored `.build/20aa-cc9e-b348/modules`, separate
from retained `.build/f87-5075-a5cc`. Canonical shared/Trip/Auth and any Shell paths
are untouched; no moving HEAD is read or substituted. No sibling manifest rewrite.
The16 official20aa package blobs are checked against the fixed shared SHA manifest
and read straight from the official SDK Git object into its designated isolated
shared export path. No generated model or client is copied into feature Sources.

isolated-inputs.json.xz records every prepared file's fixed source and SHA. After
checks, every recorded new file AND every file from the retained f87 preparation
still has its exact original hash. canonical sibling tracked paths pass git diff
--exit-code HEAD; current feature business/test/lock bytes equal46581fc.
Twelve affected getTrip/manual-preview generated schema/Client/Operations blocks are
literal unchanged from f87, and fixed shared Transport equals exact94 Host-guard bytes.
Detailed comparisons are in preservation.json; no business test was weakened.

## New author results, scoped only to this closure

PASS actual single20aa graph: swift package with package-path
`ios/Modules/CJManualPreviewClient/.build/20aa-cc9e-b348/modules/CJManualPreviewClient`,
scratch-path `/tmp/cj017-manual-preview-9d-build`, --skip-update,
--force-resolved-versions and show-dependencies --format json.
Four references resolve to ONE isolated20aa CJFoundation path; no identity conflict.
Raw graph/diagnostics are archived; graph-check.json records actual selected path.
The scratch name is historical and does not choose an old SDK.

PASS compiled module and five minimal test functions / three suites: swift test
with the same isolated package/scratch, --disable-sandbox --skip-update
--force-resolved-versions and filter
'exactOptInRunsOfficialClientAndPreservesFrozenNFDRequest|IndependentPreparationTests|PreparationOwnershipTests'.
The actual generated getTrip obtains the closed original source, and generated
preview passes through the actual fixed shared capability using original validators.
Frozen NFD/content/version, can_savefalse and source/work ownership pass. Exact prepare
reentry probe, both callback points, newer single-use/discarded-old-caller and cancel/
edit controls pass without live requests. Older unaffected behavior evidence is reused.

PASS normal-import public API compile against the newly built20aa closure: both
constructors, actual original Trip/source/session parameters, sync prepare→Task.perform,
and Chinese SwiftUI component. No @testable import in the compile-only public probe;
functions never invoked. public-api-check.json records xcrun swiftc command/exit/hash.

No unrelated full suite or generic iOS build rerun. Existing business/codec/Host/iOS
results retain their original scopes. Warnings (deprecated skip-update / generated
imports) are retained in raw logs; no generated code is rewritten to suppress them.

## Accurate remaining conditions

No missing fixed dependency remains in this isolated module closure. Canonical
consumer/sibling/App closure is deliberately not rewritten or accepted here. Main/
original owners must integrate exact sharedcc9 + Tripb348 and this Package pin into
the intended host graph; the new host fca5 was not imported, mutated or validated by
this owner. Isolated compatibility does not itself activate or approve that App graph.
Original f87 publication input stays available independently of this follow-up.

Independent candidate Review/Testing remains pending. New source/attempt authority,
real account/provider/API/network, product cache/Keychain, SQL/device, rendered UI,
save/confirmation/locks/feasibility and original Issue I remain UNRUN. No new SDK
identity, feature abstraction, permission/factory activation or actual saving/cache
behavior. No push/PR/merge/deploy/main update. No old FAIL or partial artifact removed.
Only compiler scratch and this module's ignored assembly were used for preparation.
All compressed logs round-trip to original bytes; metadata gives SHA256/length.
