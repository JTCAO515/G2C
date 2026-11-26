# LIO-answer-followups.1 — two-bubble layout and fixed action buttons (#1727)

Additive to `LIO-timeline.2` (`LIO-CONVERSATIONS-V2.md`). A poll that does not declare this version gets rows byte-for-byte as before; nothing else changes. No request body, no send route and no other timeline version changes.

## Declaring support

`GET /v2/lio/timeline?conversation_id=…&before=…&accepts=LIO-answer-followups.1`

- `accepts` is optional and has exactly one accepted value, `LIO-answer-followups.1`. Any other value, an empty value, a repeated `accepts`, or `accepts` on another route (`/v1/lio/timeline`, `/v3/lio/timeline`) returns 400.
- It is a read-side declaration only. It is not stored with a message and it does not change what the server writes or how it answers.

## Rows

For a declared poll each message row may carry two more keys; a row without the keys is a row the server has nothing to say about yet.

- `layout`: `"split"` or `"single"`. `split` means the App shows the answer in two bubbles, cut at the first blank line (`\n\n`); with no blank line, one bubble. The server fixes the value before the answer's first text, so every row of one message that has answer text, or a final status (`completed` or `failed`), carries the same value; a queued row (`sending`) before the answer starts may omit it. An account that is not on the server's list, a flat server, the code-written self description, and every reply that is not a normal answer (plans, edits) read `single`. A message that failed after the value was written keeps that value; the server never changes it afterwards.
- `followups`: only on a `completed` row that has answer text and whose `layout` is `split`, and only when the server has at least one button or chip. `{"version": "LIO-answer-followups.1", "actions": [{"tool": …, "parameters": {…}, "label": …}], "chips": [{"label": …, "ticket": …}]}`; each of `actions` (one or two) and `chips` (one to three) is present only when it has entries, and at least one is.

## Actions

The server chooses the buttons from this fixed table, from the traveler's question; the model never writes a tool, a parameter, a coordinate, an address, a URL or a label. The table is the App's tool registry (`LioToolRegistry`, #1724): a tool or parameter the App does not register is not sent. Adding one is a row here, in the App and in the server tests together.

| Button | `tool` | `parameters` | `label` (zh / en) |
|---|---|---|---|
| Payment setup guide | `payment-guide` | `{}` | 打开支付开通指南 / Payment setup guide |
| Taxi | `taxi` | `{}` | 打车 / Get a taxi |
| Taxi to a place | `taxi` | `destination` (Chinese name), `lat`, `lng` (decimal degrees, GCJ-02, at most 6 decimals, inside China), and optionally `address`, `destinationEN` | 打车去这里 / Taxi there |

Parameter values are strings, stripped, non-empty, at most 200 characters, with no control, separator, zero-width or bidirectional-format characters; at most 8 parameters, and at most 600 bytes of compact JSON in all. A taxi destination needs `destination`, `lat` and `lng` together, never part of them. A destination comes only from places the server already sent as tool evidence in this answer. This version of the server sends the first two buttons (no destination yet); the contract is the table.

The server re-checks every stored button when it reads a row and drops one that does not pass; a damaged record never puts an unlisted tool or parameter on the wire.

## App behaviour

- A bad or out-of-China `lat` / `lng` is treated as no destination: only the taxi page opens.
- A button whose tool is not in the build opens a "not available in this version" state; the server does not mark buttons as expired.
- Buttons stay tappable when the history is read again.

JSON shape: `lio-followups-schema.1.json`. Synthetic examples: `lio-followups-examples.1.json`.

## Tap-to-ask chips

A chip is a short question the traveler can send with one tap. The server picks it from a reviewed table by the topic of the traveler's question (payment, taxi); the model does not write it. Labels are at most 12 characters (Chinese) or 24 (English), single line, no control or format characters.

- **Row**: `chips: [{"label": "付不了怎么办", "ticket": "<43 characters, [A-Za-z0-9_-]>"}]`, at most three. A chip keeps its `ticket` for 24 hours after the answer; later rows show the chip without `ticket`, and the App shows it but does not offer a tap.
- **Sending it**: the App sends the chip like any typed question, `POST /v2/lio/messages` (`LIO-message.2`) with `text` equal to the chip `label` and one more optional field, `chip_ticket` with the chip's ticket. No other version accepts the field. A `chip_ticket` that is not a string is a 400; a string that is not shaped like a ticket is ignored.
- **Free questions**: the server counts the question against the daily question limit unless the ticket is spent for it. A ticket is spent, in the transaction that records the question, only when all of these hold: it belongs to the signed account, has not been used, is under 24 hours old, and `text` is byte-for-byte the label it was issued for (no trimming, case or whitespace folding); no other chip of the same answer has been used; the account has used fewer than 20 free chip questions today (Beijing day); and the chip is at most the third level of a chain (the answer to a typed question offers level 1, the answer to a level-n chip question offers level n+1). Otherwise the message is an ordinary question: it is counted, it is not an error, and the `text` the App sent is what is recorded.
- **No client flag**: the request cannot say "this is a follow-up"; whether a question was free depends only on the server having spent a ticket. A replay of the same message with the same bytes returns the original and does not spend or count again. Free questions still use the same model, tool and cost limits as any other.
- **History**: chips are shown when history is read again, without tickets after 24 hours.

JSON shapes: `lio-followups-schema.1.json`; examples: `lio-followups-examples.1.json`.
