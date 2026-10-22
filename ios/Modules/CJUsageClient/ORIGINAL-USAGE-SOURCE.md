# Original accepted MESSAGE → closed usage source

Incremental product slice after `49d146c1b3f608d9142bf18be4aeaf14c6281e57`.
Dependency-only prep **6f2d877cee7d7a845c920de10c94730b3c542c1d** restores the exact
CJMessageClient tree from **6936a632ecc5cdbfd615b80c75312a09ed64b23a**.
The product diff is prep→new head, ONLY CJUsageClient. Exclude prep when integrating.
SDK33 **33cec5ba71d74820cb0acd3c89ecbe39ba125590** is exported from exact original
Package/lock/Sources/Tests blobs. Module lock, canonical AUTH and all seven previous
SDK exports remain unchanged. No CJShell, shared, root, registry or App wiring change.

## Public input and flow for CJ006

Construct `OriginalUsageViewModel` with canonical `SessionLifecycle`, `MessageRecovery`,
its original `StorageScope`, explicit `MessageEndpoint`, original credential callback,
`currentBinding` and canonical `NoRedirectTransport`. Absent config fails closed.

1. Obtain the original canonical `ActionRecord` from the current MESSAGE recovery
   after its actual receipt query/submission returned accepted. Pass that record and
   original `Lease` to `captureAcceptedMessage`. This method reads current recovery,
   requires accepted phase and identical original record/receipt bytes, decodes the
   actual generated `MessageReceipt`, and checks ID/digest/original conversation.
   It does not query MESSAGE, stage input, mark accepted or mutate any store.
   Do not construct an accepted ActionRecord/receipt from IDs or an AuthAttempt.
2. The returned `AcceptedUsageMessage` has NO public initializer. Create
   `OriginalUsageBinding(acceptedMessage:sessionOperation:actorIdentity:selectionGeneration:revision:)`
   using the original canonical SessionOperation and current host lifecycle values;
   publish this same binding in `currentBinding`. A-B-A requires new selection generations.
3. On explicit user action, synchronously `prepareAssociation(binding)` BEFORE a Task,
   then `await read(prepared)`. The actual generated `Client.getOriginalUsageAssociation`
   issues only `GET /v1/message-usage-association?message_id=<original message>`.
   There is no caller attempt/run/scope selector.
4. A successful response must match original receipt message/conversation/generation/
   run by UTF8 bytes and exact positive sequence. Missing/null/extra/invalid refs fail;
   malformed/foreign associations never create a source. MESSAGE message/conversation/
   generation fields are nonempty without a USAGE scalar cap, within configured
   original/receipt/request/response byte budgets. Attempt/operation and the actual
   stored RUN usage binding retain their own 200-scalar limits. 503 becomes
   `.failed(.unavailable)`, without retry or a status GET. Render existing bilingual
   UsageFailure.unavailable copy rather than a numeric zero.
5. `.sourceReady(ResolvedUsageSource)` contains a CLOSED official response result with
   no public initializer or seven-ref acceptance API. It preserves original attempt,
   operation and run. The result is local model/source ownership, not authorization.
   The host can show a source-ready action; do not claim usage has been queried yet.
6. On a SECOND explicit user action, call `prepareStatus(source)` synchronously, then
   `await read(prepared)`. Only this model's current source can be used. Actual generated
   GET reads its exact original attempt; status must match its attempt/operation/run.
   `.loaded(UsageSnapshot)` can render through the existing UsageStatusView.

`Tests/PublicInterface/OriginalUsagePublic.swift` typechecks without @testable; its
sequential code demonstrates types only, not permission to auto-run the second action.
External compile-negative probes confirm both source constructors are inaccessible.

Each preparation installs an independent owner before callbacks, including equal
revision reentry. Both stages guard original source record/current recovery lease,
SessionOperation, actor, selection, revision and preparation ownership before/after
credential callbacks, transport, body await, generated decode and final publication.
Callback reentry/old errors/cancellation cannot overwrite newer work. Host calls
`invalidate()` synchronously on session/selection teardown; no remote cancellation.
No new persistence, KeyPurpose, attempt/operation ID minting, POST, automatic polling
or retry. GET wrapper keeps JSON/duplicate keys/no-store/trace/byte limits. The original
explicit-host UsageSource/UsageViewModel API stays compatible and is NOT a substitute
for this official provenance path.

## Evidence boundary

Association proves only stored original references. It does NOT prove a USAGE row,
reservation, dispatch, provider execution, payment or production source availability.
RUN068's actual writer remains SyntheticFirstStep-only. Producer/root gates remain independently owned; this slice makes no producer/root
acceptance claim.
All tests are in-process, with canonical MESSAGE query creating synthetic accepted
input and canonical default NoRedirectTransport intercepting both official GETs.
Real network/accounts/keychain/cache/SQL/provider/billing/App/device/full I remain UNRUN.
See evidence/ASSOCIATION-RESULTS.md for author results and all retained failures.

Field-boundary P2 repair evidence: `evidence/REFERENCE-BOUNDS-REPAIR.md`.
