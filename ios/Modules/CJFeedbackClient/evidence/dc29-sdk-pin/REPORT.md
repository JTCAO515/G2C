# Formal Feedback consumer dc29 SDK compatibility increment

2026-10-23. Original branch cj/023-feedback-client, exact clean parent/base
**5548e6bd9375f4a46fa3d1a56a5fc233897a8acd**. Final head is the commit containing
this report, recorded in owner final. Formal tracked Package.swift path20aa→
**dc29bb3634e63d8f065c38d39a7a0059f76cfa53**, plus necessary module evidence. This
is the official consumer manifest needed for the future unified App graph, not only
a modification to a temporary test manifest. No business Sources/Tests/lock edits.
All old FAIL, f19b repair, f87/20aa fixed heads and evidence are preserved.

Fixed input preparation remains solely under own ignored `.build/dc29-pin/snapshot/`.
CJMessageClient is byte-exact **9b4852dfad418d124d60366ada8efb380a8ffc1d** from its
original owner repo; AUTH is exact original clean tree; Feedback manifest and all
Sources/Tests/lock are exact formal candidate bytes. No tracked peer/shared/Shell/root
file was changed. Preparation is excluded from the product diff, with no dependency
prep commit or new SDK identity. Existing shared script exports16 exact official
inputs from rootdc29 in cj-005-foundation; generated-pin inventory equals fixed shared.
Every shared tracked file and consumer input is rechecked exact after compilation.

PASS official20aa/dc29 git-show comparisons: all old **28 paths /97 schemas** equal;
new paths/schemas listed in compatibility.json. SDK Package/lock and Memory UTC helper
byte-identical. Shared Transport94 Host-guard bytes match the original tree. All15
original business/lock files and80 previous original export files retain hashes.
Formal original `swift package dump-package` parses with dc29 without resolving the
known old mixed graph. Fixed shared/AUTH tree IDs and export/file hashes are recorded.

PASS actual **candidate combined graph**: one CJFoundation at the officialdc29 path.
See dependency-graph.json (resolved nodes/raw graph hash); raw .build/dc29-pin/graph.json
retained. No Trip dependency/missing Trip candidate. No SDK/consumer lock drift.
A SwiftPM scratch-lock wait completed normally without retry/failure.

PASS public API/SwiftUI module Swift compilation and **6 unchanged functions /
22 cases /2 suites** in that exact graph. Actual official Client exact body/hash/refs,
original GET, UTC/null/oneOf/receipt validation and public closed constructor checks
all pass using an in-process synthetic interceptor. Command/output targeted.txt;
original full build/test log losslessly preserved as targeted-full.txt.xz. No new
tests or implementation edits, full old-suite rerun, real HTTP, credentials/cache/
Keychain/PG/device or install. New-pin unsigned iOS build UNRUN; original business
and prior iOS evidence reused only for unchanged source scope.

Remaining original/full App graph: **UNRUN**, not represented as PASS. The original
sibling CJMessageClient manifest still33 and canonical original
`.generated/dc29bb3634e63d8f065c38d39a7a0059f76cfa53/CJFoundation` is absent. Main/shared
owner must integrate fixed9b4852d, prepare its canonical official export and align
other formal consumers before CJ006 validates the whole App graph. This owner did
not wait on or execute that known-conflicting old graph. Its formal Feedback manifest
is now ready for that exact integration. Source/export independent gates and any
shared publication hold remain Main-owned; this does not implement FEASIBILITY or
claim App, real-source, I, device or release acceptance. Business factory/network/
credentials/save execution gates remain closed/unchanged. No push/PR/merge/main update
or deployment. Final scope/whitespace/byte preservation checks pass.
