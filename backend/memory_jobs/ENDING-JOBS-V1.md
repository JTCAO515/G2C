# MEMORY-END-JOBS@1

Explicit new local runtime path for #411. MEMORY-JOBS@1 and its exact-head end
semantics are unchanged. This protocol uses the existing history_job/cursor,
result_bytes, candidate and origin tables, all already covered by memory-derived
cleanup. No new store, role, permission, model exit or automatic retry is added.

`POST /internal/v1/memory-ending/jobs`, octet-stream UTF8 JSON, at most 32768
bytes, has exactly version, job_id, attempt_id, source, end. IDs and source are
the existing MEMORY-JOBS@1 shape; source.mode must be conversation_end. `end` has
exactly conversation_id, generation, epoch, through (B EndQuery). It must match
source's conversation/generation/epoch and contain the entire requested segment.
Unknown/duplicate fields, wrong versions, empty segments and more than 100
messages per segment are rejected. Comparison DTOs never confer consent.

```json
{"version":"MEMORY-END-JOBS@1","job_id":"end-1","attempt_id":"attempt-1","source":{"conversation_id":"chat","generation":"generation","epoch":0,"after":0,"through":100,"source_version":1,"withdrawal_epoch":1,"mode":"conversation_end"},"end":{"conversation_id":"chat","generation":"generation","epoch":0,"through":101}}
```

Each operation first uses B's public SOURCE@1 at the exact full head to obtain
the genuine immutable end, then closes that C holder. It reads the segment
through the public incremental reader under the same captured outer identity,
unchanged generation/epoch and fresh per-conversation consent. This explicitly
versioned mapping is not a fallback when end verification fails. An unended
conversation never supplies an end, and the end cannot append. No nested source
holder, private B service, B SQL or invented ConversationEnd is used.

The persistent logical mode remains conversation_end. Completion advances its
own cursor; incremental and end cursors are independent. The canonical identity
is still derived from the original message/subject/slot/extent/context, so the
same evidence across incremental and end jobs reuses the same Memory operation.
Pending, inflight, UNKNOWN, original bytes, lifecycle/Memory epochs, original
result recovery and zero automatic resend retain the existing queue rules.

CollectionService.prepare_model_input_v2 produces the existing Data2 grammar,
including the genuine end_ref and all eligible messages in the segment. For B's
actual BackgroundJobs, install EndingCollectionAdapter explicitly and pass a
JobRequest whose query is the original segment with mode=incremental. The adapter
checks the actual full end on every bounded stage and rejects any other request
query, original job/bytes, interval or purpose. It uses the same typed output2
and publication-result@2; original receipt queries stay source independent.
No lease spans a provider wait. Candidate/inference requires the existing user
confirmation action, and generated Trip content cannot certify a long-term
preference or an actual visit.

The source-only read_ending_segment artifact remains private data and is never a
model message, queue permission or dispatch grant. Tests verify 101 actual signed
committed messages as exact 100+1 segments, real end/replay, consent, two accounts,
durable jobs and separate cursors, original results after host reconstruction,
typed publication and same-source incremental reuse. Supplied extraction output
is not a real-model quality result; actual background/Meter combination has its
own evidence and L2 remains #32.
