# Same-context original message lookup for feedback consumers

Fixed base main8f2ff45519d1d09f178f1fa766b6829d81bda77a, isolated owner checkout
cj-009-context-query / branch cj/009-context-query. Shared export candidate4fb05cc and
all original owner trees remain untouched. Scope: backend/message only; no feedback
code, root API, domain SQL, RUN states, permission policy or infrastructure change.

## Public interface

`HistoryReadContext.query_message(message_id: str) -> Stored | None`

Obtain the context ONLY from `Boundary.with_history_context(token, operation)`; same
callback exposes the captured trusted `ctx.principal` and `ctx.scope`. No private
_service/_repository use, independent second identity selection, caller owner/scope,
JWT parsing or run-only lookup. This is a read seam, not permission to commit feedback
inside the callback; feedback owner still needs its own scoped write/confirmation fence.

query_message reuses Service.query and therefore current server-selected scope, scope
lock, original receipt chat active/creation-generation check, and transaction/commit/
return guards tied to the original principal. It then checks before returning:

- command parsed from ORIGINAL immutable raw bytes through existing public Command.parse;
- requested message ID == command.message_id == receipt.message_id (no normalization);
- command.conversation_id == receipt.conversation_id;
- SHA256(raw) == receipt.input_sha256;
- actual Stored/Receipt types, positive non-bool sequence, nonempty generation/run ID.

Malformed stored input/shape/hash/association fails Unavailable; dependency/guard errors
propagate and never become None. None ONLY denotes absent record in this scoped ledger,
not proof an action never happened, permission to write/retry, or a valid feedback source.
No query input or private raw body is included in errors/logs.

Stored is returned unchanged: raw bytes + structured immutable Receipt fields
message_id/conversation_id/generation/sequence/run_id/input_sha256. There are NO original
serialized receipt bytes. Do not reconstruct JSON and label it an original receipt or
use input_sha256 as a receipt hash. Feedback must compare any proposed source run_id
exactly to the original receipt.run_id, and retain only approved minimum references,
not casually copy private body bytes into diagnostics/feedback storage.

This proves accepted message/original assigned run linkage, NOT RUN acceptance, execution,
completion, valid answer, tool effect or model success. RUN status/evidence remains the
CJ010 public authority. No completion enum or second run source was introduced.

## Context lifecycle limits

Context is usable only during its synchronous callback, on its creating thread, in the
current ContextVar binding. Retained/expired contexts and cross-thread use (including
copied contextvars) reject before repository calls. Nested with_history_context is
refused before checker/resolver, so nested binding cannot replace the current principal.
The entry marker is reset in finally even on initial binding errors. A later independent
call can obtain a new valid context. No await/generator response is allowed, as before.

The context properties establish callback lifetime, not an independent AUTH grant.
Every actual query retains existing current gates and the outer final same-principal/
unchanged-scope guard after projection. Consumers must materialize approved read results
inside callback and must not retain context/metadata as future permission. Provider
freshness/distributed revocation remains an existing limitation, not solved here.

## Executed checks

Python3.14.7 using real AUTH interface/admission code in the fixed main checkout plus
synthetic verifier/facts/repository, no database or network:
- 7 new context_query_tests PASS: exact raw/original receipt + same metadata; absent vs
  dependency/inactive/recreated rejection; changed hash/raw/IDs/conversation/invalid
  receipt; identity/final guard changes; expired/cross-thread with copy_context; nested
  callback refusal; resolver reentry refusal before a second authority binding.
- 3 targeted existing history-context checks PASS: ordinary single identity, expired/
  deferred/error cleanup, final projection guard. No unrelated suite or PG rerun.
Logs: evidence/context-query-tests.txt, context-query-regression.txt.

No resource capability expanded, no live account/provider/PG/Keychain/HTTP/publish action.
Independent Review/Testing pending. CJ023 may consume the exact signature/fixed candidate
for source association; this is not a complete feedback write contract or Issue closure.
