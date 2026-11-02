# Processing source policy (dispatch/claim preparation)

This C-owned adapter is local runtime only. It implements the same hold protocol
as MESSAGE-SOURCE@1 and @2, but is not a Run/Meter/provider implementation or a
capability to resend an unknown attempt. No storage or cleanup privilege is added.

Inside B's original protected HistoryReadContext, call:

```python
policy = collection.processing_policy(
    context, token, job_id, attempt_id, original_input, prepared_input_sha256,
    max_payload_bytes=explicit_bound,
)
```

`context` is the actual outer context, not wire principal/scope fields. C binds its
own canonical repository and fresh checker to that captured identity. Original
input is the exact fully encoded `{system,messages}` from prepare_model_input;
prepared_input_sha256 is the digest of exactly those C-prepared bytes, retained in
B's original job descriptor. It is distinct from a registered Meter operation's
full-input digest if B wraps the request with other fields. A digest or prepared bytes
alone is data and confers no permission.

B installs policy in its public source reader. In its actual snapshot callback,
enter C's public wrapper before the registered exit callback:

```python
return context.with_enabled_source(query, policy,
    lambda snapshot: policy.with_input(snapshot, registered_step))
```

For SOURCE@2 use with_enabled_source_and_travel and its genuine lease as specified
by B. B retains responsibility for binding that selection to its original job and
actual registered exit; this dispatch adapter does not publish current Memory.

The policy holds C Memory below B's existing MESSAGE/Travel locks. It checks the
original job/attempt, exact source query, original Memory epoch, inflight state and
absence of output/checkpoint. with_input compares the actual protected messages
to the original C batch and renders the current exact model input under C's
server policy. Changed bytes, input digest, source, policy, Memory basis or phase
reject before registered_step. The callback receives the exact original bytes,
returns bounded bytes through B, and performs only bounded local claim/admission
or dispatch-intent work under B's unique Meter/Run/cancellation gates. No provider
or network wait may span this source lease. B's actual exit reenters the short
guard at its required dispatch point. C rechecks phase and fresh admission on return. Expired wrapper lifetime
cannot be reused.

Dispatch/claim cannot write a C checkpoint. The separate result adapter is:

```python
policy = collection.publication_policy(
    context, token, job_id, attempt_id, original_input, prepared_input_sha256,
    original_model_output, model_output_sha256, max_payload_bytes=explicit_bound,
)
# SOURCE@1 for long-term; SOURCE@2 supplies its genuine lease for current entries.
return context.with_enabled_source_and_travel(query, policy, selection,
    lambda snapshot, lease: policy.apply_original_result(snapshot, lease))
```

It accepts only the original inflight/unknown C attempt, unchanged source/Memory
basis and absent or byte-identical checkpoint. Every current entry derives its
Travel comparison from its actual committed typed evidence and must match the
genuine lease. A legacy source, mixed selections, missing/other/stale selection
cannot be inferred into Travel or silently become long-term.

Checkpoint, canonical entries/operations, origin, completed cursor and the original
typed publication receipt commit together. A caught error still poisons the C
holder and rolls all partial writes back. B must record its publication only
**after** the public source call has exited successfully, including C and MESSAGE
commits. Unknown commits reconcile original results, never provider retries.

`query_publication_in_context(context,token,job_id,attempt_id)` is a fresh-account
read independent of the old source grant. It returns original typed receipt bytes
or JSON null for a non-completed original; null does not authorize resending.
Call this read outside any C holder, before source entry or after source exit.
Standalone `query_publication` and GET `/v3/memory-publication-receipts` wrap this
as MEMORY-PUBLICATION-response@1. Stored results are checked against immutable
canonical operations and the original model entries/source before release.
They remain historical after pause, withdrawal, expiry or a new configuration.

The result has version MEMORY-PUBLICATION-result@1, job_id, attempt_id,
enqueue_input_sha256 (exact original C enqueue bytes), prepared_input_sha256,
model_output_sha256, and the original canonical receipts. It uses the existing
bounded 16 KiB opaque history_job.candidate field; result_bytes remains the exact
model output. The default legacy publish_output path keeps its existing raw
candidate format. Old completion does not fabricate a typed publication receipt
or trigger a failed-parse fallback; keep that old path until its consumers/data
and rollback are verified. The existing same-domain cleanup hook erases both.

`transition_original_in_context(...,target)` supports only cancelled/failed/unknown
metadata under current account admission, without renewing a withdrawn source or
granting begin/completion. Call it in the outer context, before entering any C
holder. Existing native transition rules and original IDs remain unchanged.
B never accesses C's transaction or SQL.

Source/phase/input refusals use cj_memory_jobs.codec.Conflict/Unavailable. Model
shape rejection is extraction.InvalidExtraction; native Memory/Message commit
uncertainty remains their CommitUnknown. The caller must reconcile the original
typed publication after uncertainty, not infer failure/zero cost or retry a
provider. B retains its separate original Meter state and monetary uncertainty.

Actual restricted-PG tests cover pending, changed bytes/digest/interval, lifetime,
checkpoint and valid original input. Their dispatch callback is a fixed marker,
not a model call. Result tests include inner/outer ACK loss, current-source
binding, caught-error atomic rollback, old-source receipt reads and cleanup.
Actual typed-source publication then drives the original normal run_once,
registered Meter/FakeProvider, process/CLI restart and scoped model requests.
Extraction output is supplied; actual background JobRun/Meter extraction remains
UNRUN until B's producer bridge is wired. Real model quality remains #32.
