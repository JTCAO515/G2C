# ORIGINAL-USAGE-WIRE@0.1.0-rc.1

Fixed RUN0685dbf8ad9622ad56c4435cb2fc47c3096046d1, original MESSAGEbf79/AUTHf3.
Existing root575/9d and all prior operations/schemas preserved. GET
/v1/message-usage-association?message_id=… / getOriginalUsageAssociation returns
{request_id,association}, seven exact refs: conversation_id, generation, message_id,
message_sequence, run_id, attempt_id, operation_id. No nullable/fake association.

Only original message ID enters request, with explicit host UTF8 bound. Host Message
boundary/checker and trusted approved-environment RUN resolver are reused. No caller
scope/run/attempt/unit/period/owner/permission, login attempt selection or ID minting.
Public OriginalUsageAssociationReader derives complete Binding from original protected
MESSAGE receipt and reads canonical RUN stored UsageBinding. Request cannot configure
repository or replace its source. Missing/corrupt/legacy null association fails.

All generated validation, original message equality and BASE request_id envelope
encoding occur INSIDE public read_projected. Final response cap includes envelope;
source performs second strict canonical recovery/full association comparison/source
recheck, original MESSAGE final AUTH retirement, then callback-free captured binding
comparison. HTTP only sends exact returned bytes, no outside decode/re-wrap/new guard.
No raw input/command bytes/outbound bytes/input digest/reserve/output limits/period/
unit/status/text/effects/usage object escapes. No USAGE/Meter query or write occurs.

Association means only stored original references. It is not evidence of a USAGE
ledger row/reservation/dispatch/execution/fees/current status or permission. It can
remain readable for persisted RUN unknown state, never authorizes retry/start. Actual
audited producer remains SyntheticFirstStep.create_fixture only; no production worker
linked. Real accounts lacking association remain explicitly unavailable; nothing is
backfilled or synthesized to appear supported. Shared dispatch fence remains disabled.

One canonical RUN package: new postgres strict require_clean_close defaults False,
so existing recover/transaction/diagnostic/display consumers keep their semantics.
Feedback/run-display root consumer pins now same068 package; existing other runtime
blobs unchanged, display module byte-identical. New association uses strict clean close.
Cursor/connection-close failure withholds result; source publication pure field check
follows the last AUTH callback without new checker/resolver/SQL/project/context access.
Dependency before/after hashes and actual old public behavior checks are separate.
No domain implementation edits or second package/authority introduced by root.

OriginalUsageWireConfiguration requires explicit positive message-ID/final-response
byte caps. No production values chosen, no truncation. Limits do not bound the
canonical adapter's full log/outbound-input reconstruction work. Missing config fails
closed. Standalone source uses original strict verifier/checker and read-only Message
Boundary with no run-ID writer; same-app uses exact existing MessageBoundary/checker.
Default absent resolver/association is unavailable, never successful empty refs.

BASE: missing bearer401; malformed/extra selector400; ID/association byte cap413;
unknown/changed/guard/I/O/strict-close/read-cancel/commit uncertainty503 retry_safe_read.
Reader-origin non-Exception interruption sanitized inside sync invocation; outer HTTP
cancellation still propagates. No automatic retry, write, reserve/claim/settle/cancel,
provider, new ledger/table/permission. Trace/header/no-store and generic safe errors
unchanged; no private values/exception strings logged.

Source scoped actual public-context tests are separate from DB/HTTP/account evidence.
Original producer12 and old compatibility evidence are not reused as our independent
approval. This source firstfixed precedes assessment of a fresh private PG combination;
no old instance restart or automatic new cluster. App/real association producer/USAGE
status/fees/dispatch/full I and independent source/root gates remain unverified.
