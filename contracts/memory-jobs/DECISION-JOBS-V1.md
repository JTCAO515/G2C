# Accepted-decision intake: MEMORY-DECISION-JOBS@1 / model3 / Pub3

C-owned local-runtime contract. Existing JOBS1, END-JOBS1, Data2/Output2/Pub2 and
their entry points remain separate. No failed-parse/version fallback is allowed.
This adds no model provider, Meter, cleanup role or second authoritative value.

The source is a genuinely committed full MESSAGE-send.3 discussion reference,
explicitly enabled for history, plus the same current accepted C Trip. Text,
manual-source flags and comparison DTOs do not grant either source. Full-record
references only: day/item/scoped-edit projections are refused in this version.

## Original command and API

```json
{"version":"MEMORY-DECISION-JOBS@1","job_id":"original-job","attempt_id":"original-attempt","source":{"conversation_id":"chat","generation":"gen","epoch":0,"after":0,"through":1,"source_version":1,"withdrawal_epoch":1,"mode":"incremental"},"decision":{"trip_id":"trip-original","expected_version":2,"content_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},"end":null}
```

Exactly these fields; original UTF8 bytes at most32768, original IDs unchanged.
Source reuses the existing1–100-message grammar. For conversation_end, end is the
full original `{conversation_id,generation,epoch,through}`; it must match the
source identity and cover the segment. The actual immutable full end is verified
before reading the segment; incremental reader mode grants no ending authority.
Missing/mismatched end, source/Trip version or digest, duplicate/extra keys,
boolean integers, another owner and unsupported selectors refuse.

The explicit `create_decision_collection_app` host installs:

- POST `/internal/v1/memory-decision/jobs`: enqueue only, no model dispatch.
- GET `/internal/v3/memory-decision/publications?job_id=...&attempt_id=...`:
  original Pub3 or null, account-only after source withdrawal; absence is not resend permission.

Both return `{version:"MEMORY-DECISION-response@1",request_id,result}`.
Trusted worker methods are `enqueue_decision_serialized`, `begin_decision`,
`prepare_decision_input`. The existing default collection host does not install
these routes or silently activate this producer.

## Genuine phase adapter for the B writer

`DecisionCollectionAdapter(collection)` declares
`publication_version="MEMORY-PUBLICATION-result@3"` and
`consumer_version="RUN-BACKGROUND@3"`. Its phase factories REQUIRE the keyword
`consumer_version="RUN-BACKGROUND@3"`; an old BG2 caller fails before preparation
or provider work. The version label is compatibility data, not source authority.

```text
processing_policy(context,token,jid,attempt,prepared_utf8,prepared_sha256,
                  *,max_payload_bytes,consumer_version)
publication_policy(context,token,jid,attempt,prepared_utf8,prepared_sha256,
                   output_utf8,output_sha256,
                   *,max_payload_bytes,before_commit,consumer_version)
query_publication_in_context(context,token,jid,attempt)
transition_original_in_context(context,token,jid,attempt,target)
```

B supplies its actual HistoryReadContext and original token, then invokes the
public `with_enabled_source(command.reader_query,policy,project)` (or genuine
joint source/Travel seam for a supported current message entry). Each policy
holds MESSAGE → actual C accepted Trip → canonical Memory. Processing uses
`policy.with_input(snapshot,local_work)`; publication uses
`policy.apply_original_result(snapshot,travel_lease=None)`. Local work must not
wait for a provider. All holders are released before model/network work.

The prepared outer `{system,messages:[{role:"user",content}]}` is materialized;
its content is Data3 with filtered opaque messages, actual accepted document,
opaque decision/anchor refs and decision_source_sha256. The current byte image
must equal the original at every phase and phase exit. Current Trip/consent/
Memory/admission changes refuse. `before_commit` is B's required original Meter
deadline/cancellation check, after C final rendering/source/auth and immediately
before canonical Memory COMMIT. No C work follows that check before that COMMIT.

## Output and authoritative publication

Output3 has exactly `{version:"MEMORY-EXTRACT@3",entries:[...]}`. Entries reuse
the finite subject/slot/kind/text/extent/occurred_at/evidence grammar; evidence
has exactly ref and quote, from an actual supplied message or decision document.
One reference per original message anchor per entry. Owner/tool/confirmation/
source fields and guessed refs/quotes are rejected. Historical documents are
data, never instructions or tools/consent/write authority.

Any Trip-supported conclusion remains a candidate, including model-declared
fact/experience/preference under a permissive direct-statement classifier.
Accepted plans prove a choice, not a visited experience or permanent preference.
User confirmation still uses MEMORY-CANDIDATE@1 and canonical Memory versions.

The logical accepted choice has a scope-bound digest over Trip id/version/content
hash and its original accepted action/proposal/candidate hash. Trip-supported
publication identity uses that choice plus canonical subject/slot/extent/context;
message-supported identity additionally includes the original message source.
The same choice across chats reuses the first item/review producer. M42 keeps the
decision digest and appends only admitted original refs; old NULL-digest origins
remain immutable. Source references are derived and cannot renew authority.

Pub3 has exactly Pub2's seven fields plus decision_source_sha256, with
version `MEMORY-PUBLICATION-result@3`. Job/attempt/enqueue/prepared/output hashes,
actual canonical operation receipts and source digest are checked on original
reads. The new B writer must explicitly accept/validate Pub3; BG2 remains Pub2.
Query/reconcile never republishes, renews consent or authorizes an unknown attempt.

## Retention and evidence boundary

The accepted document is an immutable comparison copy in the existing bounded
job batch (262144 bytes), not a new store/value. Same-PR memory-derived registry
and account hook cover the added bytes/digest/refs. #26 must also fence the
decision digest, clear matching candidate/source refs and overlapping copied jobs;
account cleanup is not item cleanup. No proactive Memory retention deletion.

C signed API/private PG currently proves durable enqueue/input/phase/Pub3,
same-choice cross-chat dedup/origin/first review, explicit confirmation and
historical receipt. C supplied outputs do not prove actual B worker/Meter/model
integration. That combination must use the original run_once/unique Meter/Fake,
limits/current admission/withdrawal/cancellation/ACK UNKNOWN and zero resend.
Real extraction quality remains #32 UNRUN; models/fees/cloud/device are UNRUN.
