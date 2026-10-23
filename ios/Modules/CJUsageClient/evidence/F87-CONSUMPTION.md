# CJUsageClient unified f87 dependency candidate

Base **d3b898f2ce83d22a50201a45b0e6c884d25a3d16**. Product Package.swift changes ONE
SDK path33→**f87a78a9d8984c59905e385483f17dddd8144d8a**. No business behavior or
activation change. Sources, Tests, lock and every old FAIL remain unchanged.

Shared dependency source is exact **5075bcf604e959d5c4592071a1e9de39d8687395** from
cj-009-memory-api-pin. No sibling/shared/root/App file is modified. SDK is an exact
export of official f87 Package/lock/Sources/Tests, never regenerated or rewritten.
Old25 paths/90 schemas byte-equivalent as JSON values; SDK manifest/lock/helper
and shared Transport94/lock match old canonical inputs (f87-compatibility.txt).

## Preparation and actual validation

`python3 ios/Modules/CJUsageClient/scripts/prepare_f87_consumption.py <shared-repo>`
reads only fixed Git blobs and creates this module's ignored `.build/f87-consumption`
graph. It copies own actual manifests/Sources/Tests and exports shared5075, base
canonical AUTH and SDKf87 inputs. Refuses symlinks/differing existing files rather
than overwriting preparation.83 input hashes are in f87-preparation.json, all equal
after build/test. Reproduce commands from repository root:

```sh
swift package --package-path ios/Modules/CJUsageClient/.build/f87-consumption/ios/Modules/CJUsageClient show-dependencies --format json
swift test --package-path ios/Modules/CJUsageClient/.build/f87-consumption/ios/Modules/CJUsageClient --disable-automatic-resolution --filter 'OriginalUsageTests.acceptedCanonicalReceiptThenAssociationThenExplicitOriginalStatus|UsageTests.canonicalDefaultReadTransportWithGeneratedClient'
```

- PASS actual package graph:2 CJFoundation references,1 unique f87 path; all package
  identities have one path. This is the bounded usage/shared/AUTH graph, not full App.
- PASS compile of actual generated SDKf87 and unchanged client module, then2 targeted
  in-process methods: canonical accepted MESSAGE query→association GET→explicit original
  attempt status GET; legacy canonical NoRedirectTransport default GET. No full business
  suite, PG, keychain or device rerun. Previous d3 business/boundary proof reused.
- PASS ordinary-import public source-flow typecheck against actual f87 module output.
- PASS source/Test/lock integrity and no sibling/shared/Auth/backend/contracts edits.
- Logs: f87-consumption-tests.txt, f87-public-typecheck.txt, f87-graph.json.gz,
  f87-graph-stderr.txt, f87-public-and-integrity.json. SwiftPM used accepted cache
  versions; module lock and all83 input files remained exact.

## Remaining integration dependency / evidence boundary

The original sibling CJMessageClient in THIS tree remains at SDK33 by design. Own
product manifest now expects the shared5075/f87 path, so do not claim this original
mixed tree or current App graph builds. Actual integration must provide exact
shared5075/f87 export and align other active consumers in the one App graph; Main/
Publish own that work and CJCleanupClient6d5e318 combination. The isolated preparation
is not an embedded second shared package or a different product dependency path.

The new f87 wire independent gate is pending per Main input; this is consumer
compatibility candidate only. No factory activation or real request performed.
No new feature, whole Issue9 completion, full App/CI/iOS/device/rendered UI, real
network/account/keychain/cache/SQL/provider/fees/dispatch/release acceptance. No
push, PR, merge, issue closure or message to another thread. Requested6.1Sol medium
Standard/default; effective UNKNOWN. Previous failures preserved without modification.

Initial staged whitespace check flagged an extra EOF blank line in raw SwiftPM graph
output. Raw output is preserved losslessly as f87-graph.json.gz; decompressed SHA256
is in f87-public-and-integrity.json. Final staged whitespace check PASS.
