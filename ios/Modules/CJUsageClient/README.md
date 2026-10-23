# CJ-008 original-attempt usage client

Current official accepted-MESSAGE source path: [ORIGINAL-USAGE-SOURCE.md](ORIGINAL-USAGE-SOURCE.md).
Current formal dependency candidate uses SDKdc29/shared9b, verified in an own-module
isolated graph (see evidence/DC29-CONSUMPTION.md); source behavior introduced on33
is unchanged. Prior f87 candidate remains fixed at7a1d478 for its separate integration gate. The original host-string UsageSource API below remains compatibility-only
and proves no official provenance.

Standalone, read-only iOS/macOS module. No CJShell/App wiring; not a charge,
balance, quota/reset, provider dispatch or retry implementation. Issue9 remains open.

## Original 49d146c inputs (historical)

- Base: `f4023e090c775a3540716320703a5d01d3b4daf3` (PR101).
- Dependency-only prep: `d62cf32b87f15df0c9869abb89fceb7263361630`.
  Exact `ios/Modules/CJMessageClient` tree from
  `e450e3828577feb211467e63177254f909b06b91`; exclude this prep from product diff.
  The prep replaces the independent clone's shared tree only, never Main/App graph.
- API SDK: `9d0f4b4c1e89b28d01de18092b5bf695de5bcde7`, exact official
  Package/lock/Sources/Tests exported under shared `.generated/<pin>/CJFoundation`.
  All seven old/new SDK exports are preserved as exact fixed Git blobs; hashes in
  `evidence/provenance.json`. No handwritten API DTO or auth substitute.
- Canonical AUTH remains unchanged from base f402. Its runtime Sources, manifest
  and lock are byte-identical to `8b6abb236cf10c1865a9cc8c6155bd8ac732c07e`.
  Uses actual CJSession SessionLifecycle / SessionOperation. Host context is NOT
  business authorization; server authorization remains authoritative.
- This module's lock is the conflict-free union of the existing shared and AUTH
  fixed locks, identical pin states to the existing CJShell lock. Other locks unchanged.

Integrators extract ONLY `ios/Modules/CJUsageClient/**` after prep. It requires an
explicit independent 9d SDK graph; do not replace the accepted c5 App graph.

## Public host interface

`UsageSource(attemptID:operationID:runID:)` carries the original trusted attempt.
Optional operation/run expectations must come from the same original evidence;
leave them absent if unknown. Never derive an attempt from message/run or mint one.
Response association is preserved verbatim; supplied expectations are checked by
UTF-8 bytes. Canonically equivalent Unicode with different bytes does not match.

`UsageBinding` captures that source, original canonical `SessionOperation`, opaque
actor identity bytes, host selection generation and revision. The host must allocate
a NEW selection generation on every switch (including A-B-A), supply the current
binding callback, and call `invalidate()` synchronously on session/selection change.
No persistence, attempt generation, KeyPurpose or implicit authority is added.

Construct `UsageViewModel(session:endpoint:credentials:currentBinding:liveReadTransport:)`
with a canonical `MessageEndpoint`, trusted credential callback and explicit canonical
`NoRedirectTransport`. Missing configuration/source/credential is unavailable.
There is no default endpoint or automatic network request.

On an explicit user action, call `prepare(originalBinding)` synchronously BEFORE
creating a Task. Then run exactly one `await model.read(prepared)` in that task.
Each preparation has a private model owner and generation installed before host
callbacks. Equal revision reentry cannot overwrite newer preparation. A preparation
can be consumed once, by its originating model only. A cancelled Task affects only
its own local read and never cancels an attempt on the server. The host manages Task
lifetime; this module does not start polling or retrying Tasks.

Read `model.state` for rendering. Bind it into
`UsageStatusView(state:language:readOriginal:)`; its button invokes only the supplied
explicit host action. It performs no on-appear request. No App integration is included.

The client invokes actual generated `Client.getUsageAttemptStatus` with ONLY original
`attempt_id` query. The wrapper enforces GET/bodyless/exact endpoint and operation,
no redirects, bearer hygiene, request/response byte bounds, JSON media type,
exact UUID trace agreement, no-store, duplicate-key/shape/type/decimal/null validation,
status/receipt consistency and original association checks. Lifecycle fences surround
credentials, transport, body collection, decode and final publication callbacks.
Generated decoder alone is not treated as semantic validation.

Amounts remain exact decimal strings beyond Int64; null stays unknown and actual
zero stays `"0"`. No float, arithmetic, clipping, prices or unit conversion. Bilingual
copy uses the formal historical state meanings; cancelled/exceeded records never
promise rollback, payment, current balance or a new dispatch permission. The backend
accounting algorithm is not reproduced.

## Reproduce locally

From repository root, export the fixed SDK Package/lock/Sources/Tests by Git blob
into `ios/Modules/CJMessageClient/.generated/<pin>/CJFoundation` (current pin33
and hashes in association-provenance.json; original seven exports retained).
Use accepted local SwiftPM caches and the committed module lock:

```sh
swift test --package-path ios/Modules/CJUsageClient --disable-automatic-resolution
swift build --package-path ios/Modules/CJUsageClient --target CJUsageClient \
  --triple arm64-apple-ios17.0-simulator \
  --sdk "$(xcrun --sdk iphonesimulator --show-sdk-path)" --disable-automatic-resolution
```

Module platform floor is a local compilation baseline, not a product minimum OS decision.
See `evidence/RESULTS.md` for exact author results and preserved failures.
