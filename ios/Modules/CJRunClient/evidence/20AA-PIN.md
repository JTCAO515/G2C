# CJRunClient 20aa compatibility increment

2026-10-23 Asia/Shanghai. Base/preserved f87 candidate:
a09fa5cdf229a21d5f51fa22d437a5164b57732e. Original cj/010-run-client was clean.
First actual product write: Package.swift f87 ->20aa50ed5c8449e6026155a6151f22041dee7fd4.
This commit adds only that path and these two evidence files. Business Sources,
Tests and Package.resolved remain exact base bytes. No new business behavior,
alias, factory activation, send/save/cache/delete or permission change.

Fixed shared cc9e2c3ba1fb8fe7582e5e4664a924b1c6b93f71 supplies the candidate
CJMessageClient manifest/source/export pins. Root20aa supplies the exact official
CJFoundation package16 files. Preparation follows the accepted ignored fixed-Git
snapshot model entirely inside CJRunClient/.build/20AA-pin-evidence/fixture/ios/Modules.
No peer/Shell/shared/root tracked or ignored paths were written. No tracked prep
commit is needed; ignored preparation is excluded from this product diff.

Fixture CJRunClient manifest/lock/Sources/Tests match this candidate exactly;
CJMessageClient manifest/lock/Sources match cc9e blobs, CJAuth manifest/lock/Sources
match original base blobs. CJFoundation16 exported files match official20aa blobs
and cc9e SHA256. No copied dependency manifest/source rewriting. SDK manifest/lock/
MemoryClientConfiguration helper are equal between f87 and20aa; Transport is equal
to the unchanged consumed original and cc9e. All26 old f87 OpenAPI paths and93
schemas remain equal in20aa. Original getRunDisplaySnapshot/receipt/snapshot calls
are unchanged. No Memory lifecycle API is called by this Run module.

PASS: actual isolated candidate graph contains one unique CJFoundation20aa path;
direct/shared edges resolve to this same official package. PASS: public model/source/
view plus actual official generated Client compile. PASS: four existing targeted
functions /14 cases: sevenStates, referenceMismatch (five original references),
duplicateReadReplacesSingleSnapshotAndWorkIsSingleUse and
reentrantPrepareAndSelectionAreFenced. Actual GET codec/interceptor calls are
process-local synthetic tests with in-memory session persistence.

Commands from repository root (raw outputs under .build/20AA-pin-evidence):

```sh
swift package --package-path ios/Modules/CJRunClient/.build/20AA-pin-evidence/fixture/ios/Modules/CJRunClient --skip-update --disable-automatic-resolution show-dependencies --format json
swift test --package-path ios/Modules/CJRunClient/.build/20AA-pin-evidence/fixture/ios/Modules/CJRunClient --skip-update --disable-automatic-resolution --filter 'RunDisplayTests/(sevenStates|referenceMismatch|reentrantPrepareAndSelectionAreFenced|duplicateReadReplacesSingleSnapshotAndWorkIsSingleUse)'
```

PASS: source/test/lock equality, exact Git input/export hashes, old26paths/93schemas,
unchanged Transport/helper/SDK locks, preserved f87 export and tracked F87-PIN evidence,
and git diff --check. Hashes/raw-output sizes are in20AA-PIN.json. Prior accepted
business evidence and author19/54/unsigned-iOS evidence remain their original layers;
no full suite/PG/Keychain/device rerun or evidence reclassification.

Remaining graph condition: actual original tree and complete App graph UNRUN. This
original sibling CJMessageClient remains33 and lacks20aa export; it was deliberately
not used for a known-broken graph attempt. Host/shared owner must combine canonical
cc9e/20aa dependencies with this candidate and the other consumers for the new Memory
lifecycle host graph. CJRunClient itself depends on neither Trip nor Memory client.
No wait on old sibling graph was necessary to finish this isolated candidate.

The prior f87 fixed commit, its ignored export/evidence and 0d1e publication boundary
remain independent. This later20aa candidate does not replace or qualify their gates.
UNRUN: full Shell/Memory lifecycle integration, new iOS runtime, real request/account/
provider/PG/Keychain/device, CI/deploy/release and complete Issue11 I. No independent
approval is claimed. Main routes this fixed delta to original Review/Testing and the
new Memory host owner. Requested Sol6.1medium/default; effectiveUNKNOWN.
