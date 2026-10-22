# CJ023 FEEDBACK internal candidate 0.2.0

Base: `8f2ff45519d1d09f178f1fa766b6829d81bda77a`.
Scope: [Issue 15 / CJ023](https://github.com/JTCAO515/Go2China/issues/15).
This is the FEEDBACK owner's internal Python/SQL candidate, **not frozen FEEDBACK@1.0
wire, registered routes, an App feature or complete Issue acceptance**. CJ005 owns
formal wire, generated clients, migration and cleanup registration.

## Submit and original-action query

The trusted host constructs `Boundary(checker, resolve, sources=optional_sources)`.
`checker` is the existing `cj_auth.admission.AdmissionChecker`; `resolve` maps its
verified `TrustedPrincipal` and server-selected environment to `(connect, scope)`.
It must use stable issuer/subject + environment, never request owner, email, token
expiry or caller scope. `connect` creates a fresh idle non-autocommit PostgreSQL
connection. This module supplies no membership policy or default scope/connection.

`boundary.with_operation(token, callback)` invokes a synchronous callback that
calls `op.submit(Action(original_utf8))` or `op.query_action(action_id)` and returns
**fully encoded bytes**. At most one submit attempt per callback is allowed.
Escaped contexts, other threads, deferred results and swallowed failures cannot
publish success. AUTH is checked at entry, inside the transaction, before/after
commit and after final encoding. Identity/mapping changes withhold publication.
Calling the repository directly authenticates nobody; it is server-internal.

`Action` accepts exact immutable UTF-8 JSON bytes with exactly these fields:

- `action_id`: ASCII letters/digits/underscore/hyphen, 1–128 characters.
- `problem`: nonblank voluntary user text, at most 6000 UTF-8 bytes, no NUL.
- `expectation`: voluntary user text (may be empty), same bound, no NUL.
- `references`: empty for general feedback, or one message and optional one run:
  `{ "kind": "message" | "run", "id": string }`. A nonempty list must contain
  message. IDs retain exact Unicode spelling, at most 1024 UTF-8 bytes.

Total input ≤16384 bytes. Duplicate/extra keys, malformed Unicode, unsupported
shapes, run-only and Trip/Memory/proposal references are rejected. Caller model/
rule versions, usage, duration, tool result, failure stage, owner, scope, transcript
and token fields cannot become authoritative evidence. Voluntary problem/expectation
text is never promoted to diagnostics. Deliberately pasted text is not automatically
classified/redacted; consumers must not prefill full private transcripts and should
ask users to omit credentials.

Receipt fields: `action_id`, `input_sha256`, database UTC `submitted_at`,
`status="submitted"`, `message_en="Feedback submitted."`,
`message_zh="反馈已提交。"`, `source` (null for general feedback). No claim of repair,
training, successful model execution, operator delivery or third-party action exists.

## Exact-byte idempotency and uncertain ACK

Durable key: `(trusted scope, "submit", action_id)`. Per-action transaction advisory
lock serializes absent-row checks; collisions only serialize unrelated work.
Original input is stored once. Same key and exact bytes return the original receipt;
any byte difference conflicts, including JSON whitespace. No reconstruction counts
as original bytes. No queue or secondary diagnostic/usage ledger exists.

`query_action` returns the original immutable receipt or `None` in that scope.
Foreign and absent actions are indistinguishable. `None` means absence in the
observed ledger, not permission to replace action ID/account or infer no earlier
write after retention. A replay/query returns the original stored source observation,
even if its source later expires; it does not advertise that source as currently
accessible or repeat the submission's diagnostic read.

Commit exceptions/cancellation, post-commit guard failure and interrupted cleanup
withhold success with `commit_possible=True`, `recovery="reconcile_original"`.
The host retains original ID/bytes and queries the same action under its original
account/scope. It must not invent a replacement ID. No commit retry is performed.
Projection failure after commit cannot undo the row. Pre-commit rejection does not
disprove an earlier original-ID attempt. Private provider/driver exceptions are
sanitized; cleanup logs use one fixed message and no private values.

## Pinned concrete MESSAGE / RUN composition

Fixed public seams were confirmed and supplied by Main from the original owners:

- MESSAGE `bf79a948c36a7c5cecf40d840cb9623c2d2e9d7c`:
  `Boundary.with_history_context` → `HistoryReadContext.query_message(message_id)`.
- RUN `eadda152d3138ad04696392fcdc59c411c2c95a4`:
  `read_diagnostic(repository, binding)` → `RunDiagnostic` whitelist.

They are imported unchanged in separate preparation commits; see
[dependency pins](DEPENDENCIES.json). No `_service`/`_repository` access, cross-domain
SQL, snapshot copy, run-only reverse lookup or permissive authorization callback is
used in FEEDBACK production code.

`Sources(message_boundary, resolve_run)` is the concrete optional source consumer.
It requires the same canonical checker instance as FEEDBACK. The trusted resolver
receives the MESSAGE context's principal/scope and returns an existing RUN
PostgreSQL Repository for that exact scope. Missing Sources rejects references;
there is no fallback that accepts unverified IDs.

Within each MESSAGE protected synchronous context:

1. Match context principal/scope to the captured FEEDBACK binding, query original
   message and require a non-null verified Stored/Receipt. The owner verifies raw
   command/hash and current chat active/generation. Raw input is transient only.
2. Derive complete RUN Binding from that receipt's conversation, generation,
   message, run, sequence→message_sequence plus trusted context scope. A supplied
   run ID must exactly match. No caller-selected binding field is accepted.
3. Call RUN's public whitelist read, whose repository enforces full binding,
   active scope and expiry. Re-read the message after the RUN read to detect a
   changed association. The context's final original-principal guard must pass.
4. Persist only `SourceReference`: message_id, conversation_id, generation,
   message_sequence, run_id, message_input_sha256, run_status_at_read,
   event_highwater_at_read. The hash identifies message input, **not receipt bytes**.
   No original serialized receipt bytes exist; none are fabricated.

Before feedback commit the full protected read is repeated and must match. Final
encoded response publication repeats it again through MESSAGE's original guard.
Changed/missing/foreign/expired/unknown sources fail with the same safe
`ReferenceUnavailable`. A final-projection change after the row committed is an
uncertain response requiring original action query, not a claimed rollback.

These are separately committed read transactions; **this does not create an atomic
cross-domain source/feedback or provider-revocation fence**. Status may change after
the last observation. The accepted contract stores the authoritative *read-time
observation*, not a guarantee that the source remains active or unchanged at commit,
response delivery, or the earlier instant the user decided to submit feedback.
A strict linearizable source-retirement/feedback policy needs future owner-approved
transaction/cleanup composition. No such stronger guarantee or permission is assumed.

`run_status_at_read` is queued/running/completed/failed/cancelled/context_invalid/
unknown. Event highwater is only sequence progress. **Model/rule version, usage,
duration, tool results and failure stage remain UNKNOWN/unavailable** because the
pinned whitelist supplies none. Their fields are not fabricated or inferred from
status, exception stage, message acceptance, effect payloads or sequence. CJ005
must preserve unavailable/unknown semantics in wire/UI mapping.

## Data, compatibility and remaining gates

This 0.2 candidate adds optional receipt `source` and the candidate table's nullable
`source_reference` to the earlier unconsumed 0.1 core. It is not an in-place database
upgrade; all tests use new empty clusters, and old clusters are preserved stopped.
No registered consumer has been silently changed. CJ005 must review final types,
errors and source visibility before generating formal wire and registering SQL.
Root OpenAPI, migrations, registry, locks, Swift/UI and other domain code are not
modified by FEEDBACK product commits. [Cleanup inventory](CLEANUP.md) identifies
the single private store; production RLS/privileges/retention remain unconfigured.

[Current evidence](../../backend/feedback/evidence/SOURCES-REPORT.md): real local
PostgreSQL persistence using canonical MESSAGE/RUN implementations with synthetic
AUTH facts. Independent Review/Testing are PENDING. Original Issue I prerequisites,
both actual App entry points, real accounts/model diagnosis, devices and deployment
remain **UNRUN**. Issue stays open; submitting feedback never means fixed or trained.
