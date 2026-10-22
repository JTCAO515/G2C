# RUN-DISPLAY-WIRE@0.1.0-rc.1

Fixed producer414e5c19d8470ac2fbdc645ddfaedeee8dd6039f (c12 display plus projected
read increment), MESSAGEbf79/AUTHf3. Existing RUN core/postgres/usage/diagnostics/init
bytes match prior eadda; one package superset, no second RUN/MESSAGE or AUTH provider.
All accepted201156 operations/schemas preserved; no domain or UI edits.

GET /v1/run-display?message_id=… / getRunDisplaySnapshot returns required
`{request_id,snapshot}`. Snapshot contains exactly conversation_id, generation,
message_id, run_id, message_sequence, status, event_highwater, text, text_state.
Original MESSAGE receipt derives full internal Binding; no caller run ID/scope/
principal/permission is accepted. Original opaque ID and display text retain exact
Unicode spelling. Request-ID is server trace, same X-Request-ID, no-store.

Complete only means persisted status completed; other statuses are partial,
including failed/cancelled/context_invalid/unknown. Queued may have actual empty
text. Missing/expired/inactive/foreign/corrupt/changed/unknown reads return errors,
never fabricated empty/queued/null snapshots. Event highwater is not message
sequence, model version or provider proof. This read is not SSE, a cursor, listener,
RUN creation, dispatch, cancellation or restart. No raw user message/receipt, scope,
principal, events/effects, USAGE/outbound bytes/digest, model or failure stage escapes.

The initial c12 read returned only nine-field bytes, conflicting with BASE envelope.
That conflict was sent to Main; original RUN owner added public read_projected.
Root exclusively calls read_projected(token,message_id,project): pure generated-model
validation and final envelope JSON encoding happen INSIDE project. The owner checks
strict materialized bytes and full envelope max_response_bytes, then second recovery/
state+epoch/source and final MESSAGE identity. Outside, HTTP Response sends those
exact bytes, with no decode/rewrap/deferred projection or homemade guard.

Explicit RunDisplayWireConfiguration requires positive non-bool max_message_id_bytes,
max_text_bytes and max_response_bytes; no production values chosen. The first is the
HTTP opaque-ID UTF8 bound; latter two construct the exact producer configuration.
No silent truncation. Response/text bounds do not bound the adapter's full-log DB
reconstruction/query memory. Local fixture values are not approved production policy.

Standalone factory uses strict existing JWT verifier/unique CJAccessProvider and
explicit trusted MESSAGE/RUN resolvers. Its MessageBoundary is read-only (no run-ID
factory). Same-app composition reuses the existing MessageBoundary/checker. Resolver
maps approved environment/profile and trusted issuer/subject/audience, never caller
owner or token timestamps. Default missing config fails closed, no DB/credential
fallback. Public reader is the only business/read boundary; no private method access.

BASE mapping: missing bearer401, malformed/extra query400, opaque ID or snapshot/
envelope cap413, other source/guard/I/O/changed/unknown failures503 retry_safe_read.
No retry is performed. Non-Exception interruption originating inside synchronous
reader is sanitized to unavailable at the worker invocation; outer HTTP task
cancellation still propagates. No private data or exception text is logged. Failures
cannot be treated as completed text or inferred source absence.

Read-time status is not guaranteed latest at delivery. Sequential MESSAGE/RUN guards
are not atomic cross-database revocation. Real accounts/provider/worker, original
claim/cancel/cursor/dispatch constraints and complete Issue11/App I remain separate.
No new persistence, queue, cleanup authority, schema apply, RLS or resource default.
Existing RUN private stores remain canonical; registry only notes this readonly view.

Checks: scripts/check-run-display-wire.sh AUTH_REPO SOURCE_REPO;
scripts/check-generated-run-display.sh; scripts/build-run-display-loopback-client.sh;
scripts/generate.sh --check. Source pins/export preserve original dependency ownership.
New private PG/numeric HTTP author evidence is separate from scoped doubles and from
independent Review/Testing. Old suites/instances need not be restarted.

Actual author combination at c02cf08 passed7 groups on a fresh private PG/numeric
HTTP instance including official generated Swift GET. Two cap controls use real
DB+ASGI and are labeled separately. Services stopped; complete layer/source hashes
and remaining limits are in tests/evidence/run-display/REPORT.md. No production
limits/account/provider or full App/Issue11 acceptance follows from that result.
