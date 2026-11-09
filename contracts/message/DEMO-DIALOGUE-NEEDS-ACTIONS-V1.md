# Demo dialogue needs cards and actions

`DEMO-dialogue-message.2` uses the dialogue POST fields and original receipt
shape. It adds opt-in planning intent and spoken confirmation. The deployed
`DEMO-dialogue-message.1` still accepts ordinary question RUNs.

A metered dialogue RUN may publish an unconfirmed `needs_card`. The card event
has its original `card_id`, `version`, `status`, `dates` (null or an object
with nullable `start` and `end` local dates), `city`, `party_size`, `pace`, and
`fixed_items`. A fixed item has `item_id`, `label`, `starts_at`, `ends_at`, and
`time_zone`. Unstated fields remain null. The initial event retains the original
pending revision. An explicit action receipt carries the new revision.

`POST /v1/demo-dialogue/actions` accepts UTF-8 JSON with
`Content-Type: application/octet-stream`. The exact fields are `version`
(`DEMO-dialogue-action.1`), `action_id`, `conversation_id`, `card_id`,
`expected_version`, and `operation`. `correct_needs` additionally requires
`changes`, the same field patch grammar as canonical manual NEEDS. It changes
only the pending card. `confirm_needs` writes the canonical NEEDS revision
and enqueues an original planning MESSAGE in the same owner transaction.
A dialogue message of exactly “yes” or “可以” confirms only when that active
conversation has one completed, pending card.

POST and `GET /v1/demo-dialogue/actions?action_id=…` return
`{version:"DEMO-dialogue-action-receipt.1",request_id,receipt}`. The receipt
contains `action_id`, `conversation_id`, `card_id`, `version`, `operation`,
`input_sha256`, nullable `message_id` and `run_id`, and the projected `card`.
For confirmation, the message ID is the original to subscribe to. A changed
action digest conflicts. An unknown outcome is recovered by reading the
same original action or the original spoken confirmation message.

The planning RUN may project a `trip_candidate` only from C's protected
source-bound discovery after publication. It has `card_id`, `version`,
`status`, `proposal_id`, `trip_id`, `expected_trip_version`,
`candidate_hash`, and `days`. The dates, local times, places, source IDs and
fixed indicators are those of the validated candidate. Referenced unverified
source snapshots have no openable URL. Producing or reading the candidate
grants no authority to adopt it.
