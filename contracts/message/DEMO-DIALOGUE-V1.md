# DEMO-dialogue-message.1

The Hong Kong beta enables this additional route for existing internal assembly
subjects. The bearer, retirement, invitation floor, and daily demo cap are the
same as for existing protected MESSAGE operations.

Send `POST /v1/demo-dialogue/messages` with bounded UTF-8 JSON bytes and
`Content-Type: application/octet-stream`. The client supplies `version`,
`message_id`, `text`, and `locale` (`zh` or `en`). Omit both optional fields for
the default conversation. Use `new_conversation: true` for a new conversation, or
supply the `conversation_id` returned from an earlier dialogue message to resume
it. These two fields are mutually exclusive. No owner, travel, planning,
confirmation, or memory selection is accepted from this request.

POST and `GET /v1/demo-dialogue/messages?message_id=…` return
`{version:"DEMO-dialogue-receipt.1",request_id,receipt}`. The receipt contains
`message_id`, `conversation_id`, `run_id`, and `input_sha256`. The digest covers
the exact dialogue request bytes. The existing worker receives the original
internally generated `MESSAGE-send.2` input and retains its own digest. The
first successful message, default Travel creation, and outbox enqueue commit
together under the MESSAGE owner lock. All that owner's dialogue conversations
share the same default Travel identity.

Identical request bytes for an original message ID recover that receipt.
Different bytes or collision with an existing legacy message ID return
`INPUT_CONFLICT`. GET returns a null receipt for an absent or foreign original
and never dispatches or provisions. On `MESSAGE_OUTCOME_UNKNOWN` or
`MESSAGE_UNAVAILABLE` with `reconcile_original`, query the same message ID.
An unavailable or retired travel or conversation is never reactivated here.

This slice creates an ordinary, metered, non-planning RUN. The typed dialogue
event and explicit card actions are separate slices in #702. Existing versions,
including their explicit context/NEEDS validation, remain unchanged.
