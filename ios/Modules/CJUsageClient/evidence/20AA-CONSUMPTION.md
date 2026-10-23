# CJUsageClient subsequent20aa compatibility candidate

Base **7a1d4783d434fe69c62e954db93157a54f6e4182** remains the independently consumable
f87 fixed candidate; this incremental commit does not move or overwrite that input.
Product Package.swift changes ONE SDK path f87→
**20aa50ed5c8449e6026155a6151f22041dee7fd4**. Fixed shared input is
**cc9e2c3ba1fb8fe7582e5e4664a924b1c6b93f71** from cj-009-memory-api-pin.
No business function, alias, SDK generation, activation or real request is added.

Only own module manifest/prepare/docs/evidence change. Business Sources/Tests/module
lock, original f87 prepare/evidence and every previous FAIL are byte-preserved.
No sibling, shared tracked path, Shell, root or App is edited. Canonical Transport94,
SDK manifest/helper/locks remain exact; all old26 paths/93 schemas equal f87 inputs.

## Preparation and missing consumer evidence

`python3 ios/Modules/CJUsageClient/scripts/prepare_20aa_consumption.py <shared-repo>`
uses fixed Git inputs in own ignored `.build/20aa-consumption`. The graph contains
exact official sharedcc9, canonical AUTH, official SDK20aa and unchanged own business
sources. It refuses symlinks/differing existing bytes, preserving prior f87 snapshot.
No embedded new shared package or alternative product package path is introduced.

Actual checks (local author compatibility only):

- PASS all84 prepared input hashes before/after graph and test compilation.
- PASS actual package graph: all package identities have one path;2 CJFoundation
  references both point to ONE20aa export. Raw graph preserved losslessly as gzip.
- PASS actual SDK20aa/module compilation and2 targeted in-process consumer methods:
  canonical MESSAGE query→closed association→explicit original usage GET, plus legacy
  canonical NoRedirectTransport default GET. No new Memory feature/endpoint is called.
- PASS ordinary-import public source-flow typecheck against actual20aa module output.
- PASS old26 paths/93 schemas, manifest/helper/locks/Transport and business integrity.
- PASS staged diff whitespace check; previous unmodified business proof reused.
  No full suite, PG, keychain, device or iOS/App build repeated.

Reproduce from repository root after prepare, using accepted dependency caches:

```sh
swift package --package-path ios/Modules/CJUsageClient/.build/20aa-consumption/ios/Modules/CJUsageClient show-dependencies --format json
swift test --package-path ios/Modules/CJUsageClient/.build/20aa-consumption/ios/Modules/CJUsageClient --disable-automatic-resolution --filter 'OriginalUsageTests.acceptedCanonicalReceiptThenAssociationThenExplicitOriginalStatus|UsageTests.canonicalDefaultReadTransportWithGeneratedClient'
```

Evidence:20aa-preparation.json,20aa-compatibility.txt,20aa-consumption-tests.txt,
20aa-graph.json.gz,20aa-graph-stderr.txt,20aa-public-typecheck.txt,
20aa-public-and-integrity.json. Public compiler argv/raw graph SHA recorded there.

## Remaining complete App graph condition

This is only usage/shared/AUTH consumption compatibility. The original sibling in
this worktree still points33 and is intentionally untouched. Main/Publish must supply
exact sharedcc9/20aa export and align other active consumers to ONE20aa SDK in the
future Memory lifecycle Shell graph. It is not proof that the original mixed tree
or whole App builds. The existing f87/0d1e release gate continues against its own fixed
head and evidence; do not substitute this moving follow-up candidate into that gate.

No change to real sending/saving/cache/delete factory, shared authority or permissions.
New Memory lifecycle behavior and new wire gates remain independently owned. No
full App/CI/rendered UI/device, real account/keychain/cache/network/SQL/provider/fee/
dispatch/production acceptance or whole Issue9 completion is claimed. No push/PR/
merge/issue closure/message to another thread. Requested Sol6.1medium Standard/default;
effective UNKNOWN. All original FAILs and historical gates remain preserved.
