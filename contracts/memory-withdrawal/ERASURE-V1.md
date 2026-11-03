# MEMORY-ERASURE@1 / MEMORY-ERASURE-ASSOCIATION@1

C-owned, local runtime only. Added versions; old withdrawal observation,
MEMORY, CLEANUP@1.0/1.1, candidate Action1 and Pub1/2/3 remain unchanged.
This is item deletion, never account deletion or a history-organization grant.

## Explicit user command and result

`POST /v1/memory-erasures`, signed original UTF8 `application/octet-stream`,
at most 32768 bytes. Exact keys:

```json
{"version":"MEMORY-ERASURE@1","action_id":"original-action","item_id":"original-item","expected_version":3,"derived_range":"owned_trip_derived_scope"}
```

IDs preserve exact Unicode spelling, at most 4096 characters, nonblank/no NUL;
version is a positive int64, never bool. No owner/source/authority fields.
The range acknowledgment is mandatory: M30 has no item FK. The request stops
the selected item and all its sources atomically, increments item/scope versions,
and freezes the complete association before any cleanup dispatch. The cleanup
operation ID is `memory-erasure-v1:` plus SHA256(scope UTF8 + NUL + exact command).
Reusing action_id with different bytes conflicts, including whitespace changes.

`MEMORY-ERASURE-response@1` returns action/operation IDs, stopped item version /
scope epoch, `stop_use: stopped`, real `online_status` and original step states.
Stop-use is distinct from physical completion. Already sent model requests,
displayed history and external provider retention cannot be withdrawn here.
`GET /v1/memory-erasure-progress?action_id=<exact original>` is read only;
absence stays unavailable/UNKNOWN. Repeated exact POST reconciles an already
dispatched unknown step; it never redispatches it or invents a new operation.
Response encoding stays inside the original current identity context.

Deletion preserves original chat and accepted formal Trips. It clears the
account's Trip derived result scope and nonaccepted proposals/drafts, expressly
**not** a precise item match. A must explain this range before sending the
mandatory acknowledgement. New explicit saving uses new item/source/operation
IDs. No age-based automatic erasure is added.

## B consumption: original immutable association only

Module `cj_memory_withdrawal.association_reader`, constructor
`AssociationReader(store, memory_scope)`, method `read_original(request) -> bytes`.
`store` is the original principal-bound public `cj_cleanup.store.Store`;
`memory_scope` comes from that same trusted principal. No client scope is accepted.

The reader accepts only exact CLEANUP@1.1 memory-purpose HookRequests for
`business/message`, `checkpoints/run`, `business/usage`, `memory-derived`,
`business/memory-management-actions`, `business/trip-authoritative`, or
`business/memory-authoritative`. It calls the public **read-only**
`require_intent(cursor, request)` in the original operation transaction.
Exact request bytes, subject, original in-progress step, approved selection,
scope, protocol, registry and original operation must agree. Trip uses
`trip_scope_for(memory_scope)`; all other targets use memory_scope.
The reader creates no intent, does not dispatch, and cannot authorize account
cleanup. Before original intent, after missing/corrupt manifest, wrong owner,
selection, target, scope or version: `cj_cleanup.core.Denied`, no reconstruction.

Return bytes are canonical ASCII JSON <=1,000,000 bytes with exactly:

| Field | Meaning |
| --- | --- |
| version | `MEMORY-ERASURE-ASSOCIATION@1` |
| operation_id / subject_digest / memory_scope_digest | Original cleanup operation, original principal digest, SHA256 of exact Memory scope |
| selection | CLEANUP@1.1 memory selection: kind/item_id/stopped item_version/stopped scope_epoch |
| original_selection | item_id/item_version/scope_epoch immediately before stop; both versions advance by exactly one |
| source_refs | Complete selected-item source chain: source_id/source_version, <=1000 |
| operation_refs | Canonical source/action originals: operation_id/input_sha256, <=1000 |
| message_refs | Exact original conversation_id/generation/sequence/message_id/input_sha256; <=10000 |
| job_refs | Every matching C job: job_id/attempt_id/original_input_sha256/state; <=1000 |
| decision_source_sha256s | Exact canonical accepted-decision digests; <=1000 |
| derived_range | `{kind: owned_trip_derived_scope, precise_item_match: false, preserve_formal_trips: true}` |

`association_codec.parse_original(raw, request, memory_scope)` is a public byte
validator, **not** authority. B obtains bytes from the reader, then can use this
parser. Digest values are lowercase SHA256 hex; versions/sequences are positive
int64. Message input_sha256 and job original_input_sha256 must be compared with
the actual original B-owned payload associations before removing copied content.
Do not match by text/subject/slot or infer permission from manual sources.

Jobs include pending/inflight/unknown/completed/failed/cancelled and exact
accepted-decision digest matches across different message anchors and endings.
`state: erased` is allowed only when an earlier overlapping deletion removed a
shared payload and a permanent exact job+attempt+input hash proves its erasure.
Missing jobs without that proof fail closed. The manifest is immutable; C
authority removes it only after all original content-domain steps confirm.
Only minimal irreversible hashes/progress remain, not source text/private IDs.

B's memory-purpose hooks remove copied/derived payloads in B's domains, stop
affected work, and preserve original chat and valid accounting evidence. They
must use this original association and original receipt/reconciliation protocol,
not account hooks, guessed current joins, whole-conversation deletion, or a new
fee attempt. Unknown ACK/cost stays UNKNOWN with zero automatic resend.

## Runtime original-history fence

`MEMORY-HISTORY-ERASURE-FENCE@1` is the explicit new consumer method on the
existing C `RuntimeMemory` (including TypedRuntimeMemory):

```python
run = runtime_memory.capture_history(
    original_binding, all_original_message_refs,
    decision_source_sha256s=all_original_accepted_decision_digests,
)
with run.hold(original_binding) as check:
    check()  # immediately before model admission / final output commit
    # keep the original lease held until that operation commits
```

The trusted host supplies **all** genuine context coordinates; the wire/model
cannot provide or expand authority. capture_history returns a runtime object
with `erasure_protocol == MEMORY-HISTORY-ERASURE-FENCE@1`, not a new source grant.
It retains existing canonical identity, MESSAGE reference, Memory snapshot and
current-state checks, adds current M44 original evidence checks in the **same**
Memory transaction/lock, and copies only immutable digest sets. Do not nest a
second Memory transaction inside an existing held Memory lease. Capture and
each new model dispatch/publication require fresh checks; stale/erased evidence
raises RuntimeDenied. An already in-flight request cannot publish after stop.
Old capture() semantics are unchanged; using old capture is not Fence@1 proof.

## C storage/hooks and candidate compatibility

M44 appends the private manifest and minimum noncontent fences. Same PR installs
account removal of the manifest and explicit `item_cleanup.erasure_hooks(store,
memory_scope)` for account/item purposes. Old account_hooks remains account-only.
No runtime DELETE/TRUNCATE, new role, BYPASSRLS or SECURITY DEFINER.

Deleting a shared history job must not erase unrelated canonical candidates.
`GET /v6/memory-candidates?conversation_id=<id>&after_candidate_id=<id-or-empty>`
returns `MEMORY-CANDIDATE-projection@2`, at most 50 current canonical candidates,
their current Memory epoch and original review job_id/attempt_id. Use the last
candidate_id as the next cursor; empty candidates ends scanning. Existing
`MEMORY-CANDIDATE@1` confirm/reject uses canonical origins without needing an
erased job payload. V3/V4 historical discovery remains unchanged.

The explicit deletion app factory requires a complete B memory-purpose hook
factory; missing composition is unavailable. C component tests reporting B
UNKNOWN do not prove B physical deletion or whole #26 completion. Production,
external retention, devices and real model extraction quality remain separate.
