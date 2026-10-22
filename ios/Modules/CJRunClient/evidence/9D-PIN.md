# CJRunClient 9d-only package migration

2026-10-23 Asia/Shanghai. Product basee066043b3bf643b3711ad8e53e5cf03e0b56f550;
original cj/010-run-client branch/worktree was clean. Product delta is only this
module's Package.swift path c5 ->9d and these two pin evidence files. Business
Sources, Tests and Package.resolved are byte-identical to e066043. Previous c02/c5
reports remain historical evidence; this file records the current migration.

Dependency prep55e9e4bdccd14e081bf0271e14cbf4091e60ed1c is separate and excluded
from the product diff. Four CJMessageClient-owned files were imported as exact
blobs of shared e450e3828577feb211467e63177254f909b06b91: Package.swift,
scripts/prepare_generated.py, evidence/generated-pin.json and
Sources/CJMessageHTTP/Transport.swift. No dependency source was authored here.

Official9d0f4b4c1e89b28d01de18092b5bf695de5bcde7 export uses the existing CJ009
prepare mechanism. All16 exported files match exact official root git blobs.
All16 c5 and all16 c02 exported files retain their prior hashes. Locks and external
SDK versions remain unchanged. No other module or host manifest was modified.

PASS: actual standalone module dependency graph has one unique CJFoundation path,
the9d export. Both direct and shared edges resolve there. No additional owner-module
c5 dependency is present in this module graph; complete CJ006 host graph is UNRUN.
PASS: existing public model/source/view and official generated Client compile.
PASS: four existing targeted test functions /14 cases cover sevenStates,
referenceMismatch (all5 original references),
duplicateReadReplacesSingleSnapshotAndWorkIsSingleUse and
reentrantPrepareAndSelectionAreFenced. Official GET/codec calls use process-local
synthetic interceptors and in-memory session persistence; no real requests.

Commands from repository root; raw output remains under module .build/9d-pin-evidence:

```sh
swift package --package-path ios/Modules/CJRunClient --skip-update --disable-automatic-resolution show-dependencies --format json
swift build --package-path ios/Modules/CJRunClient --skip-update --disable-automatic-resolution
swift test --package-path ios/Modules/CJRunClient --skip-update --disable-automatic-resolution --filter 'RunDisplayTests/(sevenStates|referenceMismatch|reentrantPrepareAndSelectionAreFenced|duplicateReadReplacesSingleSnapshotAndWorkIsSingleUse)'
```

PASS: business source/test/lock blob equality, prep/e450 blob equality, new/old
export hashes and git diff --check. Exact source/raw evidence hashes are in9D-PIN.json.
Generated unused-public-import and deprecated --skip-update warnings are preserved.
Prior19/54 author suite and unsigned iOS compilation remain reused evidence for
unchanged business code, not newly rerun9d runtime evidence. No unrelated suite ran.

UNRUN: complete host/USAGE49 integration, new iOS runtime, real network/account/
Keychain/PG/provider, CI/deployment and Issue11 I. This pin adds no attempt behavior
and does not anticipate the pending new RUN readonly-source interface. No new
public-interface blocker found within this module. Main may route the fixed product
delta to original Review/Testing and CJ006 for its separately owned host graph.
Requested model6.1Sol Medium/default; effectiveUNKNOWN.
