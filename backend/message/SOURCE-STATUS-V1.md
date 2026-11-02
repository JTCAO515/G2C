# MESSAGE-SOURCE-STATUS@1

Additive trusted-owner metadata seam:
`HistoryReadContext.source_status_v1(conversation_id) -> SourceStatus`.
The type and VERSION live in `cj_message.source_status_v1`. SOURCE1/2 and their
frozen fields remain unchanged; no HTTP route, table, grant or end writer is added.

The caller enters the existing canonical `Boundary.with_history_context`. Its
current verified principal and pre-scoped runtime repository own the conversation.
The read holds the same MESSAGE scope and active-chat locks as send/finish. It
returns one immutable materialized value from that transaction:

- `cursor`: existing Cursor with server scope, conversation_id, current generation,
  epoch, `through=current last_sequence`, `after=0`. An empty open chat has0/0.
- `conversation_type`: travel. Service is reserved and remains unavailable.
- `end`: None **only** when all persisted end fields are absent on the owned,
  active, readable chat. Otherwise the existing genuine end verifier requires its
  exact scope/head-bound end_id, generation, epoch and through and returns the
  existing ConversationEnd. The full-head counter is not a source interval.

Missing/foreign/inactive chats, invalid persisted end, stale identity/account
admission or database uncertainty fail. No exception or Unavailable is converted
to open. The method never calls finish or writes an end; old finish/replay and
late-send rules still apply. Scope/chat SELECT locks are released on method return;
the returned metadata is neither a lease nor collection/dispatch permission.

The C consumer may use the metadata to choose its original queue request. It must
still obtain fresh C consent and genuine source/Travel authority at every actual
processing stage, preserve original job/attempt bytes and use the original Meter.
Metadata may go stale immediately; it never authorizes a retry or a synthetic end.
No message text, receipt bytes, consent version or C private state is read here.

```python
def materialize(context):
    status = context.source_status_v1(conversation_id)
    # C selects its bounded segments and original request from this data only.
    return encode_status(status)  # local materialized bytes, no network wait

raw = boundary.with_history_context(token, materialize)
```

The context method checks callback lifetime/thread; canonical admission is checked
around the actual repository transaction and before the outer materialized return.
Use the current account-aware canonical checker for account retirement as with
SOURCE2. There is no alternate identity, caller owner or permissive fallback.

`message_source_pg.py` uses real signed API/runtime PG to check empty/open, genuine
end/replay/current epoch, no end/message writes, foreign/missing/inactive/corrupt
refusals, actual NOWAIT probes for both locks, expired context and final fresh
admission loss. Existing SOURCE1 and actual joint SOURCE2 tests remain in the suite.
