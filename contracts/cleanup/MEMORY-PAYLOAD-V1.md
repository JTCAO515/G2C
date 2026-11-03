# B-MEMORY-PAYLOAD@1 / RUN-MEMORY-HISTORY@1

Frozen additive local interfaces for #26/#472. CLEANUP@1.1, prior account
hooks, RUN-BACKGROUND@2/@3, MESSAGE-send.1/.2/.3/.4 and existing rc semantics
are unchanged. Only the explicitly approved dedicated `cj_local_cleanup` role
can redact stored payloads. This is not permission to activate real accounts,
cloud services or a model provider.

## Composition

```python
from cj_cleanup.memory_payloads import hooks, hold_payloads

# C's original create_erasure_app_v2 receives these explicit dependencies:
# resolve_backend_hooks=hooks, hold_payloads=hold_payloads
```

`hooks(store, scope, reader)` returns exactly `business/message`,
`checkpoints/run`, `business/usage` hook objects with synchronous
`execute(HookRequest)->HookReceipt` and read-only
`reconcile(HookRequest)->HookReceipt`. It requires the original memory-purpose
CLEANUP@1.1 root plan, original physical in-progress intent, subject/operation/
registry/entry/invocation/request digest and domain scope. Account and diagnostic
requests are rejected. C retains its four physical domain hooks and metadata;
B never implements or inspects C private tables through these hooks.

`hold_payloads(store, scope, association_bytes, prototype)` is C's
MEMORY-ERASURE-COMPOSITION@2 context manager. It compares the public
MEMORY-ERASURE-ASSOCIATION@1 against the original root plan, uses a fresh dedicated
connection, try-locks the owner payload barrier and each physical foreground/
background worker, and yields exactly True only while ready. Busy yields False
before any hook is dispatched; original steps remain pending. Parent transaction
locks are released before C commits a target intent. Session locks and the
thread-bound lease last only through that callback, then are cleared/closed.
Runtime writes to MESSAGE/RUN/job/source-cache tables take the shared barrier.
No polling queue, replacement IDs, destructive preflight or automatic resend.

Each executing hook obtains C's public original association. RUN additionally
uses original MEMORY-ERASURE-EVIDENCE@1 and `compare_prepared` to verify the actual
C enqueue hash, MessageRef/source text/document fingerprints, BG2/3 prepared bytes,
accepted-decision digest and original typed publication if present. Erased shared
jobs require prior B proof of that exact C enqueue hash. A live C job absent from B
gets a permanent hashed empty barrier; a later already-erased C job without B
proof stays unavailable. No inference from current items or an absent row.

## Erasure and retention

The selected item range is **owned_trip_derived_scope**, not an item foreign-key
claim. It includes proven original C message sources, B's real Memory model slot
with matching original source/version, and all owned formal Trip/draft-derived
RUN inputs/source caches (MSG3/4 and consider_trip). A user quoting a Memory prefix
or source ID cannot create a lineage. Inventory is bounded and fail-closed:
20,000 rows per scanned B table, 8 MiB per private payload, C's explicit bounded
association/evidence. Unsupported/corrupt/oversized original data does not complete.

- MESSAGE: keep exact original chat/raw_input, receipt and human-visible history;
  stop affected RUN IDs, clear related copied formal source_content/hash, acknowledge
  old delivery so it cannot be scheduled as a fresh model operation.
- RUN: keep original IDs, status, visible text_delta/effects and immutable original
  accounting command/config/hashes; null only positively proven model/tool/input
  copies for related RUNs and proven C BG2/3 input envelopes. Old writes to stopped
  RUNs and erased/empty jobs are rejected by restrictive RLS, including after rebuild.
- USAGE: no ledger DML, settlement, refund, zero-charge inference or new attempt.
  It confirms only after the original atomic RUN domain result is confirmed.
  UNKNOWN/outstanding billing evidence is retained; it is not diagnostic data.

M45's `cj_run_payload_erasure` holds only SHA256 owner/object/input/C-enqueue
digests plus finite kind/outcome. No raw scope, private IDs, source text or model
content. These permanent restore/write barriers follow C's irreversible hashed
erasure fences and are not 90-day diagnostics. Account admission still rejects
all sensitive access after retirement. Backups/restoration remain #30.
Minimal evidence readers can represent an erased original command internally;
fresh dispatch still requires an actual UsageBinding with bytes. Legacy bytes-
required original-usage wire readers withhold rather than mint a replacement.

The atomic domain result commits with B erasure. A lost commit/receipt ACK is
UNKNOWN; the same original request is reconciled read-only from that result.
Missing original result remains UNKNOWN. Reconciliation never deletes/reexecutes.
New deletion requests cannot remove unrelated owner/Bob data or change fees.

## RUN-MEMORY-HISTORY@1

Only the explicit host path in original `run_once` enables `memory_history=True`.
It wraps the actual C Runtime/Typed/Tracked Memory adapter, calling public
`capture_history` with the original canonical five message coordinates/hash and
genuine accepted Trip decision digests. No capture refresh or silent empty formal
set. Each actual model boundary invokes C's `with_history` to union later actual
source2 Trip decision context while retaining the original binding/principal/
snapshot/payload and all earlier references. The genuine C history fence is held
before model admission and final RUN/result publication; a late invalid source
cannot publish. Ordinary source text is never a provenance permission.

The old unadapted MSG3 + Memory producer/worker guard remains closed. C must
provide an explicit new compatible foreground producer/runtime before enabling
that combination. This contract does not invent or enable a service session.

## Positive and negative examples

Positive: actual signed C erasure API2, real BG2/Meter/Fake, typed foreground
consumer and dedicated B hooks erase copied payloads, keep chat/accepted Trip/
UNKNOWN ledger, recover a lost committed result via the original operation, and
construct a new context excluding the deleted item. Actual source2's second model
uses a real accepted decision digest through the public C reader.

Negative: worker busy leaves pending; foreign owner/purpose/intent, altered
original bytes/hash/protocol/publication, unsupported source cache, missing shared
job proof, out-of-callback lease, missing erasure proof or oversized inventory
cannot complete. Runtime has no DELETE/TRUNCATE/cleanup membership or erasure
proof writes. Original request/cost UNKNOWN is never relabeled confirmed.

Native/device/provider retention/real account/cloud/backup acceptance is UNRUN
here. Historical displayed chat and previously sent provider requests cannot be
retracted by this interface. App human history after source erasure is the additive
[MESSAGE-history.5](../message/HISTORY-V5.md), not an execution authority.
