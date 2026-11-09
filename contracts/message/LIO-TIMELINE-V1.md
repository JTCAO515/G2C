# LIO-message.1 and LIO-timeline.1

The Lio app uses the current signed internal-beta identity. Each account has one
Lio conversation across both languages. Its Travel context is created on the
first accepted message or resolved from the owner's existing default.

## Send

`POST /v1/lio/messages` takes UTF-8 JSON as `application/octet-stream`.

```json
{"version":"LIO-message.1","message_id":"first-question","text":"Where can I take a walk in Beijing?","locale":"en"}
```

The client can include the previously returned `conversation_id`. The response
has `version: "LIO-message-receipt.1"`, `message_id` and `conversation_id`.
The client may retry a lost send using the same message ID and exact request
bytes. The server checks the original on an uncertain commit and returns its
existing result when present. A message ID reused with different bytes returns
409. Replaying an accepted send consumes no additional question or provider
call. A new send over the existing 40-question daily limit returns 429 with
`{"failure":"quota"}`. Bearer identity, owner isolation, and revocation apply
to send and replay.

## Timeline

`GET /v1/lio/timeline` returns a snapshot that the client may poll after a send
or reconnect. Parameters are optional `conversation_id` and `before`. A
snapshot contains up to 20 messages in original send order. The client uses
`next_before` to load an older page. A supplied cursor must identify a Lio
message in the same active conversation. Before the first message, the timeline
has an empty array and null conversation ID and cursor.

```json
{
  "version": "LIO-timeline.1",
  "conversation_id": "lio-dialogue-12c1b3c6601251fa7ee290de44eea521",
  "messages": [
    {
      "message_id": "first-question",
      "text": "Where can I take a walk in Beijing?",
      "answer": "You can take a walk through a neighborhood park.",
      "status": "completed",
      "failure": null,
      "activity": null,
      "sources": [],
      "trip": null,
      "memory": null
    }
  ],
  "next_before": null
}
```

Display status is `sending`, `answering`, `completed`, or `failed`. Answer
text during `answering` is the committed prefix. Activity is null or one of
`checking_places`, `checking_weather`, or `checking_travel_information`.
It reflects a prepared service operation on the original answer. A source contains `title`,
`url`, and `observed_at`; a missing observation time is null. Sources come
from observed service evidence. Trip and memory attachments are nullable. A
client-observed connection error maps to `network`. Server failures use
`quota` or `unavailable`. A lost model result retains its original terminal
status internally and is never dispatched again by a timeline read.

A saved trip has `trip_id`, `title`, and `days`. Each day has a calendar
`date` or null and an `items` array. Each item has `item_id`, `label`,
`start_time`, `end_time`, and `fixed`. Unspecified times and lock states are null. A card
reflects the saved version associated with the message. A verified save
receipt can complete the display even when the final reply was lost.

Retained answers remain visible after the operational recovery window expires.
Reading a retained answer neither renews that window nor authorizes execution.

Both endpoints send `Cache-Control: no-store`. Existing Demo, MESSAGE, RUN,
and Trip contracts keep their existing version and validation.
