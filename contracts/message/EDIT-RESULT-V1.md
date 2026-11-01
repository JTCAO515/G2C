# CJ-MESSAGE-EDIT-RESULT@1 — scoped clarification/expansion recovery

B owner #360, parent #25, Refs #336/#337. Additive publisher/runtime version;
old CJ-MESSAGE-EDIT-PUBLISHER@1, send.4, EDIT-V1, profiles and all old read formats
remain exact. This L0 slice does not deliver runtime or close #360.

Source interface: backend/message/cj_message/edit_result_protocol.py. New publisher
ABI CJ-MESSAGE-EDIT-PUBLISHER@2, explicit EditResultConfiguration ABI
CJ-MESSAGE-EDIT-RESULT@1, opt-in local profile message-edit-result.1. Existing C
memory ABI is retained; absence/unsupported currentness never means memory-off.
No module loader or environment/profile discovery. Old configuration/consumer
cannot enable or dispatch this profile. Version negotiation is compatibility,
not authorization; the actual factory-issued source/publication leases remain.

## Exactly two outcomes; no automatic new intent

1. clarification_required: C's original scope resolver is not READY. prepare returns
   PreparedClarification(state), with no model prompt. B makes **zero model calls**
   and creates no model operation/reserve/claim merely to report clarification.
   C state contains the original scope/explanation and full original NEEDS/Memory
   capture needed by hold_sources. It is data, never currentness permission.
2. expansion_required: prepare returned the existing PreparedEdit for READY scope;
   B ran its original registered model/Meter. Only C's validated preview status
   EXPANSION_REQUIRED may return ScopedResult(expansion_required,original_result_id).
   It is not a general rejection category. Parsing, invariant and fixed violations
   remain DraftRejected/validation_failed; provider and budget behavior unchanged.

No other new category exists. An in-scope valid candidate still returns its original
proposal ID and follows the existing trip_proposal/confirmation path. The result
path creates no Proposal, Signer or action and never changes a formal Trip version.
It grants no save/accept/modify permission. Required selection/reasons are display
data, not a new selected scope or confirmation. Expansion needs a **new user-chosen
send.4 message** against current Trip/version/hash and original explicit namespace/
NEEDS rules. Never resend automatically, reuse an old hash, or upgrade this message.

C owns explanation content, immutable result table, body read API and actual
publisher. It may reuse TRIP-scoped-explanation.1/resolve/preview/grammar/protect;
B neither recreates a scope/version engine nor stores a second body/diff source.
Result ID uses the formal ASCII identifier grammar (1–128). ScopedResult is only
an original stored descriptor; B never accepts one from request/model JSON as a
permission. Only actual configured C code returns it inside the live transaction.

## Frozen publisher2 flow

- prepare(binding,source) returns exactly PreparedEdit or PreparedClarification.
  Only prepare may select pre-model clarification. A non-READY resolver cannot be
  disguised as a model validation failure in this profile. C captures original
  current NEEDS and Memory for the same source before returning either variant.
- hold_sources(publication,prepared) supports both variants and returns the same
  actual source checks/leases as publisher1. No fake READY/DTO/hash check replaces
  them. C344 captures via short source_lock=False and reuses the actual publication
  lease, preserving its original typed eligibility/withdrawal/version fences.
- publish_clarification_in_transaction(publication,prepared) stores the exact C
  explanation under original run/message/input bytes and returns ScopedResult
  with kind clarification_required. It cannot invoke a model or return a Proposal.
- publish_in_transaction(publication,prepared,reply) retains publisher1's valid
  Proposal return. For a validated expansion it instead stores C's original reply,
  diff/required selection/bilingual reasons and returns ScopedResult with kind
  expansion_required. C must not store a result for malformed/fixed/invariant errors.

## Common transaction and final guard

B uses the original publication transaction/cursor: RUN owner/fence → MESSAGE SHARE
→ independent TRAVEL SHARE → C Memory fence → C NEEDS revision fence → Trip UPDATE.
No separate B Trip SHARE remains while C awaits its unique Trip write lock.
For **both** outcomes C takes publication.lock_trip(), rechecks its captured sources,
then calls publication.before_write() as the last source/admission/deadline guard
before INSERT into **C's result table on publication.cursor**. No second transaction
or commit. before_write and original deadline semantics are unchanged.

B records a new result_committed event, with an effect distinct from trip_proposal,
then completes the RUN on that same cursor/transaction. The effect value is
`scoped_result:<kind>:<result_id>`; the event value has that same encoding. Only the
two exact kinds above and bounded original IDs are accepted. Outcome is computed
from that original event, not from client data or failed text. No duplicate result,
result+Proposal combination, altered original source or terminal reuse is allowed.

C's row, RUN result and completed state commit atomically. Rollback removes all
three; failed source/Memory/NEEDS/Trip/selection/account fence, deadline, cancel
ordered first or UNKNOWN leaves **no new result**. The phase=accept path still
requires an actual original trip_proposal effect; a scoped_result cannot qualify.
A result does not become acceptable after recovery or a later namespace/Trip change.

Physical commit ACK UNKNOWN may mean the common commit happened. Reconcile only
original message/run IDs and original bytes: do not mint a result/operation ID or
re-run the model. A committed original completed outcome can be recovered from a
new connection; a rolled-back attempt cannot leave an orphan result/effect. Late
cancel observes the original committed result, not an imaginary rollback/refund.

Source leases outlive the common commit, and no source SQL follows the original
final deadline. No result body is inserted before before_write. C's body reader
uses canonical fresh owner admission and original current source/Memory/NEEDS
checks before complete encoding/return, withholds on stale/withdrawn/UNKNOWN, and
never treats the display descriptor as a lease. C owns that API/retention contract.
B read pointers are historical reconciliation, not permission or a copy of C data.

## Additive B recovery versions and old-reader behavior

New GET /v6/run-draft-status → RUN-draft-status.6; /v5/run-display → RUN-display.5;
/v4/message-history → MESSAGE-history.4; /v5/message-send-status →
MESSAGE-send-status.5. They retain the original fields/receipt/reference/UTF8 bytes
and add `scoped_result` (null or RUN-scoped-result.1 below). Only RUN-draft-status.6 adds the two exact categories to draft_outcome; its original
budget/provider/validation outcomes retain their exact meaning. scoped_result is
a top-level field in status/display, and an item field in history. The complete
response schemas and both-category examples are in edit-result-schema.1.json and
edit-result-examples.1.json; existing receipt/reference/snapshot definitions are
referenced unchanged from edit-schema.1.json.

RUN-scoped-result.1 is exactly version,kind,result_id,message_id,run_id,input_sha256.
It binds the original RUN/message/input and C's result ID; no body/hash/permission
or caller owner is added. C can query its stored body under original guarded API.
History/receive/status never rewrites the original send.4 or input hash. Completed
results are queried/reopened as the same original operation after ACK uncertainty.

Old draft-status/display versions that cannot represent this new RUN outcome
explicitly refuse it instead of leaking a new enum or claiming not_recorded.
Old message receipt/history-only versions keep their exact original raw/reference
semantics and expose no new outcome field; unsupported binary compatibility gates
refuse the new profile. Old PUBLISHER@1 never produces either new event/outcome,
and existing accepted results/failure/cancellation/UNKNOWN behavior is unchanged.

New profile/compatibility gate and RUN SQL constraints, if needed, are B's next
append-only local migration (latest manifest0028 at design). C owns its result
schema migration **after** B's reserved manifest slot; numbers are assigned only
against current manifest/locks. No applied0001–0028 bytes, frozen version or test/CI
weakening. Runtime/actual C table/body API/production integration/App/real resources
remain UNRUN in this L0 PR; B continues with L1 after freeze and notifies C #336
immediately after merge, without waiting for acknowledgement/main CI.

The zero-model clarification path may register the original local Meter RUN clock
without reserving/claiming a model operation. It still enforces the original total
RUN deadline before_write; missing/UNKNOWN clock never permits a result.
