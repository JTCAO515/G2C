# MESSAGE-send.3 — formal Trip discussion (frozen consumer version)

Source: `trip-schema.1.json`; executable consumer `cj_message.domain.Command.parse_v3`;
positive/negative cases `trip-send-examples.1.json` and `backend/message/tests/test_trip_context.py`.
This is an additive version. send.1/send.2 and their parsers, stored bytes and original
receipts remain unchanged. The new version is independently consumable; it does not
require a change to the frozen root API or an iOS SDK update in this B-line PR.

## Send and authority

`POST /v3/messages`, `application/octet-stream`, original immutable UTF-8 JSON bytes.
Exactly send.2's fields plus mandatory `trip_context` (including explicit null).
`trip_id` remains null. `trip_context` is null or exactly:

```json
{"id":"trip-a","expected_version":1,"day":{"date":"2026-10-31","timezone":"Asia/Shanghai"},"item_id":"item-a"}
```

`day` and `item_id` may independently be null. IDs use the formal Trip ASCII identifier
grammar; version is an exact positive signed bigint, not a boolean. Date is canonical
ISO local date and timezone is explicit IANA (no device/default timezone).
Nonblank IDs/text, original UTF-8 conversation ID limit 256 bytes, exact expected
head CAS and duplicate/unknown-field rejection remain in force. No caller owner,
scope, source bytes/hash, current-Trip guess or authority fields are accepted.

A non-null formal Trip requires `creation_intent=none`, `travel_context=null` and
`needs_reference=null`: discussion only. It grants no Proposal, confirmation or
Trip write permission. #25 must use the original Proposal/confirmation protocol.
send.3 is discussion-only, always `creation_intent=none` and `needs_reference=null`.
A null formal selection may retain an independent travel_context for discussion;
creation remains on send.2 and its existing C publisher. travel_context is never a formal Trip. An ambiguous reference with null selection
asks for an explicit Trip/day/item, never the most recent Trip or parsed IDs in prose.

The source is the authenticated owner's current formal `cj_trip_record`, reached
through server-derived Trip scope, not through model text. This version accepts
only canonical `structured.1` (STRUCTURED-V1.md). It pins the original complete
content bytes and SHA256 in the receipt transaction. An item must belong to that
Trip; a selected day must have a declared member in the specified IANA zone. If both
are supplied that item must belong to that day. Unknown/missing/uncertain fields
are retained and never inferred from text, device timezone or another Trip.
A known start/end span in the same zone covers its explicit local dates; a later
midnight end is exclusive. With differing/unknown endpoints only a known endpoint
can establish day membership; a midnight end does not establish the following day.
This is selection membership, not a claim that an event is feasible or verified.

Missing/foreign/invalid source membership: 503 `MESSAGE_CONTEXT_UNAVAILABLE`;
owned version mismatch: 409 `MESSAGE_CONTEXT_CONFLICT`; malformed input: 400.
Foreign and absent IDs reveal the same error. No receipt/head advance/outbox occurs
on a rejection. Reconcile the original message; never substitute a new ID/version.

## Original results and lifecycle

Accept envelope `MESSAGE-accept.3`; status `GET /v3/message-send-status` envelope
`MESSAGE-send-status.3`. `MESSAGE-trip-reference.1` includes original message/run,
generation/sequence/hash, immutable selection epoch, context kind (`trip/travel/none`),
Trip selection, `content_version=structured.1` and content hash (both null unbound).
Public references contain no owner scope or source bytes and grant no authority.
Same-ID/same-bytes replay resolves the original receipt **before** current head/source
checks. Different bytes conflict. Trip changes never refresh that reference.

`GET /v2/message-history` returns `MESSAGE-history.2`, the existing bounded authenticated
cursor/page semantics plus each row's `reference` and original base64 bytes. Earlier
send.1/draft.1 rows have reference null; send.2 rows retain their original travel
reference. `GET /v3/run-display` returns `RUN-display.3` with the existing snapshot and
original reference. `GET /v4/run-draft-status` is the existing v3 outcome plus the new
original reference under `RUN-draft-status.4`. None grants fresh execution authority.

`POST /v3/run-cancellations` accepts exactly `RUN-cancel.3` + original message_id
(max 16384 UTF-8 bytes, body 65536), returns original run/status/event_highwater/reference.
Cancellation and UNKNOWN recovery work after a Trip update or chat closure; they
never invoke a provider, change the association or restore a terminal RUN. All private
projection occurs under the existing fresh signed AUTH entry/transaction/return guards.
Old endpoints do not silently decode a new reference. Reopen uses original raw bytes.

Execution checks the same active chat/generation, original immutable epoch and current
Trip version/content before dispatch and each published answer/completion. Same selection
continues its epoch; A→B→A does not resurrect old work. M scope shared lock precedes
Trip scope shared lock; C's Trip writer takes that Trip scope exclusively. The final
short output lease lasts through RUN commit, never across model I/O. Version/selection/
identity change, cancellation or UNKNOWN withholds late private output and never retries.
Pinned source data enters the registered model input/Meter path, not a second exit.

## Explicit local composition and upgrade

Requires registered M2 context, existing compatible `message-travel.1` and one-way
`message-trip.1` profile. API `CJ_LOCAL_TRIP_CONTEXT=message-trip.1`; worker
`--trip-context message-trip.1` together with `--travel-context message-travel.1`.
Activate using `scripts/message_trip_profile.py` with `MESSAGE-TRIP-CONSUMER@1`;
operator-only local metadata, no runtime profile write grant. Stop old workers first.
Pending deliveries/queued or running RUNs prevent activation. Existing original work
must be reconciled, not rewritten or ACKed merely to upgrade. Old binaries cannot
read/ACK/execute upgraded scopes through the restrictive ABI gate. New binaries retain
historical reads; unconfigured workers refuse dispatch.

Existing MEMORY scopes/configurations are refused pending an explicit C adapter for
this new reference. No memory is dropped, disabled or silently replaced. This restriction
has no implicit exit: C must explicitly deliver/verify that adapter before activation
of those scopes. The local append migration has empty up/down and populated-down refusal;
no applied migration or old frozen version changes. Real providers/cloud/fees UNRUN.
