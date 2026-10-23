# Observation publication P2 — author repair, independent gates HOLD

Parent candidate: `c607358dc8475a1fdcc90d05ad47ef8450503a04`.
Fixed/tested source: `49e2b577cf3c4cb35ba9ea4b3a16ec5264b179fc`.
Final candidate is the following evidence-only commit; no subsequent product edits.
Same root/branch/sole ownership: `cj-035-feasibility-client`,
`ios/Modules/CJFeasibilityClient/**`. No peer/Shell/SDK/Auth/backend or locks changed.

## Reproduction and repair

Read-only independent source directory:
`/Users/jtsm5p/Documents/Codex/2026-10-21/cj-testing/CJ-035-feasibility-ios`.
Exact original [ObservationReentryProbe.swift.txt](ObservationReentryProbe.swift.txt)
and [Testing FAIL](testing-original-fail.log) copied byte-for-byte here. The probe
was appended verbatim to the existing fixture. [author-before.log](author-before.log)
reproduces the same1 assertion FAIL: public state loaded needs-1 while the trusted
current selection was needs-2. The original15 functions47 cases did not cover the
Observation notification callback itself; their source prefix/logs remain intact.

The synthesized observable `stored` setter notified synchronously before its final
assignment. Observer reentry could prepare a replacement, then the old setter
assigned its old value under the replacement's ownership. Observing separate
mutable ownership fields could also split preparation across callbacks.

The sole product fix is FeasibilityModel.swift:

- Preserve @Observable and explicit `access(keyPath: \.state)` /
  `withMutation(keyPath: \.state)` state notification. Operational generation,
  binding and one-use bookkeeping change without intermediate UI callbacks.
- Before notification, after synchronous notification inside the mutation closure,
  and after mutation, validate original generation/current host binding/canonical
  session. Commit a single private generation/binding/state stamp without another
  callback. A callback that replaces selection prevents the old commit.
- Public state checks the stamp and trusted current binding; it withholds the old
  loaded value even during a replacement prepare's notification before assignment.
- Invalidation also checks its generation after notification and cannot clear a
  replacement. Stale completion/error/cancellation never clears or fails newer work.

No host-side hiding, disabled Observation, deferred synthetic success, new public
activation flag or changes to credentials/transport construction. Public factory
remains hard CLOSED; no live service was used.

## Actual verification

- PASS — exact original independent probe now passes [author-after.log](author-after.log).
- PASS — complete affected module suite,18 functions55 expanded cases, in
  [affected-tests.log](affected-tests.log): unchanged original47, original probe1,
  notification-reentry6 (prepare reset/loading, loaded, failed, cancelled,
  invalidation), and prior-loaded prepare-gap1. The six new reentry cases require
  observer callbacks to fire, retain the replacement's loading/token, then actually
  GET needs-2 and load its matching report. They do not pass merely by hiding all
  state or making replacement work unavailable.
- PASS — ordinary external import/public-symbol API checks, [public-api.log](public-api.log).
  Sole public model constructor still closed; work token remains unforgeable.
- PASS — local no-signing generic iOS Simulator arm64/x86_64 compile after repair,
  [ios-build.log](ios-build.log). Full local ignored log path and SHA recorded there.
  No simulator runtime/device/VO launch.
- PASS — exact original probe/Testing FAIL SHA equality; original47 test-source
  prefix, original logs/manifest unchanged; Package manifests/lock and fixed
  shared/Auth/SDK input hashes unchanged. [provenance.json](provenance.json).
  Existing single-dc29 graph evidence reused; dependencies did not change.
- PASS — owned-scope/diff-whitespace review. Source fix is40 additions16 deletions
  in the model, plus tests/documentation/evidence in the same owned subtree.

Supplemental test-helper compilation failed three times while resolving local
function actor/Sendable capture annotations. All logs are retained as
`author-fixture-*-fail.log`; final actor-owned helper compiled without unsafe
Sendable overrides and all55 cases passed. Product repair compiled and exact
original probe passed before that helper work. Original failure/47-case evidence
was not replaced or weakened.

Commands, from repository root:

```sh
swift test --package-path ios/Modules/CJFeasibilityClient/.prepare/Modules/CJFeasibilityClient --force-resolved-versions --skip-update --filter testingObservationReentryMustNotPublishOldNeedsUnderNewBinding
swift test --package-path ios/Modules/CJFeasibilityClient/.prepare/Modules/CJFeasibilityClient --force-resolved-versions --skip-update
python3 ios/Modules/CJFeasibilityClient/scripts/check_public_api.py
```

From `.prepare/Modules/CJFeasibilityClient`:

```sh
xcodebuild -scheme CJFeasibilityClient -destination 'generic/platform=iOS Simulator' -derivedDataPath .build/ios -clonedSourcePackagesDirPath .build/ios-packages -disableAutomaticPackageResolution CODE_SIGNING_ALLOWED=NO build
```

Independent Review/Testing of this new fixed head are PENDING; client/Shell
combination remains HOLD. No full App, real route/HTTP/account/PG/Keychain/provider,
permissions, VoiceOver/device, CI, push/PR/merge, deployment or Issue18 closure.
Original accepted source/cohost/host-activation and unified-App-graph conditions
remain separate. No external messages were sent.
