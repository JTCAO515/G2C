# Cleanup client SDK20aa compatibility increment

2026-10-23 Asia/Shanghai. Exact delta base:
`6d5e318e95ab5f2be25b21569f26b37df23546f9` (old f87 candidate).
This increment changes only this module's Package/prepare/current documentation
and additive `evidence/sdk20aa/**`. Runtime Sources, Tests and Package.resolved
are byte-identical to the base. No new type aliases, SDK, business behavior,
production factory, send/save/cache/delete path, Shell or peer tracked file.

## Fixed inputs and actual first write

First tracked write updated this module's Package.swift + prepare_dependencies.py
from shared507 / f87 to shared **cc9e2c3ba1fb8fe7582e5e4664a924b1c6b93f71** /
official SDK **20aa50ed5c8449e6026155a6151f22041dee7fd4**.
The immutable shared generated-pin manifest's SHA256 is
`71fec98555a93dc2fc1c9ad3ddcaf9cd209b5b885df50739505d2f9e633b78f7`.
All 66 exports are checked against fixed Git blobs and the official manifest
before writing to ignored `.deps/20aa50ed5c8449e6026155a6151f22041dee7fd4/**`.
Old `.deps/ios/**`, old tracked f87 evidence and old commit remain intact.
The selected build graph contains only the new official SDK; no f87 graph path.

## PASS — minimum incremental verification

- `compatibility.json`: all original **26 paths / 93 schemas** exactly unchanged
  from f87. Thus getCurrentAccountCleanupProgress request/response and enums are
  unchanged. All shared CJMessageClient/CJAuth Sources unchanged from shared507,
  including Transport94 / SessionLifecycle. Official helper, package manifests
  and locks compared byte-for-byte; unchanged hashes recorded.
- `prepare.txt`, `dependency-pin.json`: fixed input/source hash verification PASS.
  Original manifests/source/locks exported without rewriting generated code.
- `selected-tests.txt.gz`: **4 existing Swift Testing functions PASS under 20aa**:
  explicit original GET/one-time read; blocked/unknown/in-progress/failed/limited
  complete; 401/403/404/503/redirect; stale old result unable to clear new loaded
  generation. These are in-process synthetic consumer checks, not real accounts.
- `ios-compile.txt.gz`: generic iOS Simulator **BUILD SUCCEEDED** with
  `CJ_CLEANUP_ISOLATED_DEPS=1`, signing disabled; compiles unchanged SwiftUI and
  client against official 20aa generated symbols. No simulator boot or App launch.
- `package-graph.json`, `single-sdk.txt`: one CJFoundation20aa, one shared
  CJMessageClient, one CJAuth across selected package graph; zero f87 paths.
- Diff/whitespace checks PASS; only the authorized module changed. Complete delta
  file SHA256 list is `file-manifest.json` (manifest itself excluded).

Original 19-function f87 behavior evidence is reused from base6d5e, not rerun.
Original initial missing-try/ClientError failures and corrections remain in the
unchanged old evidence. No new incremental test or compilation failure observed.
Dependency resolver fetched package metadata for the new local path; resolved
remote versions and this module lockfile remained unchanged.

## Remaining integration boundaries

Main supplied root20aa/cohost82f merged PR109 as fixed context. This candidate
is a consumer compatibility increment, not evidence that the entire App graph
has been updated, reviewed, tested or merged. The Memory Shell owner must combine
its exact fixed consumer inputs into one 20aa graph, retaining the accepted
Session/Transport/helper/locks and actual lifecycle bindings. Normal Package
mode still uses canonical siblings; isolated mode is verification-only and must
not be mixed with sibling host packages.

Old Shell0d1e / cleanup6d5e f87 publication and independent gates remain separate;
do not silently replace those fixed inputs with this increment. Current new
candidate independent Review/Testing/CI/Publish remain pending/UNRUN.

No trusted original cleanup operation source has been connected. Missing source
remains unavailable. No new authority/credential, live sending, saving, deletion,
Keychain, database, device, provider or cache work. Whole App render/integration,
real account/API/database cleanup/postlogout restricted query/device acceptance
are UNRUN. No Issue closure or new business-function completion claim.
