# Feedback f87 candidate pin with fixed shared5075 preparation

2026-10-23. Original branch cj/023-feedback-client, exact clean base/parent
**435d666b0e4ef67792cf6aa9506af2f77eea1a42**. Final head is the commit containing
this report, supplied in owner final. Sole non-evidence edit: Feedback Package.swift
canonical shared SDK path33→**f87a78a9d8984c59905e385483f17dddd8144d8a**.
No business Sources/Tests/lock, sibling/shared/root/App changes. Historical FAIL and
prior valid business evidence remain intact; no new functionality or write permission.

## Fixed dependency preparation — ignored and separate from product diff

This task did not authorize writing sibling CJMessageClient. Its original manifest
remains33. Therefore no shared subtree preparation commit was made in the original
repo, and no known-conflicting original graph was run. Preparation lives only under
this module's ignored `.build/f87-pin/snapshot/ios/Modules/`:

- Shared CJMessageClient copied byte-for-byte from
  `/Users/jtsm5p/Documents/Codex/2026-10-21/cj-009-memory-api-pin`
  **5075bcf604e959d5c4592071a1e9de39d8687395**, tree recorded in compatibility.json.
- CJAuth copied from this original clean base, tree3ba7e7f5390b48ba523342131f25b73c996b4410.
- Feedback Package/Sources/Tests/lock copied exactly from this candidate.
- Existing shared5075 prepare_generated.py exports16 exact official inputs from
  cj-005-foundation **f87a78a9d8984c59905e385483f17dddd8144d8a** into the snapshot's
  sole versioned CJFoundation location. Inventory equals shared5075 generated-pin.json.

The snapshot preserves the same official package/module identities and relative
layout, not another handwritten SDK. After compile every shared tracked file and
all copied Feedback Package/Sources/Tests/lock bytes were checked again exactly equal.
No dependency export overwrote original dirty/user data or existing older exports.

## Consumer compatibility

PASS fixed official33/f87 OpenAPI comparison: all old **25 paths /90 schemas** exactly
unchanged. Official SDK Package.swift/Package.resolved/MemoryClientConfiguration.swift
helper byte-identical. Shared Transport matches the original accepted Host-guard
bytes. Hashes, added paths/schemas and all original business/export hashes are in
compatibility.json. All15 original business/lock files and80 existing export files
retain pre-edit bytes. Original manifest `swift package dump-package` parses with f87.

PASS **candidate snapshot only**: actual single CJFoundation f87 package graph;
see dependency-graph.json (unique resolved nodes and raw graph hash). Raw graph remains
`.build/f87-pin/graph.json`. No Trip dependency or missing Trip-owner candidate exists.
No SDK locks/revisions changed. This is not a claim about the original or CJ006 App graph.

PASS snapshot Swift compilation of public Feedback APIs/SwiftUI module and actual
existing affected tests: **6 functions /22 cases /2 suites**. Exact generated POST/body/
feedback hash and original GET, general/linked/null and illegal oneOf, UTC whole and
fractional decoding, malformed receipt refs/hash/keys, and public constructor's disabled
POST. Only process-local interceptor, synthetic bindings/persistence and .invalid URL.
No full old suite or real service/caches/Keychain/PG/device run. Command and selected
result in targeted.txt; full original losslessly retained as targeted-full.txt.xz.
No new test failure; existing SDK public-import warnings remain. No source edits made
for the new cleanup wire. New-pin unsigned iOS compile UNRUN; old iOS behavior evidence
is reused only for unchanged sources, not represented as an f87 iOS build.

## Remaining graph dependency and gates

**Original worktree graph: UNRUN, known preparation gap.** Exact existing sibling:
`ios/Modules/CJMessageClient/Package.swift` still33. Canonical original export
`ios/Modules/CJMessageClient/.generated/f87a78a9d8984c59905e385483f17dddd8144d8a/CJFoundation`
is absent. Main/shared owner must integrate fixed5075 and run its existing official
prepare script before original/full App unified f87 graph can be claimed. This owner
has not edited those sibling paths. Isolated candidate evidence is ready for that
exact combination and Main's original dual gates/CJ006 integration.

New wire independent acceptance remains pending per Main; factory/write gates and
real-source boundaries remain unchanged. No attempt/source availability, cleanup
operation, universal deletion, App/two-entry/I or release acceptance is implied.
No real request, credential, postlogout capability, permissions, push/PR/merge/main
update, account deletion or deployment. This pin is candidate compatibility only.
