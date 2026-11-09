# DEMO-dialogue-event.1

`GET /v1/demo-dialogue/events?message_id=…` returns SSE for an original
[dialogue message](DEMO-DIALOGUE-V1.md). The bearer must still be admitted for
that owner and the source must still be readable. The stream has no execution
authority. It accepts only a dialogue message ID.

Each SSE data field is JSON with `version`, `event_id`, `conversation_id`,
`message_id`, `run_id`, `kind`, and `payload`. The SSE event name is `kind`.
The first `status` reflects the accepted original outbox. Further status and
answer deltas are projected from committed RUN events. Status `running`
corresponds to the original RUN's started event.

```json
{"version":"DEMO-dialogue-event.1","event_id":1,"conversation_id":"conversation","message_id":"message","run_id":"run","kind":"status","payload":{"status":"queued","stage":"queued"}}
```

`answer_delta` carries `{"text":"…" }` in original order. A terminal `status`
may carry `error_code` derived from the original result
(`BUDGET_EXHAUSTED`, `RUN_FAILED`, `RUN_OUTCOME_UNKNOWN`, or
`RUN_CONTEXT_INVALID`). A disconnected stream can resume with the last received
SSE ID for the same message in `Last-Event-ID`. An unknown nonzero cursor returns
`RESYNC_REQUIRED`. IDs are increasing and may have gaps. The older byte-offset
SSE endpoints retain their behavior.

Source and card projections are tracked in #702 and require protected original
evidence. A disconnected or unavailable stream is never a terminal success.
