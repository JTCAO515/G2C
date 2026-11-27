# LIO-answer-rich.1 — tappable places, tool cards, a save receipt and memory slots in one answer (#1984, F-2)

Additive to `LIO-timeline.2` (`LIO-CONVERSATIONS-V2.md`) and built on `LIO-answer-followups.1` (`LIO-ANSWER-FOLLOWUPS-V1.md`, unchanged). A poll that does not declare this version gets rows byte-for-byte as before. No request body, no send route and no other timeline version changes. Machine-readable shapes: `lio-answer-rich-schema.1.json`; examples (25 valid, 75 invalid) with the answers they point into: `lio-answer-rich-examples.1.json`; offline checker: `check_lio_answer_rich.py`.

**Status of the pieces.** This file fixes the wire. Each field is produced by its own ticket behind its own switch (D-1 #1989 entities, D-2 #1990 cards, T-1 #1994 receipt, M-1 #1999 and M-3 #2001 memory). Until a build declares the version, nothing here is sent.

## Principles

1. **The model writes text only.** Entities, cards, receipts and memory slots are made by server code from tables and from this turn's own tool results. A tool name, parameter, coordinate, place id or link in the model's output is never used.
2. **Fewer rather than wrong.** What the rules cannot decide is not sent. A place is linked only the first time it appears.
3. **Nothing unauthorised goes out.** Places that are not `approved` in the places library, memory items that are stopped or deleted, a prompt after the account withdrew consent, and a trip that is not the account's are filtered at every read.
4. **Every part fails alone.** A bad entity, card, receipt or memory slot is dropped on its own. `rich` never fails the page.

## Declaring support

`GET /v2/lio/timeline?conversation_id=…&before=…&accepts=<value>` — **one value**, now from two:

| `accepts` | Keys a row may carry besides the `LIO-timeline.2` ones |
|---|---|
| not sent | none, byte-for-byte as today |
| `LIO-answer-followups.1` | `layout`, `followups`; **never `rich`**; byte-for-byte as today |
| `LIO-answer-rich.1` | `layout`, `followups` (same values as the line above, except the `taxi` rule under `cards`) and `rich`; declaring rich implies followups.1 |

`400` for: an empty value; `accepts` twice (even with the same value); any other value, compared byte for byte with no normalisation (`LIO-answer-rich.2`, `lio-answer-rich.1`, a trailing space, `LIO-answer-rich`, a comma list such as `LIO-answer-followups.1,LIO-answer-rich.1` also as `%2C`); `accepts` on `/v1/lio/timeline` or `/v3/lio/timeline`; `accepts` on any route that does not take it; a misspelt name (`accept=`). It is a read-side declaration only: it is not stored and does not change what the server writes or how it answers; the effects behind `rich` are written whatever App reads them later.

**Switch** `CJ_LIO_ANSWER_RICH` (`off`|`on`, default `off`). With `off`, a rich declaration is **not** a 400: the row is exactly what `LIO-answer-followups.1` returns, without `rich`. With `on`, each part also needs its own switch: entities (D-1), cards (D-2), `trip_receipt` (`CJ_LIO_TRIP_AUTOSAVE` on at write time), `memory.prompt` (`CJ_LIO_MEMORY_CONSENT_REQUIRED` on), `memory.used` (M-3). The accounts are the ones in `CJ_LIO_ANSWER_LAYOUT_SUBJECTS_JSON`; there is no new list variable.

**Rolling back** to an image that does not know rich answers `400` to the declaration: the App then re-reads the same page with `LIO-answer-followups.1`, remembers that in memory only for 15 minutes or until restart, and tries rich again afterwards. An older image ignores the new effect prefixes (`lio_entities:`, `lio_cards:`, `lio_trip_receipt:`, `lio_memory_used:`, `lio_memory_prompt:`).

## `rich`

```json
"rich": {"version": "LIO-answer-rich.1", "entities": [...], "cards": [...], "trip_receipt": {...}, "memory": {...}}
```

`version` is required; at least one more key is present, each only when non-empty. An App that sees another version ignores `rich`. `entities`, `cards` and `memory` appear only on a `completed` row with a non-empty `answer`; `cards` also needs `trip = null` (a plan reply carries no cards, as with followups); `trip_receipt` may appear on a `completed` or a `failed` row (a save that committed before the answer failed still needs its undo); a `sending` or `answering` row never carries `rich`. The compact UTF-8 JSON of `rich` is at most **16384 bytes** (20 rows × 16 KiB stays far below the 4.5 MB page limit); if it is more, `entities`, then `cards` are dropped, never `trip_receipt`.

### `entities` — places in the answer text

`{"type":"place","start":5,"end":7,"place_id":"pl_bj_gugong"}`, 1–20 of them.

- `start`, `end`: a half-open range `[start, end)` counted in **Unicode scalar values** (Python `str` indices; Swift `unicodeScalars`) over the row's **complete `answer`**, as written: no normalisation, no Markdown stripped, no cut at the blank line between the two bubbles. `0 ≤ start`, `end ≤ 200000`, `2 ≤ end − start ≤ 32`. Counting in UTF-16 would be wrong after any emoji: in `上午去**故宫**，下午去景山公园看全景😀。\n\n晚上可以去王府井走走。` 王府井 is `[29,32)` in scalars and `[30,33)` in UTF-16.
- Both ends sit on grapheme-cluster boundaries: the character before `start` is not a zero-width joiner, a boundary is never between two regional indicators, and the character at `end` is not a joiner, combining mark, variation selector, skin-tone modifier, keycap or tag character. The span holds no line break, no edge blank and none of the Markdown characters `` * _ ` [ ] ( ) < > # | \ ~ ! ``.
- Sorted by `start`, no overlap, `place_id` unique (**the first mention only**).
- `place_id`: `^pl_[a-z]{2}_[a-z0-9]+(_[a-z0-9]+)*$`, at most 64 characters. The schema checks the shape only, so a new city needs no contract change. The server checks every id against the current places library and writes and reads only `review.status = approved` entries.

**How the server finds them** (D-1 follows this): the candidate places are those of the confirmed destination city and the cities of the trip bound to the conversation, intersected with the six library cities; if that is empty nothing is linked. Names are `name_zh`, `name_en` and the aliases; a Chinese name needs at least 2 scalars, an English one at least 4, English is compared case-folded, and a name containing a Markdown character is not used. Matching runs left to right, longest first, without overlap, on the final visible answer (after `display_answer` and the safety lines), and **skips** Markdown links, inline and fenced code and `https?://` runs. A Chinese match followed by one of `路 街 站 区 市 县 镇 村 号线 机场 大道 胡同 口`, or an English one followed by ` Station`, ` Road`, ` Street`, ` Avenue`, ` Line`, ` District`, ` Airport`, is not linked (王府井站 is a station); an English match inside a longer word is not linked. The code-written self description is not linked.

**Stored** as an effect `lio_entities:{"answer_sha256":…,"items":[[s,e,"pl_…"],…],"places":"g2c-places.1"}`. At every read the server recomputes the sha-256 of the answer it is about to send and drops **all** entities when it differs (the display rules changed, the self description replaced the text), then re-checks each entry and drops the ones that fail.

### `cards` — tool cards

`{"type":…,"label":…,"open":{"tool":…,"parameters":{…}},"data":{…}}`, at most 3, **one per type**, in this order. `open.tool` and `open.parameters` are what the App's `LioToolRegistry` takes; parameter values follow `LIO-answer-followups.1` exactly (strings, stripped, non-empty, at most 200 characters, no control, separator, zero-width or bidi characters, at most 8 parameters and 600 bytes of compact JSON, coordinates GCJ-02 inside the China box with at most 6 decimals), checked by the same function. `data` is for display only and every text in it is at most 40 characters under the same character rules. Labels come from this table only (Chinese at most 12, English at most 24 characters).

| `type` | `open.tool` | `open.parameters` | `label` zh / en | `data` | Sent when |
|---|---|---|---|---|---|
| `taxi` | `taxi` | `destination`, `lat`, `lng` together; optional `address`, `destinationEN` | 打车去这里 / Taxi there | none | the question is about a taxi and this answer's map result is exactly one place with a coordinate (the rule of followups.1 for a destination, the same `LioDestination`); **no destination, no card** |
| `metro` | `metro-guide` | `{}` | 看地铁线路 / Metro map | `city:{id,zh,en}` required; `route:{from,to,lines[1–4]}` optional | the question is about the metro and the confirmed city is one the App's guide has. **`route` is defined but 58.1 servers do not send it**: the answer tools have walking and driving routes only, and station data needs a transit tool that is a separate approval (P2) |
| `transport` | `transport` | `from`, `to`: ids from `lio_transport.CITIES`, different | 查火车和航班 / Trains & flights | `from`, `to`: `{id,zh,en}` | the question is about trains or flights and the fixed city table finds two different cities in it (or one, with the confirmed city as the other) |
| `currency` | `currency` | `{}` | 汇率换算 / Convert currency | `quote` one of `USD EUR GBP JPY KRW HKD AUD CAD SGD THB`; `cny_per_unit` (`^(0\|[1-9][0-9]{0,3})(\.[0-9]{1,6})?$`, above 0) and `as_of` (`YYYY-MM-DD`) together or neither | the question is about exchanging money; `quote` is found in the question by the fixed table (not found: no `data`); the rate comes only from the existing ECB cache of `CURRENCY.1` (older than 4 days or unreadable: no rate); **no supplier call on the answer path** |

On a row that carries a `taxi` card the `taxi` action of `followups.actions` is left out (and `followups` itself when that empties it): this is the only difference between a rich row and the followups.1 row. No business or medical card exists in this version.

**Stored** as `lio_cards:{"cards":[…],"issued_at":<unix seconds>}`; every read re-runs each card's checks (tool in the table, parameters as stored after the shared check, label from the table, `data` rules) and drops the cards that fail. A currency card whose `issued_at` is more than 24 hours old at read time is sent without `cny_per_unit` and `as_of` (the 4-day limit above is the age of the cached rate when the card is written; the 24 hours count from `issued_at`). `cny_per_unit` is above 0: `0` and `0.000000` are not rates.

### `trip_receipt` — what the automatic save did (ADR-0012)

| Field | When | Rule |
|---|---|---|
| `status` | always | `saved`, `not_saved` or `unknown` |
| `action_id` | always | the save's action id (`lio-plan-<run>` / `lio-edit-<run>`); `^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$` |
| `reason` | `not_saved`, optional | `conflict` (the traveler changed the trip meanwhile), `protected` (it would touch a point the traveler owns, change their order or add back a deleted place), `too_large`; an unknown value reads as "not saved" |
| `trip_id`, `committed_version` | `saved` | ids as in trip-history.4; version at least 2 |
| `summary` | `saved`, optional | `days` 0–14 × `{day 1–60, city {id,zh,en}\|null, added, updated, removed}` (each 0–99, at least one above 0, days ascending and unique), `wishlist_added` 0–99, `legs_updated` 0–99. **Structure only**: the App writes the sentence ("Beijing · Day 1: 3 places added"); no place name, no user text; the city is from the trip or the fixed city table |
| `undo` | `saved`, required | below |

`undo.state` is computed **at every read** from the database clock and the trip's current version: `available` (the current version is the committed one with the same hash, and now is before `until`), `expired` (after `until`), `superseded` (a newer version exists; only the latest save can be undone, ADR-0012 item 5), `undone` (the undo is committed), `unavailable` (the trip is gone, or this deployment has no undo route). `until` is the commit time plus 24 hours, UTC with milliseconds (`2026-11-28T03:04:05.678+00:00`), present in every state except `unavailable`. `action_id` and `target` appear **only** in `available`.

- `undo.target` **is** the `UndoTarget` of `LIO-trip-history.4`, all seven fields, referenced from `lio-trip-history-schema.4.json#/$defs/UndoTarget`; `expected_version = committed_version`, `restore_version = committed_version − 1`. It is a snapshot, not an authorisation.
- `undo.action_id` is made by the server: `"undo-" + first 40 hex of sha256(save action_id)`; two devices tapping undo send the same id, and a replay is safe.
- **The App undoes with the existing `POST /v4/lio/trip-undos`** (`LIO-trip-undo.4`: `version`, `action_id`, `conversation_id`, `target`) and, when the answer is unknown, asks `GET /v4/lio/trip-undo-receipts` with the same three values, never a new id. After `committed: true` it re-reads the timeline and the receipt reads `undone`. It never starts a write itself.
- `saved` is trusted only when the authoritative receipt table (`cj_trip_receipt`) has the row for `(scope, action_id)`; an effect that says `saved` without a row reads as `unknown`, and an effect that still says `unknown` while the table has the row reads as `saved` (the second effect may not have been written).
- With `CJ_LIO_TRIP_AUTOSAVE` off no receipt exists at all.

**Stored** in this order, outside the trip lock: `lio_trip_receipt:{"action_id":…,"status":"unknown"}` (the intent) before the commit, then `{"status":"saved"|"not_saved",…}` once the result is known; the last one wins.

### `memory` — memory slots (M-1, M-3)

`{"prompt":"consent","used":[{"item_id":…,"title":…}],"used_total":n}`, any non-empty subset (`used` and `used_total` together).

- The **memory candidates stay in the row's existing `memory.tags`** (`LIO-MEMORY-ACTION-V1.md`) and are decided with `POST /v1/lio/memory/actions` as before; `rich.memory` does not repeat or change them. The App shows at most 2 tags under the answer as real buttons.
- `prompt: "consent"` means "this answer holds a preference that could be remembered, and the account has never chosen": the App may ask once ("let Lio remember your preferences?") and writes the choice with `PUT /v1/lio/memory/consent` (`LIO-MEMORY-CONSENT-V1.md`), the only record of consent. The prompt is not consent. It is sent only with `CJ_LIO_MEMORY_CONSENT_REQUIRED` on, to an account whose consent reads `recorded: false` (never to one that withdrew), when a fixed, reviewed table of preference cues (taste, pace, budget, party, interests, way of travelling, language; **never health or religion**) matches the question. Code decides it, no model, and only the marker `lio_memory_prompt:consent` is stored. It prepares no suggestion and reads no memory.
- `used`: 1–3 items (`item_id` `^[A-Za-z0-9][A-Za-z0-9_.:-]{0,255}$`, `title` at most 40 characters, one line), `used_total` 1–99 and at least the number listed ("按你记住的 3 条偏好"). The source is only the memory items the server itself gave the model this turn, most relevant first; the model's claim to have used one is ignored. **Stored** as `lio_memory_used:{"item_ids":[…],"total":n}` — ids only. At each read the ids are re-projected through the authorised memory view: an item that is stopped, withdrawn, deleted or edited away is dropped and titles are the current ones; if none is left `used` is not sent.

## Order of writing

After the answer text is final (the safety lines appended), in this order: `lio_layout:` (before the first text, existing), `lio_entities:`, `lio_cards:`, `lio_followups:` (existing), `lio_memory_used:` and `lio_memory_prompt:`, then — on the trip path — `lio_trip_receipt:`. Each effect is at most 8192 bytes; a larger one is not written (audit line `LIO_RICH_EFFECT_DROPPED`) and the answer goes on. A failed write never fails the answer. If a prefix occurs more than once the last one counts.

## Reading

Every read re-validates every effect and drops what fails; nothing is trusted because it was stored. A poll that did not declare `LIO-answer-rich.1` **skips all of the above**: it reads no receipt table and no memory view, so its rows and its database work are as they were.

## App behaviour

1. `rich` is decoded with `try?`: a broken `rich` never fails the page (unlike `memory.tags`). Entities, cards and `used` are decoded one by one; an unknown `type` or a field that fails its rule drops that one. An array over its limit is dropped whole. Unknown keys are ignored.
2. **Entities.** Check every range on the raw `answer` through `unicodeScalars`: both ends must be `Character` boundaries, the piece non-blank without a line break; a failing one is dropped, overlapping or unordered ranges drop all of them. Render by replacing from the **back** each range with `[piece](g2c-place-<nonce>:<place_id>)` (a fresh random nonce per render), then parse the Markdown, then cut at the first blank line. After parsing keep only links with that nonce; **remove every other `g2c-place…` link** so the model cannot make one. An id the App's built-in library does not have is plain text. A tap opens a popover card in place; "more" opens the place page.
3. **Cards.** Known type and tool in the build: a tap opens it with the parameters as sent. Known type, tool gated off: the card shows and says "not available in this version". Unknown type: not shown. An out-of-China taxi coordinate is no destination: only the taxi page opens. The currency card says "reference rate" with `as_of`.
4. **Receipt.** `saved`: show the summary ("added · Undo"); the Undo button only in `available`, with the time left. `expired`, `superseded`, `undone`, `unavailable`: say so, no button. `not_saved`: say why, never retry. `unknown`: "confirming whether it was saved", re-read with the normal poll; after three reads still `unknown`: "the result is unknown, check your trips".
5. **Memory.** Tags are real buttons. On `prompt: consent`, if the device has not asked yet, ask once (#1747) and write the answer with consent.1. `used` reads "Based on what you asked me to remember: …" and opens the memory item.
6. **History** reads follow the same rules; a target that no longer exists (place retired, tool not in the build, trip deleted, memory stopped) was filtered or labelled by the server, and the App degrades without an error.

## Decisions taken (recommended by the draft; the coordinator confirms or changes them)

1. **Undo route.** The receipt carries trip-history.4's target and the App uses the v4 undo; T-1 makes that route usable for v2 conversations and puts the 24-hour check in the shared layer. If that cannot be done, `undo.state` is `unavailable` and `CJ_LIO_TRIP_AUTOSAVE` must not be turned on. It also goes on only for accounts whose App build declares rich, so that every save has an undo button.
2. **Metro stations** are not sent in 58.1 (see the table); `route` waits for a transit tool (P2, TL-5).
3. **The consent prompt is not "preparation"** in the sense of `LIO-MEMORY-CONSENT-V1.md` (code only, no model, no stored preference, only for `recorded: false`). If that is not accepted, `prompt` is removed and the App asks when the traveler first opens "My memory".
4. **Currency reads the existing ECB cache**, no supplier call.
5. **No new account list**: rich uses the `CJ_LIO_ANSWER_LAYOUT` accounts.
6. **A `failed` row may carry `trip_receipt`**, because the undo must not be lost when the answer fails after a save.

## Review checklist (red line: contract)

R-1 the three byte-for-byte cases (no `accepts`, followups.1, rich off) with a golden sample and no extra database read · R-2 the 400 rules, rich only on `/v2/lio/timeline`, `off` never a 400 · R-3 rollback: older images ignore the new effects everywhere effects are read (timeline, display snapshot, summaries, export, erasure) · R-4 no model-made clickable content, the App strips `g2c-place*` links · R-5 card parameters traced to this turn's tool results or a fixed table, re-checked at read, one shared parameter function · R-6 entity accuracy: scalar unit, answer hash, grapheme safety, first mention only, `approved` only, Q-1 accuracy ≥ 98 % · R-7 receipt truth: `saved` only from the receipt table, undo state computed at read, 24 h in the shared undo layer, `unknown` never starts a write · R-8 memory: tags not redefined, consent record the only consent, withdrawn accounts not prompted, `used` ids only and re-projected, no health or religion cue · R-9 privacy: entities are ids and offsets, cards public places and cities only, no user position, contact or document, receipt without place names, `Cache-Control: no-store` unchanged · R-10 every limit has a negative example · R-11 failure isolation · R-12 scope: no business or medical card, no new supplier call · R-13 the App registry, `lio_transport.CITIES` and the metro city table agree with the card table.
