# CJRunClient formal dc29 consumer migration

2026-10-23 Asia/Shanghai. Product baseb1b5edf15ec84d1a1a1a4dede1b705958c9f8469;
original cj/010-run-client was clean. Actual first writes are the formal Package.swift
path20aa ->dc29bb3634e63d8f065c38d39a7a0059f76cfa53 and the new public-consumer
SDKPublicConstructionTests.swift. Product diff contains those plus this pin report
and JSON evidence. This is the formal consumer manifest change needed for later
unified App integration, not merely a temporary fixture manifest change.

All business Sources, all pre-existing Tests and Package.resolved are exact base
bytes. New test uses external imports only (no @testable): public endpoint/explicit
NoRedirectTransport/model/view construction succeeds; without original source,
prepareRead returns nil, state stays unselected and credential callback count is0.
No request is sent, no source authority/factory/write path is activated.

Fixed shared9b4852dfad418d124d60366ada8efb380a8ffc1d and official SDKdc29 inputs
are prepared by the accepted ignored fixed-Git snapshot model, entirely under
CJRunClient/.build/DC29-pin-evidence/fixture/ios/Modules. Peer/shared/Shell paths
remain untouched. CJMessageClient Package/lock/Sources match exact9b4852 blobs;
CJAuth Package/lock/Sources match exact original base blobs; CJRunClient candidate
manifest/lock/Sources/Tests match actual current module bytes. CJFoundation16 files
match exact official rootdc29 blobs and shared generated-pin SHA256. No dependency
source rewrites, extra package identities or typealiases.

PASS: real isolated candidate graph has one unique officialdc29 CJFoundation path,
with direct/shared edges resolving to the same location. PASS: module/public API and
actual generated Client compile. PASS: five targeted functions /15 cases: sevenStates,
referenceMismatch (five original refs), duplicateReadReplacesSingleSnapshotAndWorkIsSingleUse,
reentrantPrepareAndSelectionAreFenced, and the new public closed-construction test.
Generated GET/codec/interceptor tests remain process-local synthetic checks.

Commands from repository root; raw output under .build/DC29-pin-evidence:

```sh
swift package --package-path ios/Modules/CJRunClient/.build/DC29-pin-evidence/fixture/ios/Modules/CJRunClient --skip-update --disable-automatic-resolution show-dependencies --format json
swift test --package-path ios/Modules/CJRunClient/.build/DC29-pin-evidence/fixture/ios/Modules/CJRunClient --skip-update --disable-automatic-resolution --filter 'SDKPublicConstructionTests|RunDisplayTests/(sevenStates|referenceMismatch|reentrantPrepareAndSelectionAreFenced|duplicateReadReplacesSingleSnapshotAndWorkIsSingleUse)'
```

PASS: all28 old20aa OpenAPI paths and97 schemas are equal in officialdc29, including
the consumed original getRunDisplaySnapshot, MessageReceipt and RunDisplaySnapshot.
SDK manifest/lock/MemoryClientConfiguration helper remain equal; Transport is equal
to original consumed bytes and9b4852. Existing business/test/lock hashes, exact
snapshot inputs, old20aa export and tracked20aa/f87 evidence preservation, and
`git diff --check` are verified. Hashes/raw-output sizes are inDC29-PIN.json.
Old failures and accepted unaffected business evidence retain their original scope;
no broad suite/PG/Keychain/device/install was repeated. Deprecated --skip-update and
generated unused-public-import warnings remain in raw logs.

Remaining actual App graph condition: UNRUN. Original local sibling CJMessageClient
remains33 and lacksdc29 export, outside this owner's write scope. Main/host owner
must consume canonical9b4852 plus all formaldc29 consumer manifests for the real
cohost graph; this formal consumer migration supplies this module's piece. The
isolated exact-input candidate PASS does not mean the original-tree or complete
App graph already passed. CJRunClient itself has no Trip/Memory/Cleanup dependency.

UNRUN: complete App/cohost, new iOS runtime, actual network/account/provider/PG/
Keychain/device, CI/deployment and full Issue11 I. No install or source/factory/
credential/save execution boundary change. Main routes this fixed candidate to
original Review/Testing and host integration. Requested6.1Sol medium/default,
effectiveUNKNOWN.
