# Lio conversations v2

Use the same signed internal-beta identity for both languages. A new Lio conversation has its own timeline and itinerary. Saved long-term preferences that the owner has authorized are available to that identity across conversations. The existing v1 routes and the account's original default conversation retain their v1 behavior.

## Send and resume

`POST /v2/lio/messages` accepts UTF-8 JSON with content type `application/octet-stream`.

```json
{"version":"LIO-message.2","message_id":"first-new-question","text":"What travel pace do I prefer?","locale":"en","new_conversation":true}
```

The first accepted message creates the new conversation and returns its ID in the same transaction. Save the ID for reopening. Continue a conversation by sending `conversation_id` with a fresh message ID. Omitting both fields sends to the original default conversation. A blank conversation can be presented locally before the first send.

```json
{"version":"LIO-message-receipt.2","message_id":"first-new-question","conversation_id":"lio-dialogue-12c1b3c6601251fa7ee290de44eea521"}
```

Retry a lost send with the same message ID and exact bytes. The ID is unique for the signed owner across conversations and versions. Different bytes for an accepted ID return 409. Replay adds no question or provider call. Sending both selection fields, sending `new_conversation: false`, using a foreign or unrecognized conversation ID, or submitting a version to the wrong endpoint returns 400. The existing owner admission, revocation, and daily question limit apply.

## Read and undo

- `GET /v2/lio/timeline?conversation_id=…&before=…` returns `LIO-timeline.2` with the v1 timeline fields. Omit the conversation ID to read the default. An explicit ID selects a Lio conversation owned by the signed identity. The cursor must be a message from that conversation. A foreign conversation ID or cursor returns 400.
- `GET /v2/lio/trip?conversation_id=…` returns `LIO-trip-history.2`, with the v1 history fields and the selected conversation ID. Send the same ID with `before` for pagination. An ID with no itinerary for the signed owner yields an empty history.
- `POST /v2/lio/trip/undo` accepts `LIO-trip-undo.2` with the original `action_id`, opaque `target`, and the selected `conversation_id`. `GET /v2/lio/trip/undo` accepts those three values as query parameters. Both return `LIO-trip-undo-receipt.2` with `action_id`, `conversation_id`, and `committed`. A target from another conversation returns 403. Keep the same action ID, target, and conversation ID to check an uncertain result.

Trip changes and message replay retain the original write, revision, and receipt checks. Remember, Memory management, and erasure keep their original signed endpoints. Model inputs use the current authorized Memory view, including the same edit and erasure boundaries as the default conversation.
