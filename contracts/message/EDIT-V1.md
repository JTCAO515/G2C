# CJ-MESSAGE-EDIT@1 / MESSAGE-send.4 / message-trip.2

B owner (#343), appended consumer version. Frozen interface source:
`backend/message/cj_message/edit_protocol.py`, `edit-schema.1.json`,
`edit-examples.1.json`. This first slice freezes L0 only; runtime, activation and
actual C consumer remain UNRUN until their respective delivery. It does not close #343.
Old send.1/2/3, message-trip.1 and all existing stored bytes/rejection tests remain exact.

## Original input and selection

POST `/v4/messages`, original immutable UTF-8 octets with the same body bound,
identity/head-CAS, duplicate/unknown-field and original-receipt-first rules as send.3.
Keep trip_id=null and creation_intent=none. New required field
`modification_intent` is `none` (discussion) or `propose_scoped_edit` (explicit user
request to generate a scoped candidate, never an acceptance). Model text cannot set it.

Required trip_context is exactly id, expected_version, content_sha256, day, item_ids.
Trip ID/version/hash come from the owner's actual formal structured.1/2 record;
never trust a read DTO as authority. Hash is lowercase SHA256 of original canonical
content. day is null or {date,timezone} using SEND-V3's declared local membership
rule, including minute/second midnight exclusion. item_ids is a unique list of
1–60 stable formal item IDs, or empty. A modification requires exactly one of
non-null day or nonempty item_ids; discussion may select the whole explicit Trip.
Day resolves to exact original member IDs, retained in the original reference.
C's sole scope/protect engine decides candidate changes; B does not add an engine.

travel_context is mandatory non-null {id,expected_version}, an independently
selected current owned TRAVEL identity. It is the actual temporary memory namespace.
It can never be inferred from Trip ID, dates, current UI, a latest record or text.
There is no namespace-free mode in this version. Missing/unknown namespace refuses
all consumption, rather than inventing an empty Context or using only long-term data.
needs_reference is null for discussion, and an explicit current owned
{id,expected_version} for propose_scoped_edit. Captured immutable NEEDS binding is
read by C using the original canonical reader/revision lease, not a copied engine.

Receipt/reference atomically pin original message/run/generation/sequence/input
hash, explicit modification intent, Trip/version/content hash/version, selection
and resolved IDs, namespace/version, NEEDS reference and continuous selection epoch.
The exact public MESSAGE-edit-reference.1 fields are version, message_version,
conversation_id, generation, message_id, run_id, sequence, input_sha256,
modification_intent, trip_context (the original send.4 selection),
resolved_item_ids, content_version, namespace={kind:travel,id,version},
needs_reference and selection_epoch. Internal reference data additionally exposes
owner_scope to trusted C code, never on the wire. source.reference provides this
immutable reference with public_value(); source.original_utf8/trip_content are
original bytes and source.selected_item_ids is the resolved tuple. C accesses
these named properties, not private fields. No reference constructor grants a lease.

Same-ID/same-bytes replay returns the original before fresh source/head checks;
changed bytes conflict. A→B→A never revives an old selection. Old Trip/hash, owner,
invalid member, missing source/namespace, stale NEEDS or consumer mismatch yields
zero new receipt/outbox/effect. No automatic ID, version or attempt refresh.

Malformed input400 INVALID_INPUT; source missing/foreign/unsupported/currentness
UNKNOWN503 MESSAGE_CONTEXT_UNAVAILABLE; owned version/hash/selection conflict409
MESSAGE_CONTEXT_CONFLICT. Errors retain original recovery semantics. A reference,
source DTO/hash or configured ABI is data/compatibility, never a write permission.

## Frozen C interfaces and lifetime

Trusted composition passes EditConfiguration(memory=<C implementation>,
publisher=<C implementation>), ABI CJ-MESSAGE-EDIT@1. Exact adapter ABIs are
CJ-MESSAGE-EDIT-MEMORY@1 and CJ-MESSAGE-EDIT-PUBLISHER@1. They are required actual
server dependencies, not caller JSON/READY tags, reflection probes or fallbacks.
The old MEMORY configurations cannot enable this new profile; missing adapter,
missing configuration, unsupported ABI or capture/currentness failure refuses.
Old message-trip.1's MEMORY refusal stays. C freezes its adapter separately in #344.

EditMemoryConfiguration.bind(database,scope,identity,admit,message_context=...) returns
C's RuntimeMemory interface, using original current_context/require_current,
typed eligibility/policy, version, pause/withdrawal fences and the same Meter.
The source's namespace descriptor alone is not a lease. Actual canonical
message_context.hold_for_effect(binding,source_lock=...) yields a factory-issued
same-authority/thread/lifetime object whose memory_namespace has kind=travel,
id/version and check(binding). C maps this real namespace to its existing travel
ContextRef; it must not map the formal Trip ID/kind, manufacture none, omit temporary
memory or silently turn memory off. read_original(binding) and capture(binding)
provide original data only. Captures are issued by B, checked against their actual
original receipt again, and not reconstructible from a caller DTO.

ScopedEditPublisher.prepare(binding,source) captures C's current NEEDS/protection
input before model IO and returns PreparedEdit(system,state). B alone calls its
registered draft model exit/Meter with original user/Trip/memory inputs plus this
bounded prompt; C does not create another model/tool exit. No SQL lease spans IO.
C state is captured data, not authority. B uses original operation identity and
unknown-exposure rules; no automatic redispatch on restart or UNKNOWN.

## One transaction publication seam (no Trip SHARE self-lock)

B message_context.publication(binding,capture,phase='proposal',deadline=...) opens
its canonical RUN transaction and the following outer source leases. phase=accept
is available to C's original confirmation path; it requires original completed RUN,
while proposal requires running. cancelled/failed/context_invalid/UNKNOWN refuse.
No wire field chooses a publication phase or supplies a transaction/lease.

Order: RUN owner/write fence → MESSAGE scope SHARE → independent TRAVEL row SHARE
→ C MEMORY fence → C NEEDS revision fence → C's sole Trip scope FOR UPDATE.
B holds no separate Trip SHARE connection in this branch. Ordinary text/discussion
uses short source checks and a Trip SHARE publication lease; these leases cannot
be carried into a C write transaction. Same selection/namespace/identity stays
held through the common transaction's commit. All gates use original binding.

1. B issues EditPublication with its actual scoped RUN cursor, source reference,
   live namespace lease and enter_source(contextmanager). C registers existing
   current-memory/NEEDS/protection leases/checks in this outer stack, which outlives
   the common commit. These checks run before deadline; no source SQL follows it.
2. C calls publication.lock_trip(). On that **same cursor/connection**, B takes
   canonical owner Trip scope FOR UPDATE and checks exact original Trip bytes,
   version/hash, selection and IDs. There is no independent B Trip SHARE left to
   upgrade and no second version/write engine. lock_trip returns original bytes.
3. C validates its same captured inputs, diff, scope/protect/output_check and
   original Proposal/ConfirmationSigner/act. publish_in_transaction uses the sole
   C _publish_in_tx on publication.cursor, with publication.before_write as the
   last guard before the write. It must not open/commit a second Trip transaction.
   before_write checks current original owner/run/message/selection/namespace and
   registered source checks, then the prepared original deadline **last**.
4. B records the original proposal effect through the existing RUN state machine on
   this same cursor; Proposal and RUN effect commit together. B never accepts it.
   For later explicit acceptance, C's original act writer checks the exact proposal
   and confirmation on this shared cursor; B's phase=accept gate grants no substitute
   confirmation. A checked Trip is locked through commit; own writes do not trigger
   a second comparison to the old version after mutation.
5. Commit ACK UNKNOWN reconciles the original receipt/action/effect/bytes, never a
   new ID/attempt. Cancellation ordered first refuses; publication ordered first
   retains its committed effect and cancellation does not pretend rollback/refund.
   C is responsible for feeding actual source/confirmation checks into its sole writer.

Source leases are opaque factory-issued live objects; every use checks authority,
original binding, thread/lifetime and fresh principal. B's new implementation uses
an active publication lease when RUN validates an effect, preventing any second
Trip SHARE query while C owns FOR UPDATE. DTO/hash equality cannot open this path.

## Additive recovery and explicit local host

New envelopes: MESSAGE-accept.4, send-status.4, edit-reference.1; MESSAGE-history.3;
RUN-display.4, RUN-cancel.4, RUN-draft-status.5. New routes /v4/messages,
/v4/message-send-status, /v3/message-history, /v4/run-display,
/v4/run-cancellations and /v5/run-draft-status. Original receipt/status/history/
response bytes and association stay immutable after source changes. Cancellation
uses original ownership, not a current Trip/namespace lease; UNKNOWN never retries.
Old reads cannot strip the new reference. Historical reads use their original version
or the explicit new history, not a reinterpretation of old raw input.

Local trusted factories accept edit_configuration=EditConfiguration(...) explicitly;
LocalDatabase and run_once use that same configuration. New profile/operator activation
requires registered M2, compatible adapter/publisher injection and real namespace
currentness. An upgrade requires resolved existing deliveries/RUNs. Legacy code or
unconfigured CLI refuses new-profile dispatch; no arbitrary module-path loader is
introduced. ABI settings are LOCAL, compatibility gates never replace ownership.
Runtime migration numbering follows the latest manifest (currently0026; no number
reserved by this L0 slice). No old activation script or applied migration changes.

Actual runtime/activation/schema tests, C #336/#344 and A #337 remain UNRUN in this
contract slice; #343 continues until all four frames have actual evidence. Real
services/models, fees, cloud/production and devices remain UNRUN.
