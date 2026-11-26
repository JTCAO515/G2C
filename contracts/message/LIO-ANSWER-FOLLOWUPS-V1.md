# LIO-answer-followups.1 — two-bubble layout and fixed action buttons (#1727)

Additive to `LIO-timeline.2` (`LIO-CONVERSATIONS-V2.md`). A poll that does not declare this version gets rows byte-for-byte as before; nothing else changes. No request body, no send route and no other timeline version changes.

## Declaring support

`GET /v2/lio/timeline?conversation_id=…&before=…&accepts=LIO-answer-followups.1`

- `accepts` is optional and has exactly one accepted value, `LIO-answer-followups.1`. Any other value, an empty value, a repeated `accepts`, or `accepts` on another route (`/v1/lio/timeline`, `/v3/lio/timeline`) returns 400.
- It is a read-side declaration only. It is not stored with a message and it does not change what the server writes or how it answers.

## Rows

For a declared poll each message row may carry two more keys; a row without the keys is a row the server has nothing to say about yet.

- `layout`: `"split"` or `"single"`. `split` means the App shows the answer in two bubbles, cut at the first blank line (`\n\n`); with no blank line, one bubble. The server fixes the value before the answer's first text, so every row of one message that has answer text, or a final status (`completed` or `failed`), carries the same value; a queued row (`sending`) before the answer starts may omit it. An account that is not on the server's list, a flat server, the code-written self description, and every reply that is not a normal answer (plans, edits) read `single`. A message that failed after the value was written keeps that value; the server never changes it afterwards.
- `followups`: only on a `completed` row whose `layout` is `split`, and only when the server has at least one button. `{"version": "LIO-answer-followups.1", "actions": [{"tool": …, "parameters": {…}, "label": …}]}` with one or two actions.

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
- Buttons stay tappable when the history is read again. Tap-to-ask chips are not part of version 1.

JSON shape: `lio-followups-schema.1.json`. Synthetic examples: `lio-followups-examples.1.json`.
