# CJRunClient c5-only package migration

2026-10-23 Asia/Shanghai. Product base84f41e1d5c76db789565e46fb05377f27fedea45;
original branchcj/010-run-client and worktree were clean, no reset or task duplication.
This is a host-requested package-graph dependency repair. Product delta: one path
replacement in this module's Package.swift plus these two pin evidence files.
Business Sources, Tests and Package.resolved remain byte-identical to84f41e1.
The prior README/REPORT/provenance remain historical c02 author evidence; this
increment is the current c5 migration evidence, without rewriting those results.

Dependency prep19064196e7cbeb847d5c61b20b8a157afef2c76b is separate from the product
diff. Its four files are exact blobs of shared fixed input
f4c17b59213828543cef042d127c56d8467963d8: CJMessageClient Package.swift,
scripts/prepare_generated.py, evidence/generated-pin.json and
Sources/CJMessageHTTP/Transport.swift. They remain CJ009-owned and must be excluded
from this product diff. Later shared5d/9d inputs were not consumed.

Official exportc5ffafb5524c40c6c518bb7a9c00c2e74aeeec2a uses the existing CJ009
prepare script and exact official root git blobs. All16 exported files match;
all16 oldc02 export files retain their hashes. No generated files, business
interfaces, locks, SDK versions or other client/host manifests were rewritten.
Shared f4's transport default behavior is consumed unchanged; this Run client
continues to expose only its existing GET read path.

PASS: actual standalone SwiftPM graph has one unique CJFoundation location, the
c5 export; both dependency edges resolve there. This establishes this module's
graph, not the pending complete CJShell host graph.

PASS: public RunDisplayModel/RunDisplaySource/RunDisplayView and official generated
Client compiled with `swift build` using existing locked revisions and local caches.
PASS: four existing targeted test functions /14 cases: sevenStatuses, all five
original-reference mismatches, duplicate/single-use reads, and reentrant prepare /
selection. Actual names are sevenStates, referenceMismatch,
duplicateReadReplacesSingleSnapshotAndWorkIsSingleUse,
reentrantPrepareAndSelectionAreFenced. Their official generated GET calls use
process-local synthetic interceptors and in-memory session persistence.
Prior19/54 author suite and unsigned iOS build evidence are reused for unchanged
business code; they were not rerun or reclassified as new c5 runtime results.

Commands from repository root (raw output under module .build/c5-pin-evidence):

```sh
swift package --package-path ios/Modules/CJRunClient --skip-update --disable-automatic-resolution show-dependencies --format json
swift build --package-path ios/Modules/CJRunClient --skip-update --disable-automatic-resolution
swift test --package-path ios/Modules/CJRunClient --skip-update --disable-automatic-resolution --filter 'RunDisplayTests/(sevenStates|referenceMismatch|reentrantPrepareAndSelectionAreFenced|duplicateReadReplacesSingleSnapshotAndWorkIsSingleUse)'
```

PASS: Sources/Tests/lock blob equality, prep/shared blob equality, old/new export
hashes, and git diff --check. Exact hashes/raw-output sizes are in C5-PIN.json.
Only pre-existing generated unused-public-import warnings and deprecated
--skip-update warning appeared; no source repair was needed.

UNRUN: complete CJShell/preview/Trip host graph and integration, new iOS runtime,
real network/Auth/Keychain/PG/provider, CI/deployment and full Issue11 acceptance.
No additional product-interface blocker found. Main can route the fixed product
delta and existing dependency prep to the original host owner and Review/Testing.
Requested model6.1Sol Medium/default; effectiveUNKNOWN.
