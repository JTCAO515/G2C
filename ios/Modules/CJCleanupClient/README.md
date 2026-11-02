# CJCleanupClient — original account and device cleanup

The fixed-candidate notes below describe the historical current-ALLOWED reader.
The additive M3 API@1 and DEVICE@3 implementations are documented at the end;
legacy read behavior is preserved. App/native acceptance is a separate gate.

Historical dependency-only increment: base `d749fdc3ca4a25c78e5f9cc0eba3f55113255798`
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
  <local>/Documents/Codex/2026-10-21/cj-009-memory-api-pin \
  <local>/Documents/Codex/2026-10-21/cj-005-foundation \
  <local>/Documents/Codex/2026-10-21/cj-007-auth
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


## M3 CLEANUP-API@1 account workflow (#443)

The old current-ALLOWED GET/view remains unchanged. `AccountCleanupClient` adds
explicit DEBUG iOS Simulator loopback-only device registration, original account
preparation, explicit confirmation, preparation query and restricted progress.
Release/unconfigured roots remain closed. The default App is not activated by
this module; the component acceptance app is a separate bundle, not CJProbeApp.

The actual verified SDK `SessionLifecycle`/operation and host-owned
`AccountCleanupLifetime` authorize ordinary actions. The host supplies a separate
WhenUnlockedThisDeviceOnly `SessionPersistence` slot for original bytes and
restricted capabilities. Never use the ordinary SDK slot, UserDefaults, raw files
or a bearer fallback for this journal. Native record namespace is checked against
the expected environment/account; a new in-memory generation may only query the
same persisted original. The lifetime must be invalidated when the selected
account/progress scope changes. Restricted reads do not regain ordinary rights.

Each explicit action captures opaque work synchronously. Request bytes are
saved/read back before the POST; only the actual bound service response creates
an operation or capability. Quiesce all business writers in `beforeConfirmation`
without retiring the original SDK operation before the sealed POST exit. After a
possible confirmation exits, the host reads `requiresRestrictedProgress` and
clears/blocks the ordinary SDK. A verified prepared/blocked ACK does not claim
revocation. All later reads use `Cleanup <original progress token>`, never that
token as Bearer. Last current GET and the historical confirmation ACK remain
separate. Ordinary credential or transport failures are returned as safe typed
failures rather than header/body-bearing exceptions.

Only a staged confirmation whose durable marker proves no HTTP dispatch can be
explicitly resumed with the same original bytes. A possible dispatch is query-only
forever in this client; no automatic retry/new operation exists. Unknown preparation
uses its original action GET; null does not unlock another POST. DEVICE@1/V2
currently have no read-by-action registration discovery, so registration ACK loss
stays UNKNOWN without a replacement ID or repeated POST. This and the initial
unknown device-call discovery gap were notified to B on #27 for an additive version.

No native erasure, device receipt or all-account completion is implied by these
APIs. The native component harness selects actual B-owned domains from the real
registry for a component positive, and separately checks the full real inventory's
missing-owner hooks remain blocked/prepared. It never supplies an operation ID or
progress capability to the App. Complete App UI/AX, all provided device storage and
key erasure, original device call/receipt and physical devices remain #27/#29.

## M3 CLEANUP-DEVICE@3 and normal App integration (#450)

`DeviceCleanupClient` consumes the accepted six `/v3` control paths. Registration,
call and receipt bytes are protected and read back before a POST. First ACK loss
uses the original action plus exact UTF8 SHA256 GET, or the original invocation
GET for a report. Null/errors do not permit another POST or an invented operation.
Only actual service responses create bindings, invocations and limited credentials.
An accepted call cannot be retargeted by a later account fence or response.

The DEBUG Simulator account root enables the normal Memory/Account deletion page
only with `G2C_DEV_CLEANUP_PROFILE=device-v3` and the existing explicit account and
offline profiles. Release/unconfigured roots stay closed. A verified online SDK
session enrolls the device; opening an explanation does not confirm account
removal. The user reviews the actual original preparation and explicitly confirms
it. Possible confirmation retires ordinary business access and the canonical SDK;
progress remains limited to that original operation. Reading a still-prepared
operation preserves its confirmation entry. A local stop does not imply online
cleanup completion or grant a device call.

Actual account verification and foreground legacy/structured Trip sync failures
share the V3 identity path. Only explicit HTTP401/403 enters the read-denial path;
a further signed identity check authorizes a session-invalid original call.
503/network/UNKNOWN cannot stage that call, erase cache, or renew its deadline.
Local 14-day expiry only denies reading. Offline-page reads perform no business
write, cleanup POST or queued action. A successful identity check alone renews
nothing; only another successful formal Trip synchronization renews the period.

The App resolves all19 fixed targets from its verified namespace and exact native
locations, never from response paths. Directory identities and existing key UUIDs
must match the recorded manifest before confirmation and first native execution.
Only a sealed accepted formal-source sync can provision a previously absent
Offline directory/key; an existing object cannot be replaced. Already-provided
journal families have their exact empty sidecars provisioned before enrollment.
No future storage, fake ciphertext, key or formal source is created by this step.

The original native execution and each target intent are protected before syscalls.
A started target is inspected without repeating an uncertain erase; untouched
original targets may continue. Shared keys clear only after all their named
journals verify empty. A verified outcome persisted before its first report can
explicitly submit that first report after restart. An already staged unknown ACK
remains GET-only. Partial/uncertain work is UNKNOWN, never confirmed.

Original cleanup evidence uses separate WhenUnlockedThisDeviceOnly, nonsync,
explicit Bundle-group slots in `G2C.CJAuth.session.<E>`:
`M3.Cleanup.Selected` and `M3.Cleanup.{Manifest,Execution,Device,Account}.<A>`.
These contain original scope, native identities, hashes, limited capabilities and
intent/outcome evidence; ordinary SDK credentials remain only in their canonical
SDK slot. Registration/retention/final handling of these provided control slots is
tracked on #27 and is not implied by the frozen19 business-cache targets.

`check_account_cleanup_component.py --native-device` runs the actual CJProbeApp,
signed local API, fresh restricted PG and unmodified worker/FakeProvider. The
legacy component cases remain the default. The positive projects only real B
registry leaves; full-registry missing C hooks must stay blocked. Actual App-created
message/Trip pending ciphertext and an accepted formal offline snapshot are
checked physically, with another account's hashes unchanged. Source preparation
uses the standard system size; cleanup states use actual system maximum type and
unfiltered `.all` AX audits. This remains acceptance-in-progress until its reports,
independent exact-head review and exact CI pass. Physical device/VoiceOver stays
#29 UNRUN; a current-device report never proves all devices/backups erased.
