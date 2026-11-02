# FEEDBACK-LOCATOR@1

Additive server-only current diagnostic locator for #15. FEEDBACK@1.0 submission,
rc semantics and original receipts are unchanged. No new transcript/diagnostic store.

`GET /internal/v1/feedback-diagnostics?action_id=<original action>` requires current
canonical JWT admission and reads the own original feedback through its protected
operation. Referenced observations then use MESSAGE's original protected context
and the public RUN-FEEDBACK-LOCATOR@1 whitelist, with the same checker and a final
encoded-byte guard. Foreign/absent/expired/changed/unavailable records share 503;
missing/malformed bearer is 401, bad query 400. No owner/scope/diagnostic payload
can be supplied by the caller. Output is no-store, ≤65536 bytes.

Response fields: `request_id,version,action_id,input_sha256,submitted_at,
source_at_submit,current_locator,external_model_version,rule_version,unavailable,
references_are_execution_proof`. Version is `FEEDBACK@1.0`. `source_at_submit` is
the immutable old read-time observation; current locator does not overwrite it.
General feedback has both source/current locator null.

The current locator contains exactly: original `message_version`, current `status`,
`event_highwater,last_event_kind,draft_outcome,budget_exhausted_stage`, original
`registered_source_abi`, `operations`, nullable `first_recorded_at,last_recorded_at,
run_event_interval_seconds`, and a fixed observation label. Operations include only
`operation_key,registration_id,kind,attempt_id,operation_id,input_sha256`; the input
hash is of the exact original registered invocation bytes, never a copied prompt or
tool payload. These refs locate original model/tool/memory attempts and their
original result/usage query; they do not prove dispatch, settlement or success.

Missing legacy timing remains null. New events get actual database timestamps;
no migration-time backfill. Event interval is a measured first/last event span,
not provider latency or monetary cost. Regressed/partial timestamps yield unknown,
never fabricated zero. #27 clears diagnostic timing after 90 days through the
same dedicated role, while preserving answer events and accounting evidence.

Actual persisted message/registration protocol versions, original attempt/input
references and observed RUN/draft/budget stages are returned. External provider
model/rule versions and provider-internal failure stages are UNKNOWN unless recorded
by a future accepted producer; `unavailable` names them and no client text fills
the gap. Real model/version/tool-provider tracing → L2 #32. An empty registration
observation is not proof no call happened, particularly for legacy/out-of-period data.

Executable positive/negative evidence: `backend/cj_api/tests/feedback_runtime_pg.py`
uses actual signed local API, restricted PG, original run_once and FakeProvider;
asserts own original registration/timing, cross-owner refusal, and no copied private
message text. App evidence remains A's responsibility; real providers/devices/cloud
are not established by this local locator.
