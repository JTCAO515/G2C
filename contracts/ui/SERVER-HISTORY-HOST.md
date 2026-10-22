# Server read-only history / draft UI host

Consumes exact CJ009 **94bad80fdca10e68391022a7593f709c77ccefb4** (parent 5885a18), canonical CJAPI **2f8be7c3e2dd298457488412b3a5e3b2ca59ca93**. Original 5885a18 was held for canonical-equivalent cursor String equality; it is not the final input. Host does not inspect/normalize/restrict opaque cursors. Producer root remains responsible for exact UTF8 cursor validation. Independent producer/combined review is not presumed.

Normal local dependency intake preserves fafa218; final intake base is **562767b39e5c5ba0897aeef3c9bc0a88e73d9379**. No CJMessageClient source/manifest/script edits: exact subtree matches 94bad80. Fixed prepare_generated.py exported 15 canonical CJAPI files into the newly versioned ignored 2f8 directory, after symlink/target checks; generated-pin.json is byte-identical to producer fixed source. Existing key interface export remains unchanged. No additional tracked paths outside prior CJShell/contracts/ui lease were authored.

## Actual UI and API consumption

Assistant has a separate Server history (read-only) sheet, distinct from Local recovery. ServerHistoryHost uses actual MessageHTTPClient.conversations/history/draft and retains actual MessageReadResult wrappers around official CJAPI schemas. No shadow Codable model, local Snapshot-as-server-data, fabricated default records or assumed server titles/timestamps. Default ServerHistoryHost has no binding, client, URL, token or provider; all reads are explicitly unavailable until a trusted root supplies them.

ServerHistoryBinding requires canonical client/recovery/scope/lease, ShellGeneration, explicit page size and MessageReadLimits, synthetic-source flag and trusted current-identity predicate. It grants no authentication or invitation. The host exposes only GET workflows; no PUT, POST, draft update, restore-to-editor, message send or hidden auto-fetch.

Views show explicit unconfigured/idle/loading/empty/ready/failed/resync states. Empty is only a successful canonical empty result. Malformed/unknown/rejected responses become failed, never empty; resync discards the page chain and requires explicit first-page reload. Buttons offer bounded user-driven paging, not an automatic loop. Full original history request bytes/receipt are not displayed; only canonical validated text is shown in stored-messages section.

## Lifecycle / pagination rules

- Every awaited result is passed to canonical validateRead before use, then original binding ID, scope/lease, trusted predicate, ShellGeneration and per-read request identity are checked. Retained wrappers are validated again before exposing values to SwiftUI.
- Separate conversation/history/draft request identities reject late A after B selection and late pages after reload. Same-list loading prevents duplicate in-flight requests. Canonical cursor is passed unchanged to same client/query/lease; duplicate cursor and generation mismatch produce explicit resync. Lists/history are cleared on read failure rather than mixing earlier pages with new context.
- Conversation selection includes the UI list-request token captured by its button; stale row closures after refresh/paging are rejected even if an opaque ID happens to recur. IDs are compared/diffed by UTF8 Data. This local token is not a server authority.
- History generation must match the selected canonical summary; a server generation change requires resync. No field or cursor is fabricated to repair a mismatch.
- ShellState clears server read projections before invoking message/resource invalidation callbacks. This cleanup has no injected resource callback and cannot write to a newer lifetime after reentry. Binding/projections/selected conversation/request identities are discarded on invalidation, immediately hiding all server payloads.
- The shared recovery/credentials lifetime remains owned by the trusted composition root; the read UI does not delete or mutate it. Cleanup failure blocks reconfiguration through the existing messageBindingBlocked gate. Existing unknown-auth/cleanup barriers are unchanged.
- Server draft is a separate readonly snapshot. Explicit null means no draft; non-null empty bytes plus positive revision means saved empty draft. Neither result, any error nor any language change writes ShellState.draft. Local edits remain untouched.

## Build and tests

Package directly references the exact generated CJAPI product alongside CJMessageHTTP. build-demo.sh now builds the real SwiftPM iOS graph then links Demo against compiled modules/objects, rather than manually compiling a partial dependency list. No source generation or probe execution in that script; exports must already exist. Demo imports CJShell public module and default server binding remains absent.

Nine host tests use real canonical generated/client code with in-process synthetic ClientTransport and memory-only storage. Cases: unconfigured vs valid empty; repeated exact cursor resync/no extra read; canonical-equivalent but byte-distinct cursors successfully append pages; delayed history A vs selection B; null vs saved-empty server draft preserving local editor; explicit failure; language/identity fence during await; message pagination with server sequence; selected-generation mismatch resync. Two existing identity callback tests protect prior P2 fixes. All emitted test methods are GET where inspected; no live transport is constructed.

Real service/credential/Keychain, provider, actual UI rendering/device, producer independent acceptance and full end-to-end semantics remain UNRUN/pending. This is a compiled UI + injected lifecycle candidate, not a default fake success or complete server-history acceptance. See evidence/SERVER-HISTORY-HOST.md.

## Deferred read-action origin repair (after fdbbbf)

Read entry methods now REQUIRE a `ServerReadContext?` created by `captureReadContext()` synchronously before Task creation. There is no no-context overload or current-at-execution default. This is a source change to the unaccepted UI-host candidate API, not any CJAPI/client wire change; repository callers are updated.

ServerHistoryView captures context during body/button creation and passes that immutable value to all five first/retry/next/draft Task bodies. Context retains the original canonical binding, opaque cursors, selected canonical summary, selection epoch and per-read request IDs. It is non-Codable and not an identity/authorization capability. Consumers must not call capture inside a deferred old Task to relabel its intent.

Before changing loading state, clearing pages or issuing GET, host verifies that original binding, ShellGeneration, selection epoch and relevant request ID remain current. It uses the captured client/cursor/selection, not a replacement chosen at execution. After await, canonical validateRead and original request/lifecycle checks remain mandatory. Selection invalidates stale list/read contexts; an in-flight list continuation under the old selection cannot settle or leave a stuck loading state. Completed/restarted reads consume their entry context; explicit retry needs a newly rendered/current action, never automatic retry.

Example: `let context = host.captureReadContext()` BEFORE constructing `Task { await host.loadHistory(context: context) }`. Old context after A→B or account replacement is a no-op with zero new requests and no B page mutation. No change to server AUTH, transport, POST prohibition, error/resync semantics or local editor preservation.
