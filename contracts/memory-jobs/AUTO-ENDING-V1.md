# Automatic incremental and genuine-end intake V1

`ConversationProducer(collection, submit, *, max_payload_bytes, max_conversations)`
is the explicit C worker composition for incremental and ended-conversation work.
`ProducerHost` installs it on the existing original worker's background seam.
The submit callback still prepares `RUN-BACKGROUND@2`; there is one registered
Meter and no new provider, daemon, automatic retry or public dispatch endpoint.

The producer reads only enabled C consents and public protected MESSAGE metadata.
`source_status_v1` must return a genuine persisted end before an ending job is
planned. Open/empty conversations produce no ending work; metadata lookup errors
propagate. Metadata never calls finish, grants history/Travel authority or replaces
the fresh source/end checks at enqueue, processing and publication.

The incremental cursor must reach that immutable end head first. Ending then uses
its independent cursor in 1–100-message segments, `MEMORY-END-JOBS@1`, the full
genuine end reference and Data2/publication3. Incremental and ending share the
account-basis serialization from SCHEDULING-V1: at most one pending/inflight/UNKNOWN
original at the current basis. `Service.enqueue_ending_serialized` is the new
trusted ending counterpart to `enqueue_serialized`; the old HTTP enqueue versions
and per-stream semantics are unchanged.

Ready ranges are ranked by processed cursor, then conversation ID; ties between
purposes prefer incremental. A pending end resumes exact original bytes/IDs after
host reconstruction. An old JOBS1 exact-head ending task remains on its explicit
old path. Inflight/UNKNOWN/failed/cancelled never creates a replacement attempt;
source withdrawal does not erase original publication or financial uncertainty.
Recovery queries/reconciles the original operation and never resends extraction.

This adds no store, role, retention or cleanup target. Jobs, cursors, checkpoints,
origins and end references use existing memory-derived storage and its cleanup
hook. Canonical items remain authoritative; ending extraction uses the same
source idempotency and candidate review rather than a second summary truth.

The actual signed API/PG/original worker/Meter/Fake check covers an open 101-message
conversation, incremental100+1 then ending100+1, pending host reconstruction,
outer MESSAGE ACK loss after C publication, original UNKNOWN reconciliation after
organizer disable with no extra model call, candidate confirmation using the first
producer, rebuilt Chinese model context and a second owner. Existing withdrawal,
expiry, source filtering and end-identity negative checks remain required.
Formal Trip-decision intake and item-erasure integration are separate unfinished
work; real model quality remains #32, and real models/fees/cloud/devices are UNRUN.
