# LIO-memory-consent.1 — the account's consent to Lio memory suggestions (#1970)

Additive. No existing request, response or version changes. The server switch `CJ_LIO_MEMORY_CONSENT_REQUIRED` is off by default; while it is off, Lio behaves as before and the record below is never read.

## What the server does with it

With the switch on, memory suggestions (the candidates Lio offers to remember after an answer) exist only while the account's **last** consent record is `granted`:

- **No record, or the last record is `withdrawn`**: the server generates no suggestion (no preparation, no model call, no write); the one thing code may still do is write the marker `lio_memory_prompt:consent` for an account that has never chosen (`recorded: false`, never one that withdrew), so the App can ask once (`LIO-ANSWER-RICH-V1.md`, `rich.memory.prompt`): no model call, no preparation, no preference text stored; the `memory` field of a timeline row is `null` for every message, including suggestions generated earlier; `POST /v1/lio/memory/actions` for a suggestion (`remember` or `dismiss`) fails with the existing 409 "suggestion changed" failure and applies nothing.
- **A suggestion being prepared when the account withdraws** is not published.
- **Already remembered items** are not touched by a withdrawal. Stopping their use and erasing them stay with the existing Memory management and account erasure; the App says so in its own wording.
- The consent record is the only input. No request field, header or body of any other route carries consent.

## Routes

Same signed account and `application/octet-stream` body convention as `LIO-message.2`; no query string.

`PUT /v1/lio/memory/consent`

```json
{"version":"LIO-memory-consent.1","state":"granted","consent_text_version":"consent-2026-11","request_id":"c-7f3a"}
```

- `state`: `"granted"` or `"withdrawn"`. `consent_text_version`: the version of the consent text the App showed (1–64 of `A-Za-z0-9._:-`); the text itself is never sent or stored. `request_id`: 1–128 of the same characters, chosen by the App for each user action.
- Repeating a request with the same `request_id` and the same content is safe and returns the current state. The same `request_id` with a different `state` or `consent_text_version` is a 409. A request for the state the account is already in writes nothing and returns the current state.
- Every other field, a missing field or a wrong value is a 400. No token is a 401; an account that is not allowed is a 403; a server that cannot answer is a 503 (the App keeps its local choice and retries).

`GET /v1/lio/memory/consent`

Both return

```json
{"version":"LIO-memory-consent.1","state":"granted","recorded":true,"consent_text_version":"consent-2026-11","changed_at":"2026-11-27T01:02:03.456+00:00"}
```

An account that has never chosen reads `{"state":"withdrawn","recorded":false,"consent_text_version":null,"changed_at":null}`: not consented, and the App can tell "never chosen" from "withdrew". `changed_at` is the server time of the last record (UTC, milliseconds).

## The record

Append-only: each grant or withdrawal is one row (number, state, consent text version, request id, server time); the current state is the last row; rows are never changed or deleted by the application and go away with the account. The signed account can only read and append its own rows.

JSON shapes: `lio-memory-consent-schema.1.json`; examples: `lio-memory-consent-examples.1.json`.
