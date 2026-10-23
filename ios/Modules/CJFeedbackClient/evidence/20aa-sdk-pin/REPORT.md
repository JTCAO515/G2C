# Feedback subsequent20aa consumer compatibility

2026-10-23. Branch cj/023-feedback-client, initially clean. Exact parent/base and
preserved f87 candidate: **978df94db9c452fc0d24e50514ba1e4295e8a1ea**. That fixed
commit and prior f87 evidence/snapshot remain available for the independent0d1e gate;
this subsequent candidate does not replace its version or claim it was re-reviewed.
Final head is the commit containing this report, supplied in owner final.

Only Package.swift canonical shared path changes f87→
**20aa50ed5c8449e6026155a6151f22041dee7fd4**, plus this module's evidence.
No business Sources/Tests/lock, peer/Shell/shared/root tracked changes. Factory,
permission, actual send/save/cache/delete and original-source controls unchanged.

Ignored prep (no tracked shared prep commit): `.build/20aa-pin/snapshot/ios/Modules/`.
Shared CJMessageClient is copied exactly from original owner
**cc9e2c3ba1fb8fe7582e5e4664a924b1c6b93f71**; AUTH is exact original clean tree;
Feedback Package/Sources/Tests/lock are exact candidate bytes. Existing fixed shared
prepare_generated.py exports16 official SDK files from cj-005-foundation20aa into
that snapshot's sole canonical versioned package path. After compile every shared
tracked file and Feedback copied input is rechecked equal. Fixed identities/tree IDs
and hashes are in compatibility.json. No second SDK, alias or business abstraction.

PASS direct official git-show comparison f87→20aa: old **26 paths /93 schemas** equal;
only lifecycle additions listed in compatibility.json. SDK manifest/lock/UTC helper
are byte-identical. Shared Transport matches original accepted94 Host-guard bytes.
All15 original business/lock files and80 prior original export files retain hashes.
Original `swift package dump-package` parses with20aa without resolving the old graph.

PASS **isolated candidate only**: actual single CJFoundation20aa graph, unique nodes
and raw graph hash in dependency-graph.json; raw .build/20aa-pin/graph.json retained.
No Trip dependency/missing other-owner package. Snapshot SDK/consumer locks unchanged.

PASS public Feedback API/SwiftUI module compilation and **6 existing functions /
22 cases /2 suites**. Exact generated body/hash/source/original GET, UTC/null/oneOf,
malformed receipt and public POST-disabled checks; official Client via synthetic
process-local interceptor. Command/selected output targeted.txt, original full log
losslessly preserved as targeted-full.txt.xz. No failure or test edits. No full suite,
real network/cache/PG/Keychain/device tests; new-pin unsigned iOS build UNRUN. Prior
unchanged business evidence is reused only at its original scope.

**Original/full App20aa graph UNRUN.** Original sibling CJMessageClient remains33;
canonical original `.generated/20aa50ed5c8449e6026155a6151f22041dee7fd4/CJFoundation`
is absent. Main/shared owner must integrate fixed cc9e2c3 and prepare its canonical
export; CJ006/new Memory lifecycle host then owns unified App integration. This owner
did not run a known-conflicting old sibling graph or write its files.20aa candidate
snapshot compatibility does not assert complete App graph, lifecycle behavior, live
readiness, deletion success, I or Issue completion. No push/PR/merge/main update,
deployment or permission change. Original FAIL, f19b repair and f87 gates preserved.
