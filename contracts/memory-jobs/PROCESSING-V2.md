# Explicit filtered processing V2

New background producers install V2 explicitly. V1 remains the prior separate
programmatic/data compatibility path; it is not a fallback for a failed V2 read,
parse, source check or publication, and is not claimed to meet all model-input
filtering acceptance. No new store, role or cleanup privilege is introduced here.

## Producer calls

The arguments and source reader protocol are the same as PROCESSING-V1.md, with
these explicit methods:

```python
prepared = collection.prepare_model_input_v2(token, job_id, attempt_id,
    max_payload_bytes=explicit_bound)
processing = collection.processing_policy_v2(context, token, job_id, attempt_id,
    prepared, prepared_input_sha256, max_payload_bytes=explicit_bound)
publication = collection.publication_policy_v2(context, token, job_id, attempt_id,
    prepared, prepared_input_sha256, original_model_output, model_output_sha256,
    max_payload_bytes=explicit_bound)
```

B uses its actual SOURCE@1 or SOURCE@2 reader and calls processing.with_input
with the actual snapshot before bounded local reserve/claim/intent work. No
provider or network wait spans the lease. Publication calls
publication.apply_original_result(snapshot, genuine_travel_lease) in the local
source callback. B records published only after the whole public source call and
both C/MESSAGE commits are known. Exact prepared and model-output hashes remain
distinct from B's full registered operation input/envelope hashes.

## Model data and evidence

The exact prepared UTF8 shape is still `{system,messages}`. A fixed system and
one user JSON data message contain MEMORY-EXTRACT-DATA@2: purpose, finite canonical
subjects/slots, max_entries/max_text_bytes, source_fingerprint, end_ref,
omitted_count and messages. Every message has exactly `{ref,text}`.

The model sees no raw conversation/generation/message ID. Ref is
`message-v2:` plus SHA256 of the versioned original coordinate/hash and scope
digest. These keys confer no grant. Source fingerprint binds the exact original
batch/versions; end_ref is the actual immutable B end ID. Original IDs and bytes
remain unchanged in private canonical source/attempt records, outside the model.

Before preparing, entering a phase and committing that phase, C checks current
source associations and item/source state under its Memory lock. Entire original
messages associated with pause, withdrawal, expiry or superseded explicit review/
edit are withheld. Unrelated canonical entries remain retained. An incomplete
provided history-source association fails closed, rather than treating missing
metadata as permission. Original chat display is retained.

The origin ledger is the immutable same-transaction producer/source association,
not an alternative authoritative Memory value or search index. Summaries do not
authorize this filter. Physical deletion's noncontent tombstone and original-chat
re-extraction barrier remain #26; the current extant-source filter is not claimed
as completed deletion or backup acceptance.

The output must be MEMORY-EXTRACT@2 with entries in the same grammar/kinds/scopes
as V1, but evidence is exactly `{ref,quote}`. Only currently permitted refs and
exact original quotes are accepted. Masked, foreign, forged or V1 message_id refs
are rejected. C maps permitted refs back to exact original committed evidence;
canonical publication identity stays the same across languages, V1/V2 data and
incremental/ending purposes. Inference still awaits explicit user review.

Original wire output is at most 16384 bytes. Private conversion to original long
IDs does not redefine or consume the model's original wire byte budget. Payload
data is explicitly bounded up to 262144 bytes, full source response to 524288;
overflow rejects without truncation.

If all messages are withheld, the prepared data has an empty inner messages list.
Processing/publication raises model_v2.NoEligibleSource before the local callback.
B stops/reconciles the original through the nonproductive metadata path; it must
not fabricate an empty provider output or a successful publication. This says
there is no permission in this call, not that an earlier unknown attempt cost
nothing. Original B Meter/attempt/hash/UNKNOWN evidence remains intact.

## Original receipt and current items

Publication persists MEMORY-PUBLICATION-result@2 with the same fields as result@1:
job_id, attempt_id, enqueue_input_sha256, prepared_input_sha256,
model_output_sha256 and original canonical receipts. Model output stays exact in
result_bytes; the typed original receipt uses the existing bounded candidate slot.
Checkpoint, canonical operations/items, source associations, cursor and receipt
commit atomically. Any caught publication exception still aborts the C holder.

`query_publication_v2_in_context` runs outside C holders, independent of the old
source grant, under current account admission. The standalone method and
GET `/v4/memory-publication-receipts?job_id=...&attempt_id=...` return
MEMORY-PUBLICATION-response@2. A non-completed original returns null, never a resend
grant. V1 and V2 readers reject each other's stored version explicitly; no failed
parse fallback exists. Original model evidence and actual immutable canonical
operations are checked. A receipt is historical, not current activation.

GET `/v4/memory-publication-items` with the same query returns
MEMORY-PUBLICATION-items@2, result `{job_id,attempt_id,memory_epoch,items}`. Each
item has the existing candidate projection plus review=null or
`{job_id,attempt_id}` for its real original review producer. A reused summary
candidate can therefore be reviewed with the original producer, without inventing
new task authority or duplicating it. Current version/status/value are separate
from the immutable publication receipt. The response is bounded to 524288 bytes;
oversize is explicit unavailability, not truncation. This read is not a new source
grant; confirmation rechecks the existing MEMORY-CANDIDATE@1 conditions.

## Evidence boundary

Actual private PG checks cover immutable source metadata, withheld raw content
and IDs, explicit-review supersession, same-source reuse, original review IDs,
all-withheld zero callback, typed original receipts and physical same-domain
cleanup. The original normal run_once/Meter/Fake, new process/CLI, two accounts,
Travel/current override, pause-inflight, withdrawal and expiry are also tested.
Extraction output is supplied. Actual background JobRun/model/Meter combination
is still B/C integration work; real model quality, cloud, fees and devices remain
UNRUN in their respective gates.
