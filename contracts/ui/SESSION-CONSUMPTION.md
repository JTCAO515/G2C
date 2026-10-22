# CJ006 read-only consumption check: fixed session lifecycle candidate

Historical pre-wiring assessment. The subsequent bounded in-memory host implementation is documented in [SESSION-HOST.md](SESSION-HOST.md); real SDK/Keychain gaps remain.

Input fixed **ef2c7da41cce9bc994fa7859c29dddd5f915a978**, read with `git show` from cj-007-auth, never its moving worktree. Files inspected: ios/Modules/CJAuth/Sources/CJSession/SessionLifecycle.swift, SESSION-STORE.md, Package.swift. Compared against CJ006 host **ef49452a9707ed206a11448316fc130ede57f0a8**. No Keychain implementation, real credentials, host Keychain, or moving source read. CJ007's reported Swift6 typecheck is upstream author evidence only; not independently rerun or accepted here.

## Exact consumable API

The candidate adds product/module `CJSession`, separate from `CJAuth`:

- `SessionLifecycle(persistence: any SessionPersistence, restorePolicy: .userInitiatedOnly)`; `interfaceVersion` is `CJ-SESSION-STORE@0.1.0-rc.1`.
- Explicit restore: `beginUserRestore() throws -> SessionOperation`, then `load(for:) throws -> SessionMaterial?`.
- Trusted SDK save: `beginTrustedSDKSave() throws -> SessionOperation`, then `save(_:for:) throws`.
- `isCurrent(_:) -> Bool`, `clear() throws`, `noteNetworkUnknown()`, `state: SessionState`, `canUseRestrictedBusiness == false`.
- `restoreAutomatically()` always throws `SessionFailure.automaticRestoreUnavailable`; no silent startup restore.
- `SessionPersistence`: synchronous MainActor `load`, `save`, `clearAndBlock`. Clear replaces credential bytes with a non-secret persistent block marker according to the contract; implementation/atomic persistence is not established by this interface.
- `SessionNamespace(environment: UUID, slot: String) throws`: environment must be explicitly allocated for new G2C; no default namespace/legacy fallback inferred. CJ006 does not allocate one in this read-only check.
- `SessionMaterial(trustedSDKBytes:) throws`: opaque nonempty trusted SDK bytes, not email/password; use `withBytes` only within trusted SDK handling. No serialization/logging/model/UI projection. `SessionOperation`, `AuthAttempt`, and `ShellGeneration` are distinct opaque types; never convert, equate or synthesize their private fields.

## Compatibility and gaps

| Boundary | Current CJ006 / fixed CJSession | Decision |
| --- | --- | --- |
| Identity lifetime | AccountHost invalidates AuthFlow + ShellState; CJSession clear invalidates its original operations before storage access | Semantics compatible; **integration missing**. One composition owner must own all three lifetimes. |
| New account attempt | Current submit clears private shell before dispatch but has no storage dependency | **GAP**: after capability/input checks, fence old Auth/UI and clear channel/task, then call throwing session clear; only successful clear permits new AuthFlow begin/material/dispatch. Do not leave current begin-before-clear ordering when adding persistence. |
| Clear failure | CJSession blocks on error; AccountHost only projects FlowState and reconciliation flag | **GAP**: retain an independent typed SessionState/SessionFailure projection once module is integrated. Clear failure must show blocked, never cleared/logged-out-success, and deny save/restore/new identity dispatch. Private UI remains empty even when storage clear fails. |
| Clear retry | Lifecycle allows explicit clear retry; success moves to cleared and releases its local storage block | Compatible with bounded user-triggered cleanup; never auto-loop. Successful clear does **not** settle AccountHost.requiresReconciliation for an unresolved remote operation. |
| Restore material | load returns material or missing; loadedNeedsVerification is not identity or invitation verification | **GAP**: current AuthSDKAdapter.perform returns only SDKEvent and has no trusted restored-session validation entry. No safe route to consume loaded bytes in current host. Do not interpret non-nil material as signed-in. |
| Save material | trusted save requires SessionMaterial | **GAP**: accepted SupabaseSDKAdapter intentionally returns no credentials/session bytes. AccountMaterialChannel is email/password input only. It cannot supply SessionMaterial; no casting/repacking/encoding password or SDKEvent permitted. |
| Network unknown | SessionLifecycle.noteNetworkUnknown changes presentation only; generation/store remain untouched | Semantics compatible. Must preserve AccountHost unresolved-operation barrier, real identity verification requirement and private-data visibility fence; unknown must not call clear or synthesize invalid identity. |
| Late result | Lifecycle isCurrent checks instance/generation/original operation; host checks original AuthAttempt and ShellGeneration | Compatible with a **three-token capture** held across each await, plus future actual server identity/verification. A fresh token must never relabel an old result. No token alone authorizes business. |
| One-use vs current | load/save consume an operation once, while isCurrent can remain true afterward for post-await validation | Caller must not treat true isCurrent as permission to repeat load/save; second consume throws staleOperation. Awaiting verifier uses the already loaded result with the original token. |
| Unknown restore continuation | noteNetworkUnknown does not invalidate current operation; beginUserRestore/beginTrustedSDKSave are not blocked merely by networkUnknown | Host must own retry/reconcile policy. Current UI has no original-operation lookup and must not use a new begin to bypass unknown or claim that old verification completed. |
| Writer/environment | One lifecycle/writer per namespace required; no multi-process guarantee | **GAP**: exact new namespace and shared composition owner not allocated. Do not instantiate one persistence writer per tab/view, or rebuild by language. |
| Automatic restore | Explicitly unavailable and throws without establishing successful state | Compatible with current no-restore default; future UI must handle the thrown error explicitly, not infer success from unchanged idle. No auto-restore UX is accepted by this check. |

## Minimum future wiring, once the missing seams are fixed

1. A single trusted composition root owns one namespace/lifecycle, AccountHost/AuthFlow and ShellState. It supplies the real SessionPersistence only after its fixed implementation/isolated tests are accepted. Default CJShell remains UnconfiguredSDKAdapter, with no store access.
2. On authoritative identity invalidation or explicit new account lifetime, synchronously fence Auth/UI and transient input first, then call clear. If it throws, retain storage-blocked state and do not dispatch. Clear retry is an explicit cleanup action; it does not remove remote-unknown barrier.
3. Save only exact trusted SDK session material, bound to captured original session operation, auth attempt and shell generation. Current SDK lacks that export; CJ007 must define it before implementation. Never pass secrets into ShellPresentation or FlowState.
4. Explicit restore loads once. Before and after any asynchronous trusted validation, recheck all applicable original tokens and future authoritative identity result; discard stale material/results. Unknown remains unavailable for business and does not clear credentials. Current restore-validator seam and original-result reconciliation are missing.
5. Tests needed when wiring: clear throws after UI/auth fence and adapter dispatch count stays zero; successful explicit clear retry still keeps remote-unknown blocked; stale save/restore after switch rejected; load success cannot grant access; unknown touches neither store nor generation; language does not recreate writer/lifetime. Use injected in-memory persistence with synthetic opaque bytes only, never system Keychain.

## Current decision / evidence

**Accept semantic compatibility only; full consumption PENDING.** No executable wiring or package dependency changed in this delta. Importing this fixed CJSession prematurely would not solve missing secure SDK export, restore validation, error projection or namespace ownership. Do not copy its types into CJShell. This read-only check adds no runtime/test/Keychain acceptance claim and preserves ef49452 for its existing review lane. Main can route the precise gaps above to CJ007 and authorize the minimal fixed-source follow-up after those interfaces are available.
