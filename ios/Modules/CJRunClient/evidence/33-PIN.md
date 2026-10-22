# CJRunClient 33-only package migration

2026-10-23 Asia/Shanghai. Product baseae6a30ff36a67ec3cf6a53126533d53a0636d53d;
original cj/010-run-client branch/worktree was clean. Product delta is only this
module's Package.swift path9d ->33 and these two pin evidence files. Business
Sources, Tests and Package.resolved remain byte-identical to ae6a30f. Existing
c02/c5/9d reports remain historical; this file records the current33 migration.

Dependency prep6d3548939356342b5c9da134715b60c986b27378 is separate and excluded
from the product diff. Three CJMessageClient-owned files are exact blobs of shared
6936a632ecc5cdbfd615b80c75312a09ed64b23a: Package.swift,
scripts/prepare_generated.py and evidence/generated-pin.json. Shared Transport.swift
is byte-identical to the prior e450-consumed version and fixed6936; no transport
copy or modification was necessary. No dependency source was authored here.

Official33cec5ba71d74820cb0acd3c89ecbe39ba125590 export uses the existing CJ009
prepare script. All16 exported files match exact official root git blobs. All16
files in each old9d/c5/c02 export retain their hashes. No lock or SDK version change.
No other client/host manifest was authored. Factory/permissions/source trust remain
unchanged; this pin implements no new original-association or attempt behavior.

PASS: actual standalone module graph has one unique CJFoundation location,33;
both direct/shared edges resolve there. This graph has no CJTripClient dependency,
so no Trip-owner head or manifest change was needed. Complete CJ006 host graph is
UNRUN and remains the host owner's responsibility.
PASS: existing public model/source/view and official generated Client compile.
PASS: four existing targeted test functions /14 cases: sevenStates,
referenceMismatch (all5 original references),
duplicateReadReplacesSingleSnapshotAndWorkIsSingleUse and
reentrantPrepareAndSelectionAreFenced. Official GET/codec calls use process-local
synthetic interceptors and in-memory session persistence, with no actual network.

Commands from repository root; raw output under module .build/33-pin-evidence:

```sh
swift package --package-path ios/Modules/CJRunClient --skip-update --disable-automatic-resolution show-dependencies --format json
swift build --package-path ios/Modules/CJRunClient --skip-update --disable-automatic-resolution
swift test --package-path ios/Modules/CJRunClient --skip-update --disable-automatic-resolution --filter 'RunDisplayTests/(sevenStates|referenceMismatch|reentrantPrepareAndSelectionAreFenced|duplicateReadReplacesSingleSnapshotAndWorkIsSingleUse)'
```

PASS: business/test/lock blob equality, prep/shared and unchanged Transport equality,
new/old export hashes, git diff --check.33-PIN.json records hashes/raw-output sizes.
Generated unused-public-import and deprecated --skip-update warnings are retained.
Prior19/54 author suite and unsigned iOS build are reused for unchanged business
code; no complete suite was rerun or promoted to a new33 runtime result.

UNRUN: complete CJ006 host/association integration, new iOS runtime, real network,
Keychain/account/PG/provider, CI/deployment and full Issue11 I. No public-interface
blocker found within this module. Main may route the fixed product delta to original
Review/Testing and CJ006. Requested model6.1Sol Medium/default; effectiveUNKNOWN.
