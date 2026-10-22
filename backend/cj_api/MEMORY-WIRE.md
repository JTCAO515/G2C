# MEMORY-WIRE@0.1.0-rc.1 candidate

Source base main `23e12f28435ab0ddc685d544670564e3fa79db41`. Sole wire
source: `contracts/api/openapi.json`; Python models and Swift types/client are
unmodified official generator output. Existing operations/schemas are unchanged.
Producer public API pinned by `memory_pins.json` to
`426d337b0647d7770f1716fad83f2e5e724d28e4` (core1ca / guarded f410 / first-manual9b / cancellation and ledger-hash426d); AUTH remains f3c8e507. Internal.1 is not a
MEMORY@1.0 product freeze. No backend/memory or CJShell writes.

| Operation | Path | Result |
|---|---|---|
| saveMemory | POST /v1/memories | historical committed active/candidate receipt |
| queryMemoryReceipt | GET /v1/memory-receipts?operation_id=… | original receipt or required explicit null |
| listMemoryGroups | GET /v1/memory-groups | subject/status/count groups |
| listMemories | GET /v1/memories?limit=…&after=… | live C-collation item-ID keyset page |
| getMemoryItem | GET /v1/memory-items?item_id=… | item/detail/source/time or required null |

Save body is `application/octet-stream` carrying **exact original UTF8 JSON**
matching OpenAPI MemoryManualSaveCommand and producer parse_manual (nine keys).
It excludes source_id/source_version; MemorySaveCommand remains the derived stored
detail shape. This corrects the un-frozen144fc70 reference-only POST; no backwards
compatibility with that rc is asserted. All accepted23e schemas/operations remain
unchanged. Freeze those bytes
and operation_id before the first attempt; preserve them for reconciliation.
No normalization, owner, source approval flags or implicit date/context is added.
Receipt.input_sha256 comes from the persisted operation ledger decoder for both
save and original query. It hashes original manual bytes, not the derived item or
source Command; the route never computes historical hashes or exposes raw ledger
bytes. Same-ID changed-byte conflict leaves the original hash unchanged.
Request IDs are fresh server trace IDs matching X-Request-ID under unchanged BASE
semantics; the original business operation_id remains independent and exact.

List limit is explicit (host maximum1..100); no implicit after, normalization or
localized ID comparison. `next_after` is the exact last item ID of every nonempty
page; null only for an empty page. A short final page may need one extra empty
read. Producer confirmed C UTF8 byte ordering. It is neither has-more nor a
snapshot/completeness guarantee. A saved receipt says nothing about later current
item effectiveness; no effective/model context API or RUN publication is exposed.

## Trusted composition

`create_memory_composed_app` requires explicit local environment, strict existing
JWTConfiguration/verification keys, the unique existing CJAccessProvider,
MemoryWireConfiguration and two host callables. Existing create_composed_app can
also inject the same memory configuration/binding/policy alongside MESSAGE using
the same existing verifier classes and unique AUTH provider. No zero-argument DB/client,
credential discovery, client source-registration route or production write channel:

- `resolve_binding(TrustedPrincipal) -> MemoryBinding(scope, Service)` binds an
  approved environment/profile and trusted issuer/subject/audience to a stable,
  non-reused server scope. Never use caller owner, source ID or token timestamps
  as a partition. It is called afresh at every guard stage, not cached per request.
- `source_policy(principal, scope, kind, command_or_none, argument, stage)` must
  return **True only after** explicit current source provenance/version/ownership,
  canonical subject/slot and applicable context ownership, purpose, sensitive
  collection/consent/time/retention checks. False/unknown rejects. This callback
  is trusted server configuration, synchronous and read-only; never populate it
  from client approval flags, mint slots, create approval rows or grant defaults.
  For reads it checks permitted resource access using the original argument.
  It is not an alternative AUTH provider. Missing policy/binding/config refuses
  composition; approved product collection policy remains absent.

The Service must be constructed by the trusted host with explicit server-owned
ManualPolicy before first manual save. Its immutable subject/slot/extent/context
sets, timezone-aware expiry and content_allowed / semantic_resolved callbacks are
mandatory and cannot originate from wire approval fields. Missing/expired policy,
unknown sensitive collection approval or unowned references rejects. Unresolved
semantics yields candidate; inference is always candidate. Policy callbacks are
not model calls or DB writers. Product collection/retention approval is not supplied
by this implementation; no permissive default is installed.

Only `Service.with_operation(guard, operation)` is used. Inside it the POST calls
`ctx.save_manual(original_utf8)`; reference save remains internal compatibility.
Producer atomically creates the server-derived manual source, item, original-byte
operation receipt and epoch under its scope lock. Replay reads the original receipt
and does not renew the source, consent or expiry. No source seed is needed. No consumer access to
Service.repository, transaction wrappers, alternate tables or approval writes.
Producer validates guard scope against its actual captured repository and requires
one identical TrustedPrincipal/scope and repository object at every stage.
Guard rechecks existing AdmissionChecker, resolves mapping, evaluates domain policy
and rechecks AUTH after callbacks that may wait. Exact stages: entry, transaction,
transaction_ready, precommit (inside DB transaction), private_return, return.
All projection, JSON serialization and byte-size checks finish inside this lifetime;
only fully encoded bytes cross the final guard and become an HTTP response.

This provides in-process fresh-check enforcement, not realtime session revocation
or an atomic distributed AUTH/database transaction. No claims of actual policy,
account or model acceptance follow from synthetic fixtures.

## Outcomes and recovery

Input/media/size failure is 400/415/413; a different-byte original operation or
canonical-slot collision is409. Entry access denial401/403 and unknown503 return
no private content. Source policy denial403 has no source/resource existence
information. Source/manual-policy unavailable/withdrawn or dependency failures remain503.
Cancellation/interruption is translated by producer into sticky OperationWithheld;
no caught precommit cancellation can release response bytes, and commit/projection
cancellation preserves original-action reconciliation metadata.

Commit ACK loss, postcommit access loss, projection/serialization/size failure
following a save, and guarded precommit rejection produce503 unknown with
`reconcile_original`. Precommit rollback for this call does not establish absence
of an earlier same-ID attempt. Preserve the original action; query it under newly
valid AUTH. No automatic retry, new ID, latest-item comparison or absent-receipt
inference establishes success/noncommit. Reads can withhold data even after a
successful read. Required null is distinct from absent property, invalid enum,
decoding failure or dependency unavailable. Swift generated oneOf null fallback
containers must have `value == nil`; never classify the case alone as null.

No request body, query URL, IDs, authorization header or exception string is
logged by the implementation. Responses retain no-store and BASE safe errors.
Storage registry1.2.0 records all four candidate tables and duplicated original
bytes. Physical cleanup/retention/restore fences remain UNIMPLEMENTED/UNDECIDED;
source approval expiry is not a content cleanup policy. Existing initialization
plan/registered migrations were not expanded; candidate schema apply is not a
registered upgrade or deployment.

## Executable checks

```sh
# Repositories are read-only sources of pinned Git objects, never moving imports.
UV_OFFLINE=1 ./scripts/check-memory-wire.sh AUTH_GIT_REPOSITORY MEMORY_GIT_REPOSITORY
UV_OFFLINE=1 ./scripts/generate.sh --check
./scripts/check-generated-memory.sh
```

No new package dependencies/lock changes. The scoped wire suite deliberately does
not rerun unrelated PR49/59. Generated Client transport checks are fixture-only,
not network/DB or App UI evidence. Source, author fixtures, private loopback/PG,
independent reviews, real accounts/approval resources, model next-answer use,
App/device and deployment evidence must stay separate. Issue12 remains open.

## Swift date configuration

Use `Client(serverURL: ..., configuration: .memory, transport: ...)` for MEMORY.
`ios/Sources/CJAPI/MemoryClientConfiguration.swift` combines the existing official
Runtime1.13.3 ISO8601 whole/fractional transcoders. It handles valid RFC3339 dates
with whole seconds, fractional seconds and offsets; invalid values still throw.
No timestamp truncation, new dependency, generator edit or old-client default
change. The first real PG run found this necessary: default `.iso8601` failed to
decode a valid microsecond recorded_at; the detail landed in a nonnull oneOf
fallback, which the consumer correctly rejected. Keep that explicit fallback
check after enabling the date configuration. The helper is the single reusable
MEMORY configuration for future clients, not a second generated client.
