# Local reference selection + P2 stale-settlement repair

Producer input fixed ac2981078ec3a001c577de1d557337010feb5d43, normal local intake merge **163e139c8e206f82a78b914e503dae6b3f9f6260**, preserving 3f65d5c. Producer source unmodified. This candidate combines the already-in-progress unreviewed local-list slice with the urgent P2 repair; it is NOT just a one-line fix on 3f65d5c. Review authored delta from 163e139, and separately retain producer dependency acceptance gates.

## Consumer implementation

Uses actual LocalRecoveryProjection/LocalActionReference/LocalDraftReference. Binding's conversationID/messageID are now optional defaults; trusted scope/lease/generation binding can enumerate without a manually supplied original ID. Existing explicit-ID callers remain source-compatible. Default product has no binding and shows unavailable. Demo no longer supplies current IDs to the host; selection is required.

The existing assistant double-line sheet now displays Local recovery: explicitly unordered local references, not server history, with no message body, draft preview, receipt, key, timestamp or invented sequence. IDs are private in-app metadata only, not logged. ForEach identity uses exact UTF8 Data, avoiding String canonical-equivalence collisions. Array order is consumed as unordered; no sorting/time inference or parallel canonical model added.

Host stores the producer projection itself and validates scope/lease/generation before visibility. Selection takes the original captured projection plus producer reference, validates its originating lease and exact-byte membership, then reads action()/draft() under the current lease. No query is launched merely by selecting an action. Query uses only the selected original ID, and selection is disabled while a query waits. Query completion re-enumerates to reflect current local phases.

Draft selection asks explicit replacement confirmation; its pending intent retains the original projection so a delayed confirmation cannot be rebound to a different account. No body is read into editor until confirmation. Selection failure is visible and never silently empty/success. Identity invalidation clears copied projection, record, selected IDs and pending content. Language only changes labels. Original unknown/notObserved, cleanup-failure and send-disabled rules remain.

## P2 repair boundary

Independent Testing's exact old-A save → synchronous clear/bind-B → old-A throw was reproduced before repair (two failed assertions). Save now captures original bytes and binding before calling storage. Both return and catch can settle only the same recovery instance/lease/ShellGeneration; old failures cannot block B, and saved bytes are never reconstructed from B's current editor.

Query success/error checks use the same binding-ownership predicate and recheck after injected current-state callbacks. Bind rechecks admission after its injected predicate, since that callback may have already installed B. Failed unacquired/stale binding reads do not invalidate candidate resources whose lease may now belong to another owner. Cleanup detaches state/task and sets its own status BEFORE invoking external resource invalidation, with no stale state write afterward.

Same-binding storage errors still invalidate that binding and display storageBlocked. No unknown/POST gate is relaxed. Core action/draft reads are synchronous in-memory operations; storage load occurs during the composition root's MessageRecovery.activate, before host bind. Added load-callback test verifies failed A activation cannot alter a reentrant B host. Existing producer load-generation checks are consumed, not copied.

## Validation

Source tests: original P2 before FAIL; after 17 related test functions PASS (AssistantMessageHostTests8, LocalRecoveryListHostTests5, IndependentHostReentryTests4; the save regression has two argument cases for storage return/throw). Tests cover namespace/lease/callback reentry, same-binding failure, exact NFC/NFD identifiers, delayed selection, chosen-only query, old projection rejection and no initial body read. Prior shared fixtures now use unique synthetic environment namespaces to respect the updated producer's process-wide denial memory; assertions remain intact. Wrong-scope rejection now expects no invalidation callback for an unacquired resource, a deliberate safer ownership rule.

Local list test/preview material is synthetic; no server history/HTTP/Keychain/provider/POST used. Independent review/testing, true device and complete accessibility matrix remain pending. See CJShell evidence/LOCAL-LIST-P2.md for exact source, logs, screenshots and old failure retention.
