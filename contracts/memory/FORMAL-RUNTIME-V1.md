# Explicit formal-reference Memory consumer

Local runtime only; C-owned `CJ-MESSAGE-FORMAL-MEMORY@1`. This is a trusted Python
composition ABI, not a new MESSAGE body, original-reference wire, Memory payload
or persisted context namespace.

## Existing consumer defect and version relationship

The already merged MESSAGE-send.3/formal Trip consumer and canonical Memory cannot
currently coexist on one account: main `scripts/run_worker.py` rejects a Trip
profile when a Memory scope/configuration exists (`formal Trip MEMORY adapter is
not installed`); the old signed v3 producer also remains closed in that case.
The genuine signed MSG3/accepted Trip/Memory PG regression reproduces both guards.
This ABI supplies the missing C reader for an explicitly compatible B host.

Within that new host only, this replaces the TypedRuntimeConfiguration V2 context
selector, whose contract does not interpret a formal Trip as a Memory Travel.
It retains the exact MEMORY-RUN-CONSUME@2 payload and typed collection/selection
grammar. V2 still has actual Travel/none worker consumers; it is not retired.
Old v3 receive/activation/worker guards remain closed. Installing this C factory
alone does not activate an old B path or prove the full foreground integration.
New code requiring formal references uses this explicit ABI, never a failed-read
fallback to V2/legacy or a model-supplied context identifier.

## Configuration and binding

`cj_memory.formal_runtime.FormalRuntimeConfiguration.from_bytes(original_utf8)`
accepts the exact root keys `version`, `collection`, `selections`, bounded at
262144 bytes, with version `local-memory-formal-run.1`. Collection and selections
are exactly the existing [TYPED-V2](TYPED-V2.md) `local-memory-run.2` structures;
there is no additional consent, subject, slot or context grant.

```python
runtime = configuration.bind(
    database, scope, identity, fresh_admit, message_context=original_authority)
# For a read that must not create a scope:
runtime = configuration.bind_readonly(
    database, scope, identity, fresh_admit, message_context=original_authority)
```

The authority must be the actual MessageContextAuthority for that same repository
scope; fresh admission must identify the same issuer/subject/scope and configured
identity. The host supplies canonical objects, not booleans, client descriptors or
fixtures. Readonly binding refuses an absent Memory scope. Ordinary binding uses
the existing scoped bootstrap/retirement fence; no cleanup role is involved.

## Selection, lifetime and model input

Each capture uses the original Binding and the authority's genuine
hold_for_effect/reference. The original B checks still verify owner, original
message/run/hash/generation/selection epoch and the current formal/Travel lease.

- A genuine `trip` reference selects long-term Memory only. A Trip ID is never
  converted to a Travel ID or persisted as a new Memory context kind.
- A genuine `none` reference also selects long-term only.
- A genuine `travel` reference selects the existing exact Travel current values,
  with the existing long-term slot override rules.
- Any other reference kind is unavailable; no empty-success or implicit fallback.

The runtime inherits the existing filtered canonical reads, current item/source/
expiry checks, captured epoch, fresh admission and final publication holder.
`capture_history` and `with_history` use the existing HistoryFence1/WithHistory1:
union only genuine added message/decision references, preserve the original
snapshot/payload, and reject currentness/erasure failures before model and final
publication. The payload remains data, never system instructions or source rights.
Original UNKNOWN attempts and charges remain original; this ABI grants no resend.

## Storage and evidence boundary

No new table, context kind, migration, role, cleanup hook, index, queue, Meter or
provider is added. Existing Memory and history fences/cleanup remain authoritative.
Actual limited-PG tests use genuine signed accepted Trip/MSG3/Travel/none, typed
Memory saves, original worker/Fake setup, owner/admission negatives and signed pause
invalidation; they preserve both old producer/worker denials. The compatible B
foreground producer/worker must separately consume this exact ABI and prove actual
model inputs and final publication before #411's combined frame is complete.
Real extraction quality, provider fees/cloud and devices remain #32/#29 UNRUN.
