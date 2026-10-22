# FEEDBACK-WIRE@0.1.0-rc.1

Sequential increment after NEEDS a624cca. Sole formal OpenAPI/official Python+Swift
generation; every a624 existing path/schema remains unchanged. Producer cf48196,
MESSAGE bf79, RUN eadda, AUTHf3 are separately pinned. This is local candidate wire,
not FEEDBACK@1.0 freeze or complete Issue15/App diagnosis acceptance.

POST /v1/feedback (submitFeedback) carries original UTF8 JSON FeedbackAction as
octet-stream; GET /v1/feedback-action-receipts?action_id=… (queryFeedbackAction)
returns original receipt or required explicit null. Exact keys: action_id, problem,
expectation, references. Preserve raw bytes before first send. Same-ID different
bytes conflicts, including whitespace/escaping. No reconstruction/replacement ID
on unknown. Text is voluntary, not diagnostic authority; no owner/model/version/
usage/tool/failure-stage fields allowed. Do not prefill private transcripts or
credentials; no automatic classification/redaction of voluntarily pasted text is
claimed. References are empty for general feedback, otherwise one message and
optional matching run; unsupported domains/run-only/duplicates fail.

Receipt is only submitted: original input_sha256 from actual persisted-row decoder,
database UTC submitted_at, fixed bilingual submitted text, and required nullable
source. It never claims fixed, trained, dispatched to an operator or sent externally.
No request-side hash substitutes for historical lookup. Query/replay retains original
source observation even when current source later changes; it does not reread source
or claim current access. Null lookup is not noncommit proof or new-ID authority.

Source exposes only message/conversation/generation/sequence/run identifiers,
message_input_sha256, run_status_at_read and event_highwater_at_read. The message
hash is of original input, not nonexistent original receipt bytes. No transcript,
Run text/effects/tool payload, model/rule version, usage, duration or failure stage
is supplied or inferred. Those unavailable fields are omitted, never zero/default.

## One checker and public source boundaries

Root MESSAGE pin moved e4→bf79. Only auth_boundary runtime changes: added public
query_message and tightened synchronous history lifetime/thread/nested-context
checks. Domain/storage/__init__ bytes identical. Existing signatures and other
methods preserved; root compatibility evidence is five targeted old message/history/
draft cases, not a blanket claim about arbitrary legacy internal consumers.
No MESSAGE/RUN source edits or two cj_message versions are installed in one process.
Publish must consume the separately accepted original source subtrees matching pins.

Standalone build_feedback_boundary creates one strict existing AdmissionChecker;
optional read-only MessageBoundary and FEEDBACK share that exact object. Same-app
create_composed_app reuses the existing MessageBoundary/checker rather than creating
another. Explicit server feedback resolver and optional MESSAGE/RUN resolvers are
required; missing/partial source configuration fails closed. Sources is the pinned
concrete class, never an allow callback. No new_run_id is supplied to a read-only
source boundary. Missing Sources permits general feedback but rejects new referenced
submissions; old exact replay/query remains its historical receipt semantics.

Only public FEEDBACK with_operation/submit/query_action is called by routes. Inside
that lifetime: generated validation, minimal receipt projection, size bound and JSON
bytes. Producer Sources uses MESSAGE.with_history_context/query_message and RUN's
read_diagnostic whitelist with full receipt-derived binding, checks original actor/
scope, rereads message, re-verifies before commit and after projection. Only bytes
successfully returned leave the scope; no private methods or outer authority wrapper.

These are separate read/write transactions. The saved observation is authoritative
at its reads, not an atomic cross-domain fence or guaranteed status at commit,
delivery or user-decision time. Source changes observed during rechecks reject or
withhold; a change after the last observation remains possible. Historical query
preserves that old observation and never advertises it as current availability.

## Errors, privacy and lifecycle

Missing bearer401; grammar/UTF8/extra fields400; request body bound413/media415;
original-input Conflict409. Unknown/unavailable source/auth/DB and sanitized private
projection failure503, write reconcile_original/read retry_safe_read. A postcommit
cap/codec/cancellation/ACK/authority failure never becomes a failed-uncommitted claim
or successful receipt. No auto retry; original account/action/bytes must be retained.
No query/token/body/IDs/exception text logging; BASE request-ID/no-store unchanged.
Swift uses existing Configuration.memory for whole/fractional UTC timestamp decoding;
nonnull oneOf fallback must be rejected, not classified as null.

Registry1.5 registers sole cj_feedback_action private store: original text once,
minimal historical source_reference, hash/time/IDs. No secondary queue/diagnostic
ledger/source payload copy. Retention/cleanup/restore/in-flight retirement fences
remain unconfigured. Candidate SQL is new-empty-only, not migration apply or RLS/
production grant. Actual App entry points, live accounts/model/tool diagnosis,
Issue15 I, deletion/restore and deployment remain unverified.

Checks: scripts/check-feedback-wire.sh AUTH_REPO FIXED_SOURCE_REPO;
scripts/check-generated-feedback.sh; scripts/build-feedback-loopback-client.sh;
scripts/generate.sh --check. Positive scoped wire cases are explicit public-seam
fixtures; actual AUTH entry refusal and same-checker assembly are separately checked.
New private PG/numeric HTTP/Swift combination evidence is separate from these.

Author combination201156 passed8 groups on fresh private PostgreSQL/numeric HTTP,
including concrete public MESSAGE/RUN source reads and official Swift general/
linked submit/query. The missing-Sources control is real DB+in-process ASGI, labeled
separately. All local services stopped; see tests/evidence/feedback-wire/REPORT.md.
This does not strengthen read-time observations into atomic cross-domain validity.
