# Explicit local session host slice

Consumes fixed CJ007 **b5ef9e57be6d48afaf673bb872c7246552d14c1c**, whose SessionLifecycle interface is unchanged from ef2c7da41cce9bc994fa7859c29dddd5f915a978. Dependency intake was a normal local merge 9e4425a19741ee68e831a9fa270de432393e39cb, preserving ef49452/f52a67d. Review authored delta from 9e4425a; no CJAuth source edited. Earlier SESSION-CONSUMPTION.md remains the historical pre-wiring gap assessment.

## Actual integration

CJShell now depends on the existing CJSession product. AccountHost accepts optional `SessionLifecycle` and optional MainActor async `verifyRestored(SessionMaterial, SessionOperation) -> RestoreCheckResult`. Default is nil lifecycle and UnconfiguredSDKAdapter: no store reads, no automatic restoration, no Keychain store construction, no network or real credentials. The verifier callback is a trusted composition seam; this candidate ships no real SDK session decoder/validation flow.

`RestoreCheckResult` has only needsServerVerification / rejected / networkUnknown. None grants login, principal, invitation or business permission. `LocalSessionStatus` is UI presentation only and wraps the actual SessionFailure for storage blocking; AUTH/CJSession types are not copied. Opaque material is passed directly to the injected verifier and never to ShellState, preferences, logs or UI. No save path, raw byte inspection or SDK session export is introduced.

## Operations and ownership

- One host owns its AuthFlow, ShellState and injected lifecycle. No lifecycle per view/tab/language and no namespace allocation here. The composition root must provide one writer per namespace if persistence is ever enabled.
- `restoreSession()` is explicit. It requires configured/unblocked storage, no pending flow/restore and no unresolved-operation barrier. It fences old Auth/UI/transient material, retains only public account route, captures the new ShellGeneration and original SessionOperation, then calls load exactly once. Missing, storage failure, loaded-needs-verification and asynchronous verifier results are distinct.
- No verifier: loaded material is dropped and state remains needsVerification, never signed-in. Restore button stays disabled while awaiting required verification; no hidden retry. With a verifier, completion checks original operation and UI generation after await before any state projection. Late results cannot restore private content. Stale completion resolves waiting to unknown/blocked rather than leaving a spinner stuck.
- `clearLocalSession()` first invalidates AuthFlow and ShellState, clears transient input/task, then invokes throwing SessionLifecycle.clear. The user remains on public Account to see success/failure. No old private route/body/draft survives. Success means local store clear only, never server revocation; failure shows blocked and prevents restore and new auth dispatch. Explicit cleanup retry is available, never automatic.
- `invalidateIdentity()` uses the same storage cleanup but does not retain Account navigation. New identity sign-in/register/provider work performs local clear before AuthFlow.begin/material/dispatch when a lifecycle exists. Storage failure therefore produces zero adapter dispatch. Email recovery alone does not rotate identity.
- Restore cancellation fences local callback/UI, marks unknown and preserves storage. Network unknown uses noteNetworkUnknown, never clear; it preserves lifecycle operation and storage. Language changes neither lifecycle nor identity/operation.
- Clearing successfully NEVER removes requiresReconciliation. Existing AuthAttempt unknown, in-flight cancellation or restore unknown cannot be bypassed via cleanup, identity reset or another provider. There is no reconciliation API/override in this candidate. A future host must not reconstruct itself/process to evade a real unresolved operation.
- Successful clear leaves a persistent tombstone under the persistence contract. Restore is disabled after cleared until a future trusted SDK save/new lifecycle integration exists; this slice does not invent a save to unlock it.

## UI and synthetic display

Memory → Account adds a local-session section: explicit restore, local sign-out/cleanup, and bilingual states (unconfigured, waiting, missing, needs verification, verification failed, unknown, cleared, storage blocked). Existing default sign-in/provider capabilities remain unavailable.

The standalone Demo accepts `--session-demo`: a visible synthetic banner and a Demo-only in-memory SessionPersistence. `--clear-fails` injects storageUnavailable; `--restore-unknown` injects verifier unknown. No Keychain namespace/query is constructed, no user bytes are used and no store is persisted. Default launch without these flags remains unconfigured. Existing gallery is unchanged. Demo code is outside package products.

## Evidence and remaining seams

Nine focused LocalSessionHostTests cover default no-store, one explicit load/no grant, clear failure/zero dispatch/retry, late result after clear, restore unknown/no storage mutation, language stability/rejection, load failure, stale waiting resolution, and original AuthAttempt unknown preserved after successful cleanup. Affected prior AccountHost tests were checked once during integration; unrelated suites/runtime were not repeated. See ios/Modules/CJShell/evidence/SESSION-HOST.md for fixed source and observations.

Still unconnected: trusted SDK session export/save, real restored-session validation/server invitation, durable unresolved-operation recovery, real Keychain/entitlements/access group and physical-device lifecycle. These stay with the existing CJ007/Main coordination; no access-group or protection policy guessed. CJ007's Keychain -34018 failure remains upstream FAIL/BLOCKED and is not repaired or hidden by this in-memory host demonstration. Full independent review/testing of this slice remains pending.
