# Assistant draft / query-only host candidate

Consumes fixed CJMessageClient c79da94c94315dd3b63db0fcc001dda3afa7403b. Default CJShell has an unconfigured AssistantMessageHost: no scope/lease/storage/credentials/query transport, no POST method and canSend always false. Existing 34ebd46 session slice remains an ancestor; this slice adds only shared UI-host behavior.

## Fixed dependency preparation

Main expanded only this clone's CJMessageClient/.generated/** and evidence/generated-pin.json + key-interface-pin.json lease. Checked source/target ancestors for symlinks, clean git state and absent generated directory before preparing. Ran unchanged fixed prepare_generated.py against CJ005 git objects at 312a69caf0bd97ed65679cfd8ff049972c212cef, and unchanged prepare_keys.py against CJ007 f1ce075e4b3f26e6c65bfe4b2fa8bcec8291a552. Verified all 15 CJAPI exported hashes and exact key-interface blob. Both evidence pin files are byte-identical to c79da94; no producer source/script/manifest/evidence diff to commit. Exports remain ignored, must be reproduced by the allocated integration owner. No shadow wire/key types or dependency on a moving producer checkout.

CJShell references adjacent CJMessageClient core product. Own lock adds the fixed graph's swift-collections 1.7.3, swift-openapi-runtime 1.13.3 and swift-openapi-urlsession 1.3.2; previous pins unchanged. Generated/HTTP/key products resolve as package dependencies but this host does not instantiate live transport or a key provider. Standalone demo links the original core sources as a separate static module, never rewrites them.

## Trusted binding and lifecycle

`AssistantMessageBinding` is composition-root input: original MessageRecovery, StorageScope, Lease, current ShellGeneration, conversationID, optional original messageID, explicit synthetic flag, isCurrent predicate, invalidateResources callback and optional queryOriginal callback. Views cannot construct it from draft text, arbitrary account strings, or session token bytes. The trusted root must have established namespace/account/environment, existing key capability and current identity independently; the local scope/token are not authorization.

`bind` validates scope+lease, generation and root predicate; it reads original draft/action using actual CJMessageClient types. It accepts at most one binding per UI generation, not a reset/rebind escape for unknown. `ActionRecord`/`ActionPhase` are canonical; UI activity only distinguishes querying/unknown/unavailable/storage-blocked. The UI never parses or displays opaque receipt bytes as assistant content. No message history list/API or model stream is added.

ShellState holds a weak single host fence. `invalidateIdentity()` synchronously invalidates MessageRecovery and calls the trusted local resource-invalidation hook BEFORE changing generation/clearing private draft/body/routes. This hook must revoke key-adapter/provider bindings, not delete keys or ciphertext. AccountHost already calls this before session clear. Local message rebinding stays blocked during/after failed cleanup; successful local clear removes only that cleanup block, never the trusted identity predicate or AuthAttempt unresolved-operation barrier. Default no-store/no-identity configuration cannot construct a valid binding. No automatic rebind or resource/key creation exists.

Async query captures original binding/ID/lease. After await it rechecks current namespace, lease, root predicate and UI generation before reading the canonical record. Invalidation clears visible record and task; late completion cannot repopulate. Unexpected storage/lease invalidity fails closed instead of leaving a permanent querying status. Query callback must use the same recovery and fixed transport's original-action query; no POST/test-transport activation is provided here.

## Draft and display

Draft saving is explicit and only enabled for a valid binding; original UTF-8 is handed to SecureMessageStorage through MessageRecovery.saveDraft. There is no plaintext fallback. Save error invalidates the binding and shows blocked, never saved. The saved-draft indicator matches the current exact draft bytes and disappears after edits; it makes no delivery claim. Language changes labels only and does not regenerate request bytes or IDs.

- staged: locally staged only; send unavailable.
- queryRequired: original result needs checking, query only.
- latest query error: unknown, retain original action and do not resend.
- notObserved: no receipt observed; not proof of unsent and not permission to POST.
- accepted: confirmed original-action receipt, not an assistant reply, completed run or trip result.

The fixed transport's actual-null decoder remains CJ009-owned. Host tests inject its canonical notObserved outcome without copying a JSON parser. Generic fallback JSON/receipt validation are not reimplemented. `synthetic` bindings show a persistent synthetic-local-state label; no fixture is appended to assistantBody.

## Test / demo scope and remaining gates

Eight focused tests: unconfigured, exact bytes/ID/language/draft, null→notObserved/no send, unknown vs synthetic receipt, identity/cleanup failure + late query + rebind rejection, persistence unknown, wrong scope/same-generation rebind, and reopened staged→queryRequired with original bytes. They use the real core and memory-only storage; no HTTP or session token. Demo --message-demo starts queryRequired; --message-staged, --message-unknown and --message-receipt select explicitly synthetic cases. Original request text and receipts in Demo are marked non-wire fixtures, with no transport.

Live POST activation is still prohibited by c79da94. Real identity/root composition, message-key namespace and existing-key proof, HTTP credentials/query, persistent device storage, Keychain, independent review/testing and physical-device evidence remain pending. Missing keys cannot be interpreted as empty recovery, session material cannot become a key, and cleanup failure cannot restore old private display. No provider/old DB/network/message history was accessed.
