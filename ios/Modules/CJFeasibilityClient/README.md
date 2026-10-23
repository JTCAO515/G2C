# CJ-035 current NEEDS evaluation consumer — candidate CLOSED

Owned module only. Product base `02f672605ad5521f9360e42be8f43ebfd022a0e8`, Issue #18
remains open. No changes to NEEDS, Shell, Auth, root API, global locks or sibling
SDK export. This is a local typed consumer, not a second evaluator or API SDK.

Fixed inputs:

- Official API and wire `dc29bb3634e63d8f065c38d39a7a0059f76cfa53` from
  `cj-005-foundation/backend/cj_api/FEASIBILITY-CURRENT-WIRE.md`.
- Sole shared SDK export `9b4852dfad418d124d60366ada8efb380a8ffc1d` (parent cc9),
  canonical `.generated/dc29bb3634e63d8f065c38d39a7a0059f76cfa53/CJFoundation`.
- Canonical CJSession and Auth package fixed at this product base; canonical
  CJMessageHTTP transport94 bytes from shared9b485. Exact SHA manifest:
  [inputs.json](evidence/inputs.json). No new auth, credential store or HTTP stack.
- Existing NEEDS Presentation selection/snapshot is read-only design reference;
  this module neither imports that consumer nor changes its existing20aa graph.

`FeasibilityModel(session:currentBinding:)` is deliberately hard CLOSED. It has no
network endpoint, credentials, transport, environment defaults or enabling flag.
`prepare` refuses unavailable configurations and missing current host sources.
The module-internal fixture constructor cannot be used by ordinary host imports.
Testing this seam is not production activation or an acceptance shortcut. Future
activation must explicitly compose the canonical `NoRedirectTransport`, current
session host and credential callback after the original gates; no public generic
transport injection should be added for live callers.

A trusted host supplies the actual current account, environment, session lifecycle
operation/generation, selection UUID and existing NEEDS ID. The binding initializer
confers no authorization. New selection UUIDs are required on every change,
including A–B–A, and `invalidate()` is required synchronously on selection/logout/
account/environment invalidation. Host callback must reflect its actual state;
there is no UI-owned second source of identity. Optional accepted revision/hash
must be supplied together and are compared exactly to the observed response.

Capture opaque work synchronously before creating a Task:

```swift
let work = try model.prepare(actualCurrentBinding)
Task { await model.read(work) }
```

One use and one GET `/v1/needs-feasibility?needs_id=...` only; no retry, polling,
solver/history replay, writes, confirmation or persistent cache. Each callback,
await, response-body collection and final publication rechecks the original host
and canonical session. Reentry/late cancellation cannot fail or clear newer work.

The checked transport bounds request/response bytes, source bytes, nested JSON
depth and collections, rejects duplicate keys and malformed UTF8/JSON, redirects,
non-JSON, missing/no-store/duplicate metadata or request-ID mismatch, nonnull/shape
violations and foreign NEEDS. Official generated CJAPI remains the only wire DTO.
Source revision/action/input hash associations are validated without recomputing
the evaluator or reconstructing snapshot content. Content hash is syntax-checked
and, when provided, compared to the host's accepted hash; no freshness capability
or global atomic-latest promise is inferred. Source input UTF8 and decimal strings
remain exact. Declaration evidence remains arbitrary original JSON, including null.
Original errors including503 `FEASIBILITY_INPUT_INVALID` remain explicit failures.
No empty/null/INVALID success report, zero substitution or silent fallback.

`FeasibilityView` embeds in the existing NEEDS flow, with an explicit read button;
it never loads on appearance. It shows original bilingual checks, detail pairs,
missing paths, source revisions/hashes and report/evaluator versions. Status is
CONFLICT or UNKNOWN; overall is always UNKNOWN. Local PASS is not a claim of real
feasibility. No FEASIBLE status or save permission exists. Private original inputs
are in memory only, with no local persistence/logging; invalidation releases the
stored observation. Error presentation never exposes generated ClientError,
authorization-bearing requests, raw private error bodies or credentials.

Prepare fixed dependencies without writing siblings:

```sh
python3 scripts/prepare.py /path/to/cj-009-memory-api-pin /path/to/cj-005-foundation
swift test --package-path .prepare/Modules/CJFeasibilityClient --force-resolved-versions --skip-update
python3 scripts/check_public_api.py
```

`.prepare` snapshots fixed shared/Auth Git blobs and links the SHA-verified
canonical owner SDK export; it never changes a sibling manifest or copies a second
SDK. The owned Package manifest expresses the final expected sibling dc29 path.
The original whole App currently uses20aa and has NOT been repinned or tested.
Before host integration, original root/shared independent gates, accepted cohost
pin/compatibility and one unified App dependency graph must pass, then explicit
host enablement with real current-source/session wiring must be implemented and
reviewed. Source gate pending does not block local candidate work or enable live use.

See [evidence report](evidence/REPORT.md) for exact tested inputs and limitations.
Real route/HTTP, account/PG/C2, Keychain, provider, VoiceOver, device, whole App,
CI, merge/deployment/release and full Issue18 acceptance are UNRUN here.

Observation reentry P2 follow-up: the c607 candidate had a confirmed synchronous
notification race. State publication now keeps Observation notifications, validates
ownership before and inside/after notification, and stores a generation/binding
stamp. See [repair evidence](evidence/observation-reentry/REPORT.md). Original47
checks are preserved. Client/Shell combination remains HOLD until independent
Review and Testing approve the new fixed candidate. The public factory is closed.
