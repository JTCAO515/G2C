# Accepted formal-detail byte snapshot — local author candidate

Base `b7966a1a95ed3e9b4c701f616693cf7e13d2d313`; head is the commit containing
this report. Only CJTripClient paths change. No dependency prep, SDK/Package/lock,
CJ022, root API, CJShell or AUTH implementation changes.

Read fixed CJ022 `24221d74e7d0ccb7f1d5afe27fa4384fc9c501ff`,
`contracts/offline-trip/README.md`; it explicitly requires an accepted-response
byte hook from the original Trip client. This candidate supplies that source seam,
not the offline adapter, storage factory or policy.

## Fixed public interface

```
TripClient.prepareDetailSnapshot(id: String, binding: TripBinding)
    throws -> TripDetailSnapshotRequest
TripClient.detailSnapshot(for: TripDetailSnapshotRequest)
    async throws -> AcceptedTripDetailSnapshot?
TripClient.validateDetailSnapshot(_: AcceptedTripDetailSnapshot) throws
TripClient.withCurrentDetailSnapshot<T>(_: AcceptedTripDetailSnapshot,
    _: (Data, Components.Schemas.TripRecord, String, TripBinding) throws -> T)
    throws -> T
TripClient.invalidateDetailSnapshots()
AcceptedTripDetailSnapshot.apiSourceCommit
    == c02cf08e52a0d8ffc2fefac99226654a7e01539c
```

Preparation is synchronous before Task creation. It captures client owner,
client generation, original binding/selection, requested Trip ID and source token.
Both public types have no externally accessible constructor or Codable/raw factory.
The request can dispatch once. A newer request or selection invalidates prior
sources even when account/binding values are unchanged. Retirement validates the
original binding and rechecks callback reentry before mutating the source. A stale
account/unbound UI cannot retire a newer source. Existing prepared detail UI work
also carries its original source, so older queued/in-flight reads cannot retire or
apply over a newer snapshot. Valid presentation selection and legacy reads retire
previous snapshot sources. Old detail
signature/record/null/error behavior stays intact; it issues no extra request.

The existing transport collects a bounded received body and applies its original
path/method, redirect, identity, duplicate-key and header/body trace checks. A
per-exchange internal buffer temporarily records only getTrip HTTP200; buffering
is not acceptance. The official generated Client then performs complete decoding
(including ensureNoAdditionalProperties), the existing formal-record/content/item
validator checks the record, the requested Trip ID and trace are matched, and
original session/binding/client/source lifetime is checked again before constructing
an accepted handle. No response encode/reencode is used by the feature, no new
wire model/parser, and no shared last-response buffer can mix concurrent exchanges.

The guarded read closure receives exact original body bytes, the same typed formal
record/version, exact request trace and captured original binding. Pre/post callback
checks withhold a retired result. The current guard takes only the sealed handle;
no caller owner/Trip ID/version can declare acceptance or relabel it after an await.
The handle's description/debug/Mirror are redacted. Consumers own their separate
pre-persistence/display fences; the synchronous read callback must have no side effects.

## Actual verification

- PASS:29 selected Swift Testing functions in4 suites (`tests.txt`):22 new snapshot
  functions (including parameter cases), plus7 existing directly affected detail,
  late-selection, receipt/latest, original-byte and final durability negatives.
  The rest of the original business evidence is reused, not rerun.
- New cases cover exact whitespace/escaped-Unicode response bytes versus a different
  reencoded body; same record/version/trace/binding; redaction; true null; illegal
  oneOf fallback; proposal/receipt bodies; missing/wrong/unknown fields, wrong Trip,
  zero version, content projection mismatch, duplicate JSON/trace mismatch; queued
  old selection, credentials callback switching selection, network/body collection
  awaits, final binding callback, consumer callback/await, retired official session
  operation, legacy read/UI selection/client invalidation, cancellation and no retry.
- PASS:known503 error/redirect produce no accepted handle; each original request
  dispatches at most one GET and cannot be replayed. No POST or cache file is created.
- PASS:unsigned generic iOS Simulator SDK build (`ios-build.txt`), locked dependency
  graph, no signing/launch. Package.swift and Package.resolved remain unchanged.
- PASS:compile-only `PublicConsumer.swift` imports only public modules and uses both
  new and legacy APIs. `ForbiddenConstruction.swift` fails compilation as expected
  for inaccessible constructors (`public-api-check.json` and compiler outputs).
  It is a deliberate negative fixture, not a failed product build.

## Failed attempts retained

- The first new test compilation put a throwing comparison in a Testing macro
  inside a callback. It failed before executing; moving the value outside fixed it.
  `initial-test-compile-failure.txt` keeps the diagnostic excerpt.
- First executed snapshot tests found two issues (`snapshot-first-run.txt`): a retired
  source across an await was obscured by generic exchangeUnknown, and one test
  expected invalidResponse where the official decoder correctly rejected an extra
  outer field during exchange. The new path now rechecks the original source on
  error before propagating it, producing staleBinding when retired. The extra-field
  assertion matches the actual decoder stage. Final29 selected tests pass; the
  original source-retirement failure is retained rather than erased.
- Closing audit added stale-retirement cases. An old account preparation initially
  retired the new snapshot before its binding was checked, and older prepared UI
  detail work could later retire a snapshot created by another source read. Both
  actually failed (`retirement-before.txt`, `old-ui-before.txt`). Retirement is now
  guarded before mutation and UI detail work preserves its original source for
  dispatch/result checks. Four added tests cover these cases, callback reentry
  and an in-flight UI read; final29 pass. A configured UI fixture is established
  before the source read; an unbound UI is explicitly denied retirement.

## Limits

This is author evidence on the fixed official generated Client with in-process
synthetic transports and new task-private fixtures. No real accepted-trip service,
real account, product HTTP, SQL, Keychain, cache storage/write, offline TTL/key,
remote revocation, trusted-clock policy, CJ022 integration, rendered UI/device,
CI, push/PR/merge/deployment or Issue closure was performed. Public POST remains
closed; unknown actions are not retried. Existing business HOLD/independent gates
are unchanged, and this new hook still requires original Review/Testing. It proves
current client acceptance only, not offline access authorization or provider facts.

Task-requested model: Sol6.1 / medium / default; effective model/tier was not independently verified.
