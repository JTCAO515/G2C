# CJCleanupClient — current-account original progress

Current dependency-only increment: base `d749fdc3ca4a25c78e5f9cc0eba3f55113255798`
→ shared9b4852 / official SDKdc29 / Auth4eac0ad. No business source or lock change.
Old f87 (`6d5e318`) and 20aa (`d749fdc`) candidates, exports and evidence remain
fixed for their independent gates; do not substitute moving inputs into those graphs.

Issue #27 client component only. No CJShell/shared/root/backend writes. Default UI
is unavailable until the trusted host supplies provenance for an existing original
operation, current account/environment/session binding and current ALLOWED bearer.
There is currently no accepted production original-operation source/factory wired
into this component. A UI viewed flag or arbitrary UI ID is not provenance.

## Fixed inputs

- Baseline: `b33184fdc14c55098f2f21cd7e33d05b8a5d01f0`.
- Shared export: `9b4852dfad418d124d60366ada8efb380a8ffc1d`.
- Official single CJAPI: `dc29bb3634e63d8f065c38d39a7a0059f76cfa53`,
  `CJMessageClient/.generated/<pin>/CJFoundation`.
- `CLEANUP-PROGRESS-WIRE@0.1.0-rc.1`, producer source 514aba7/evidence 6635bb9;
  source-of-truth document: producer `backend/cj_api/CLEANUP-PROGRESS-WIRE.md`.
- Canonical Transport94 is exported byte-for-byte from shared. CJAuth is exported
  from fixed `4eac0ad8db0ac33c89c7cc5b88d66b58d0fd6a7e` in the Auth owner Git
  repository, not the older shared Auth snapshot. Neither is reimplemented.
  `evidence/sdkdc29/dependency-pin.json` records every exported SHA256.
  `StrictCleanupJSON` derives only generic JSON grammar from the existing usage
  consumer; wire shape/enums remain the official generated types.

The prepare script reads immutable Git blobs. Before writing any export it checks
that the shared SDK-pin manifest has its fixed SHA256, each official SDK blob
matches that manifest, and all existing destination bytes match. It refuses
symlinks/conflicting exports. It never writes producer/shared trees or generates
another SDK. Exports and build files stay ignored under this module.

## Host seam (remaining integration work)

`CleanupBinding` accepts a **trusted host's existing original operation** together
with the actual current account, explicit environment UUID and canonical
`SessionOperation`. Its constructor does not prove permission. The host must keep
`currentBinding` accurate and provide credentials only for that exact current
ALLOWED binding; the server performs authoritative admission. Without a trusted
source, supply nil and keep the view unavailable. No IDs are generated here.

Construct `CleanupViewModel` with the actual `SessionLifecycle`, explicit
environment, `maximumSteps` (1...128), bounded `MessageEndpoint` (response budget
1...65536), credential callback and explicitly constructed `NoRedirectTransport`.
There are no network/credential/production defaults. `CleanupProgressView` accepts
this model, English/Chinese language and an original-binding callback.

On an explicit user tap, call `prepare(binding)` synchronously **before** scheduling
`Task { await model.read(prepared) }`. A prepared read is owner/generation bound
and can be consumed only once. Read is exactly one official
`GET /v1/account-cleanup-progress?operation_id=...`. It cannot create/recover/delete,
execute hooks, retry unknown actions, restore permissions or query with postlogout
credentials. No background polling or automatic retries.

The host must call `invalidate()` synchronously on logout, account/environment/
operation switch, lifecycle invalidation and dismissal/cancellation, and cancel
its local task. The view does this on cancel/dismiss. The model also fences before
and after credential/transport/body awaits, after current-binding callbacks and
immediately before publication. State access clears stale projections; old results
and old failures cannot overwrite newer preparations. No persistence is added.

Response validation rejects redirects, invalid request-id/cache/media, byte/step
budget overflow, alternate JSON encodings, duplicate keys, extra/missing fields,
unknown enum values, invalid IDs/revisions, duplicate steps/reasons, mismatched
operation and contradictory `complete`. No truncation, percentages, empty success
or zero substitution. The view shows only status/revision/step targets/states/
reasons and explains the limited frozen-operation meaning of `complete`. Failed,
blocked, unknown, 404 and 503 never mean physical deletion has completed. Client
errors retain only safe typed classification; no request/bearer/error payload is
logged or stored.

The normal Package manifest uses canonical sibling CJMessageClient/CJAuth and
single official dc29 CJFoundation. The Package dependency is formally migrated;
isolated verification is not a substitute manifest. Whole-App publication still
requires all accepted peer manifests and shared inputs aligned to dc29 plus the
host combination gate. Fixed Trip `7bcab1b13bc683c205f3ff0fa4446657427a5225` is a
Main-supplied host graph input, not a dependency of this standalone cleanup module;
its fixed candidate gate remains separate. No Trip code or package was modified.
Only the host owner can connect a real trusted original-operation source.

## Local reproduction

From repository root (source trees read-only):

```sh
python3 ios/Modules/CJCleanupClient/scripts/prepare_dependencies.py \
  /Users/jtsm5p/Documents/Codex/2026-10-21/cj-009-memory-api-pin \
  /Users/jtsm5p/Documents/Codex/2026-10-21/cj-005-foundation \
  /Users/jtsm5p/Documents/Codex/2026-10-21/cj-007-auth
CJ_CLEANUP_ISOLATED_DEPS=1 swift test --package-path ios/Modules/CJCleanupClient \
  --filter 'explicitReadUsesOriginalGETOnceAndPreservesBlocked|unknownInProgressFailedAndLimitedCompleteRemainDistinct|unavailableNotFoundDeniedAndRedirectAreNotSuccess|oldResultCannotClearNewLoadedGeneration|credentialsAwaitSwitchAndLogoutFenceBeforeNetwork|loadedProjectionClearsOnLogoutWithoutAnotherRequest'
```

For this isolated lease only, `CJ_CLEANUP_ISOLATED_DEPS=1` selects the fixed exports
under `.deps/dc29bb3634e63d8f065c38d39a7a0059f76cfa53/ios/Modules`;
it is a build-time verification switch, not runtime
configuration or a second SDK. Unset it for canonical host integration once the
approved sibling graph is ready; do not combine isolated exports with host siblings.

From this module directory:

```sh
CJ_CLEANUP_ISOLATED_DEPS=1 xcodebuild -scheme CJCleanupClient \
  -destination 'generic/platform=iOS Simulator' -derivedDataPath .build/ios \
  -disableAutomaticPackageResolution -onlyUsePackageVersionsFromResolvedFile \
  -skipPackageUpdates CODE_SIGNING_ALLOWED=NO build
CJ_CLEANUP_ISOLATED_DEPS=1 swift package show-dependencies --format json \
  > evidence/sdkdc29/package-graph.json
```

Current dependency increment: `evidence/sdkdc29/RESULTS.md`. Prior 20aa incremental
evidence stays in `evidence/sdk20aa/**`. Original f87
19-function behavior evidence and initial FAILs remain unchanged in `evidence/RESULTS.md`;
the original `file-manifest.json` belongs to that old fixed snapshot. Independent review,
Testing, CI, host App wiring/rendering, real account/API/database/device/cleanup,
postlogout restricted query and Issue #27 closure remain separate gates.
