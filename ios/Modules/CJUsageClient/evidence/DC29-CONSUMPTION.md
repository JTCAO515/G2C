# Formal CJUsageClient dc29 dependency candidate

Base **205fb479b89c7252dc2ad7587d327c578475c2fc** (20aa candidate).
Product Package.swift changes its ONE official sibling SDK path to
**dc29bb3634e63d8f065c38d39a7a0059f76cfa53**. Required exact shared source is
**9b4852dfad418d124d60366ada8efb380a8ffc1d** from cj-009-memory-api-pin.
This is the formal consumer manifest update needed for eventual full-App package
identity alignment. The ignored graph is its validation environment, not an alternative
product dependency path, a second SDK, typealias or factory activation.

Actual first write changed own Package.swift and added scripts/prepare_dc29_consumption.py.
The versioned prepare follows accepted own ignored Git-input export pattern, refuses
symlinks/different existing bytes, and never writes sibling/shared/Shell/root. Own
Sources/Tests/lock, old prepare scripts, all FAILs and old exports remain unchanged.
The prior f87 and20aa snapshots were verified still byte-exact (83/84 inputs).

## Narrow author validation

- PASS exact official shared9b, canonical AUTH and SDKdc29 exports:85 input hashes
  remain equal after actual compile/test. SDK is not regenerated/rewritten.
- PASS old28 paths/97 schemas equal20aa; SDK manifest/lock/Memory helper and canonical
  Transport94/shared lock byte-equal. No changed usage/MESSAGE operation or schema.
- PASS actual resolved graph: all identities have one path;2 CJFoundation references
  resolve to ONEdc29 export. No second active SDK identity in this bounded graph.
- PASS actual generated SDKdc29 and unchanged module compile, with2 targeted methods:
  canonical accepted MESSAGE receipt→association GET→explicit original status GET
  and legacy canonical NoRedirectTransport default GET. These exercise affected
  generated codecs/calls only, not new memory routes or real service availability.
- PASS ordinary-import public source-flow typecheck; AcceptedUsageMessage and
  ResolvedUsageSource constructors remain inaccessible to external import (expected
  compile-negative results). Public log preserved losslessly as gzip with raw SHA.
- PASS source/Test/lock/old-prep preservation, own-only diff and staged whitespace.
  Existing unchanged business proof reused; no broad suite/PG/keychain/device rerun.

Reproduce locally from repository root:

```sh
python3 ios/Modules/CJUsageClient/scripts/prepare_dc29_consumption.py /path/to/fixed/shared/repository
swift package --package-path ios/Modules/CJUsageClient/.build/dc29-consumption/ios/Modules/CJUsageClient show-dependencies --format json
swift test --package-path ios/Modules/CJUsageClient/.build/dc29-consumption/ios/Modules/CJUsageClient --disable-automatic-resolution --filter 'OriginalUsageTests.acceptedCanonicalReceiptThenAssociationThenExplicitOriginalStatus|UsageTests.canonicalDefaultReadTransportWithGeneratedClient'
```

Exact versions/sha:dc29-preparation.json; scope/old wire checks:dc29-compatibility.txt;
actual codec methods/module build:dc29-consumption-tests.txt; unique graph:
dc29-graph.json.gz; ordinary public calls/closed constructors:dc29-public-interface.txt.gz.
Argv/raw hashes and post-test integrity:dc29-public-and-integrity.json. Graph dependency
setup used accepted SwiftPM cache versions. Original module lock remains unchanged.

## Remaining full App dependency

Shared's export gate is PASS per Main task input; this author result is consumer
compatibility only. The original sibling in this worktree remains old and untouched.
Main/Publish must integrate exact shared9b/dc29 export and align all active peer
consumers to the same official dc29 identity. This candidate alone is not a full-App
build/whole wire gate, and must not replace old fixed candidates in their own gates.

No real network/credential/account/cache/keychain/SQL/provider/fee/dispatch/save/
delete execution, factory enablement, App/renderedUI/device/install/CI/deployment
or whole Issue9 acceptance. No peer/root authority edits, push/PR/merge/issue closure
or other-thread message. Requested6.1Sol medium/default, effective UNKNOWN.
