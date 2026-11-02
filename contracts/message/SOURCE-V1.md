# MESSAGE-SOURCE@1

Frozen additive contract for #403 / #23. Existing MESSAGE/history/send versions
are unchanged. Internal server composition; no App SDK or service-conversation
business path is introduced. This seam grants collection only through an explicitly
installed trusted consent policy. Default/missing policy denies. JT policy: history
organization is off by default, enabled per conversation; C owns that durable record.

## Trusted collection seam

```python
boundary.with_history_context(token, lambda ctx:
    ctx.with_enabled_source(query, canonical_source_policy, project))
```

`SourceQuery(conversation_id,generation,epoch,after,through,source_version,
withdrawal_epoch,mode='incremental')` is a comparison value. There is no request
owner/scope/authorization bool, manual source, transcript-derived consent or
caller-selectable policy. Continuous accepted MESSAGE sequences are `(after,through]`,
1..100 rows. Integers are bounded signed int64; MESSAGE epoch may be **0** (existing
canonical initial epoch), source version/withdrawal epoch start at 1. Generation
and conversation ID retain original spelling. Final response is materialized bytes,
at most 524288, encoded inside the protected callback.

`SourcePolicy.hold(principal, scope, query)` is a trusted C implementation, explicitly
injected by the host. It opens the canonical per-conversation consent/withdrawal
lock and returns `SourcePermit(cursor, source_version, withdrawal_epoch)` only after
verifying current explicit enablement, the authorized exact continuous interval,
original principal/scope, generation/epoch and current versions. It retains the lock
through callback/encoding and rechecks before exit. The permit is data, not a
capability; creating a dataclass, replaying source bytes or refreshing a token
cannot install a policy or expand a grant.

Enable, disable and re-enable must each advance `source_version`; withdrawal changes
`withdrawal_epoch`. No version reuse after disable/re-enable. A stale queued job is
denied even if its old source happens to contain the same text. Reconciliation of
an old job's status is a separate C original-operation read, not permission to
re-extract or dispatch. C supplies durable policy and its tests; #403 supplies the
MESSAGE protected read and tests it with an explicitly synthetic PG consent policy.

Lock order: canonical MESSAGE scope lock → C consent/withdrawal/MEMORY lock. The
callback may read, extract locally or persist a candidate while both locks remain
held. It must not first hold MEMORY and then enter MESSAGE. No raw transaction,
cursor, repository or authority escapes. For extraction, candidate insertion and
publication, enter this seam anew with the original current query and C policy;
serialized old snapshots do not grant a later phase. A model call is not performed
by this interface and does not hold a database lock for its duration. Before any
later publish/write, reacquire and verify current source and withdrawal fences.

Returned `SourceSnapshot` has canonical scope (server callback only), canonical
`Cursor`, current source/withdrawal versions, tuple of canonical `HistoryMessage`
(original immutable UTF8 and Receipt) and optional `ConversationEnd`. MESSAGE
validates raw-input hash, original message/conversation IDs, generation, exact row
count and sequence continuity. SOURCE policy and canonical AUTH are checked in
the original lifetime; after callback expiry no ordinary private access is gained.
Foreign/missing/stale/revoked/service sources all fail as unavailable.

## Explicit conversation end

`Boundary.finish_conversation(token, EndQuery(conversation_id,generation,epoch,
through), project)` records the user's explicit end at the exact current head.
No inactivity inference, Trip acceptance, model signal or service session exists.
Stable `end_id = sha256(JSON([canonical scope,conversation_id,generation,epoch,
through]))` with ASCII escaping and compact separators. Same exact head replays
the same end signal; different/stale/foreign head fails. Encoding and a final
fresh AUTH check occur before publishing the result. Unknown COMMIT/return must
reconcile that original head; do not mint a replacement conversation/action.

The end is immutable and closes new message insertion in that generation. Existing
message/receipt/history reads and original send replay remain possible. A user starts
a new conversation for new messages. DB trigger rejects late INSERTs after end;
both paths serialize the canonical scope lock. A changed generation/epoch cannot
reuse the old signal. `mode='conversation_end'` source reads require the exact stored
signal/current head; incremental reads never fabricate an end.

## Reserved conversation type

`CONVERSATION_TYPES = ('travel','service')` and PG enum reserve both names.
This version only writes `travel`. API service requests and direct runtime-role
service writes are rejected. Service content, staff signatures, active push messages,
JT outbox and new service storage are not implemented (ADR-0009 sections 3/4/6/7).
No service session enters planning or memory extraction.

## Signed local API adapter

Trusted host calls `register_message_source_routes(app, canonical_boundary, policy)`
on the existing local app. Paths are internal host routes, outside the frozen App
OpenAPI/SDK; no iOS generated file is changed. C can use the Python seam directly.
Authorization is the same strict signed JWT and fresh canonical admission checks.
Bodies are exact UTF8 JSON, `application/octet-stream`, ≤16384 bytes; duplicate,
extra and caller owner fields fail. No query parameters.

- `POST /internal/v1/message-source/read`: exactly `version` plus SourceQuery
  fields (including mode). Response is `request_id,version,conversation_type,cursor`
  (no scope), `source_version,withdrawal_epoch,messages,end`. Each message has
  canonical `receipt` and `original_utf8_base64`. This is accepted user input,
  not proof the model/tool completed or a final assistant answer.
- `POST /internal/v1/conversation-end`: exactly `version,conversation_id,generation,
  epoch,through,conversation_type`; response `request_id,version,end`.
- Invalid shape/service write: 400. Missing bearer: 401. Missing/foreign/stale/
  denied source: identical 503 `MESSAGE_SOURCE_UNAVAILABLE`, no private payload.
  End uncertainty is `outcome=unknown,recovery=reconcile_original`; it is not a
  rollback or permission to send anew. All output uses no-store and trace middleware.

Positive: an enabled version 3 / withdrawal epoch 2, exact current generation/epoch,
continuous messages 1..3 returns all three under the two locks. End at that head
replays the same stable ID without depending on a Trip.

Negative: owner B asks for owner A's chat; version 2 after disable/re-enable; old
withdrawal epoch; generation/epoch changed; gap in sequence; through beyond allowed
or committed head; service type; callback loses admission; no policy; duplicate or
caller owner field. All reject without publishing source bytes.

Persistence is appended columns on the already-registered `business/message`
chat table; its account cleanup hook must cover end metadata together with chat.
No new unregistered private store, role or DELETE permission. Migration 0031 is
local only; empty up/down/up and retained-end down refusal are required.
