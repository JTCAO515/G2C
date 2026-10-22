# Server draft save UI — explicit intercepted-test capability only

Consumes exact CJ009 **625b66d8728fa3102c6a88ed7996c0b62a4a0002**, including approved canonical draft CAS/confirmation/reconcile chain and exact-byte durable readback fixes. Local normal intake base **3d6ad58d4ee5c330a5c17205db43c7629eb3d6df** preserves c3d7524. CJAPI remains fixed2f8; no CJ009/CJAuth/API/Keychain source change. Parent read-only delivery remains reproducible independently.

## Capability and canonical methods

ServerHistoryBinding adds optional ServerDraftWriteCapability, with ONLY `interceptedTestOnly`. Default nil and non-synthetic bindings cannot save. The actual MessageHTTPClient still enforces its own live PUT/POST prohibition; this local test marker cannot open that gate. GET configuration, an observed server draft/null, or an endpoint alone never grants write capability. The UI displays live writes unavailable and requires explicit test injection; default App has no configured binding or fake save success.

Uses actual `saveDraft`, `validateDraftConfirmation`, `reconcileDraft`, `validateRead` and `MessageRecovery.draftSave`; stores only canonical DraftSaveConfirmation/record and local presentation state. No custom wire/CAS record/receipt, token-derived key, force/retry endpoint or backend authorization was created.

## Frozen user actions / editor identity

`captureDraftWriteContext()` runs before action/Task creation. It captures canonical binding/read-selection context, original UTF8 editor bytes, a local editor revision, expected CAS revision and host operation epoch. The expected revision comes from a current canonical first draft read (null gives initial zero) or an exact previously confirmed original save, only after checking no unresolved CAS remains. A readback never overrides an unresolved original record.

`saveServerDraft(context:)` is synchronous at entry and returns the owned Task for optional waiting. Before local mutation/dispatch it checks original binding/selection/generation, editor revision/bytes and explicit capability; stale actions are no-ops. It registers the captured editor bytes once through canonical recovery.saveDraft so the domain captures an editor revision. This does not modify ShellState.draft and is not automatic keystroke persistence. Async dispatch uses the captured original fields and rechecks current context at Task start. Save outflow/ack/unknown persistence remain the canonical client's responsibility.

After await the host calls validateDraftConfirmation, checks original binding/selection/write epoch and current scope. Only matching canonical confirmation plus the same UI editor revision and exact bytes displays saved-current-edit. Later edits, including changing away then returning to identical text, remain preserved and display saved-earlier-edit. No response assigns editor text. A language change does not assign draft or rotate its editor revision. UI draftRevision is ephemeral local presentation metadata, not a message ID, wire CAS or authorization.

Unknown/conflict/cancellation retain original CAS/query-only behavior. Explicit cancellation cancels the owned Task; it cannot promise server rollback. A local cancellation barrier cannot be removed by changing selection or refreshing GET. If no original pending target exists, UI stays blocked rather than fabricating one. No automatic replacement save or expected-revision substitution exists.

## Query only / privacy / concurrency

`captureDraftQueryContext()` captures the original canonical record and binding/selection/operation context. Query execution rechecks them before GET and after validateRead; a consumed query context cannot run again. Actual reconcileDraft GET observes the stored original conversation/generation. Equal body/revision or null sets only observed/missing UI status; no confirmation or save capability is restored.

Pending record bytes are never displayed. Record from a different selected server generation is blocked, not exposed or relabelled. Identity invalidation retires all write/query/read projections and owned Task before cancellation; ShellState checks its generation again after that callback so a reentrant newer lifecycle cannot be cleared by old outer work. Unknown A queries cannot target replacement B. Root owns real shared persistence and identity verification; this slice does not access Keychain/session/provider material.

Selection/list refresh cannot run while save or original-query work is active; save/query cannot start during a list refresh. This prevents abandoned state from leaving a new selection stuck in the old operation. Old in-flight completions still require their original epoch. Read-only server draft remains separate from editor and the original message send/recovery feature. No POST/message send path was added.

## Validation and remaining activation

Ten new host test functions use concrete canonical client + in-process intercepted responses + memory-only storage. Empty/nonempty confirmation and null/matching unknown query each have two cases. They cover GET-only no capability, exact original bytes, language stability, new/same-byte later edits, stale action zero outflow, cancel, conflict, old-account unknown-query rejection and old-generation record hiding. Existing read-origin and identity checks remain applicable and were run for affected paths. See evidence/SERVER-DRAFT-SAVE-HOST.md.

Real PUT/POST, real server/provider/Keychain/account, device display and durable product activation remain UNRUN/unavailable. A real write-capability/antirollback/reconciliation design is outside this slice and must not be inferred from test injection or GET success. No default demo fixture supplies a write capability.

## Cancel-origin P2 repair after6773

Cancel controls must capture `captureDraftCancelContext()` while that original save is displayed, before retaining/executing their closure. `cancelServerDraftSave(context:)` requires that context; the unsafe no-argument overload is removed. The context holds original binding ID, ShellGeneration, selection epoch, write epoch and Task. Before any cancellation-state mutation, all origin fields must still match an active save; expired A cannot resolve or cancel current B. It cancels only the captured original Task and does not mutate state after cancellation callbacks. A current cancel still retains CAS/query-only behavior and never means remote rollback. Existing/default write capability and canonical live gates are unchanged.
