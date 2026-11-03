# MESSAGE-history.5

Frozen additive authenticated human-history read for #26/#472.

`GET /v5/message-history?conversation_id=<original>&limit=<bounded integer>`
accepts optional original opaque `cursor`. It uses the same current account AUTH,
trusted scope, cursor lifetime/size limits and final response guard as existing
history. No owner, operation, run or source selector. Old history versions are
unchanged; an old reader requiring a physically erased formal source withholds.

Response fields are exactly `request_id`, `version: "MESSAGE-history.5"`,
`messages`, `next_cursor` (opaque string or null). Each message has exact fields:

| Field | Value |
|---|---|
| receipt | Unchanged original MESSAGE receipt |
| original_utf8_base64 | Exact retained original MESSAGE input bytes |
| text | Retained original human message text |
| reference | Existing original versioned reference object, or null |
| source_state | `retained`, `erased`, or `not_applicable` |

`retained` means the existing strict source/reference reader succeeded, preserving
its original JSON. `erased` has `reference: null`, only after the exact original
formal receipt/selection and private hashed B cache-erasure proof are verified.
It means the model source cache was physically erased, while human chat remains.
`not_applicable` has `reference: null` for a legacy message with no such reference.
It grants no model context, source reconstitution, Trip write, resend, replay of a
deleted input or generic cleanup completion. The accepted formal Trip is retained.

Positive abbreviated item: `{receipt: <original>, original_utf8_base64: <original>,
text: "Explain the stored Trip", reference: null, source_state: "erased"}`.
Malformed/foreign cursor or scope, missing source bytes without original proof,
altered original selection/hash and retired account fail closed. Removing a source
cache is never represented as an empty successful source or inferred from absence.
Real tests validate preserved original bytes/Trip, actual erasure, missing proof,
foreign owner and unchanged old-reader failure. No App/native acceptance implied.

## RUN-display.6

The corresponding human assistant history is
`GET /v6/run-display?message_id=<original>` with the same original authenticated
MESSAGE/RUN reader and final source/owner/recovery guards. Exact response fields:
`request_id`, `version: "RUN-display.6"`, `snapshot`, `reference`, `source_state`.
`snapshot` is the unchanged bounded nine-field persisted display snapshot:
conversation_id, generation, message_id, run_id, message_sequence, status,
event_highwater, text, text_state. It does not include private events, inputs,
accounting commands, proposal/scoped-result authority or recreated C content.
Reference/source_state have exactly the history.5 meaning above. Missing original
RUN/proof/owner/current account access withholds. An erased input can be recovered
only as its positively proven original accounting header, never a fresh call.
Existing RUN-display.1 through .5 and scoped result semantics are unchanged.
