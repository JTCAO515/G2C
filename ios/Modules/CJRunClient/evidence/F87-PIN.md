# CJRunClient f87 candidate compatibility preparation

2026-10-23 Asia/Shanghai. Basea6dc4a9581b16c4a997f69b66d9501a659d401f2;
original branchcj/010-run-client was clean. Actual first product write is only
Package.swift path33 ->f87a78a9d8984c59905e385483f17dddd8144d8a. This commit adds
that path and these two evidence files. Sources/Tests/Package.resolved are exact
base bytes. Previous reports remain historical evidence, including their limits.
No factory, permissions, public calls or original-source trust behavior changed.

## Fixed preparation within this module only

Shared input5075bcf604e959d5c4592071a1e9de39d8687395 from CJ009; official
rootf87a78a9d8984c59905e385483f17dddd8144d8a. Main restricted this task to
CJRunClient/** and explicitly forbade sibling/shared edits. Therefore no tracked
sibling prep commit was made. Dependency preparation is entirely ignored under
`.build/f87-pin-evidence/fixture/ios/Modules/`, excluded from the product diff.

That isolated fixture contains exact current CJRunClient Package/lock/Sources/Tests;
CJMessageClient Package/lock/Sources are exact git blobs from5075; CJAuth
Package/lock/Sources are exact original base blobs. Official CJFoundation export16
files are exact rootf87 git blobs and match5075 generated-pin SHA256. No dependency
manifest or generated source is rewritten in the fixture. All SDK locks retain
original bytes. Its actual standalone graph has one unique f87 CJFoundation path.
The direct/shared edges use the same location, not multiple SDK identities.

PASS: isolated official-SDK compilation including public model/source/view.
PASS: four existing targeted test functions /14 cases: sevenStates,
referenceMismatch (five original references),
duplicateReadReplacesSingleSnapshotAndWorkIsSingleUse and
reentrantPrepareAndSelectionAreFenced. Official GET codec/interceptor calls remain
synthetic and local. This is no new feature or external-service verification.

Commands executed on the isolated fixture (root repository cwd):

```sh
swift package --package-path ios/Modules/CJRunClient/.build/f87-pin-evidence/fixture/ios/Modules/CJRunClient --skip-update --disable-automatic-resolution show-dependencies --format json
swift test --package-path ios/Modules/CJRunClient/.build/f87-pin-evidence/fixture/ios/Modules/CJRunClient --skip-update --disable-automatic-resolution --filter 'RunDisplayTests/(sevenStates|referenceMismatch|reentrantPrepareAndSelectionAreFenced|duplicateReadReplacesSingleSnapshotAndWorkIsSingleUse)'
```

PASS: old33 OpenAPI25 paths/90 schemas are equal in official f87. Original
getRunDisplaySnapshot, MessageReceipt and RunDisplaySnapshot consumption is unchanged.
Sources/Tests/lock blob equality, unchanged Transport bytes versus base and5075,
old33/9d/c5/c02 export hashes, and git diff --check are verified. Full raw graph/test
logs remain under `.build/f87-pin-evidence`; hashes and preparation inputs are in
F87-PIN.json. Old full-business/unsigned-iOS evidence is reused; no full suite rerun.

## Remaining actual graph dependency

UNRUN: original-tree module graph. Its sibling CJMessageClient Package.swift still
references33cec5ba71d74820cb0acd3c89ecbe39ba125590 and has no f87 generated export.
This exact missing dependency was identified read-only, not tested through a known
broken graph. Main/shared dependency preparation must supply the canonical5075
manifest/export before checking the actual original or complete CJ006 App graph.
CJRunClient itself has no Trip or CJCleanupClient dependency. Neither sibling was
modified. The isolated fixture PASS does not resolve that pending actual host graph.

UNRUN: complete App/Cleanup integration, new iOS runtime, real network/account/
Keychain/PG/provider, CI/deployment and full Issue11 I. New wire independent gates
remain pending per Main; this result is candidate compatibility only. No actual
request, cleanup operation or factory activation occurred. Main can route this
fixed product delta with5075 to original Review/Testing and the actual host owner.
