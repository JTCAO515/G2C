# CJ006 account host candidate

Input: merged main 7cd587bf1476cbdbbee433068fcc7f8fd79427a8, including CJ007 29438a686fe631352ae0885ad3c9e6b7fbf0deb8. Local merge 4a549efdad7259d2c029835a87db13d3008647bb preserves b445424 evidence. This candidate uses actual CJAuth AuthFlow, AuthSDKAdapter, AuthAttempt, FlowState and SDKEvent; no copied auth model or edits to CJAuth.

CJShell's package references ../CJAuth and commits its own eight-pin resolved file. The executable product depends only on CJAuth core; the graph resolves the accepted pinned SDK dependencies but does not activate CJAuthSupabase. The standalone demo script compiles adjacent CJAuth core as a separate static module, then links it. Default is UnconfiguredSDKAdapter: no URL, network, provider flow, Keychain, verified identity, invitation grant or real account.

## Composition and lifetime

- `ShellView(state:)` retains a default AccountHost for its lifetime. A trusted composition root can inject `ShellView(state:accountHost:)`; the host must own the same ShellState. Do not rebuild either on language change.
- `AccountHost(shell:makeAdapter:)` creates an AuthFlow and provides a one-use AccountMaterialChannel plus a current-attempt predicate. A future approved SDK composition root may map the returned EmailMaterial into SDKMaterial.email bound to the SAME attempt; native/OAuth material remains the platform adapter's responsibility. No such real composition is installed by this task.
- `submit(action,email:password:)` is synchronous before the adapter task. It empties the caller's inout password, rejects reentry and unresolved outcomes, checks capability/input, begins the actual AuthFlow attempt and supplies transient email material for that exact attempt. Login/register/provider identity attempts invalidate ShellState before dispatch; recovery does not change identity or clear unrelated draft. The only retained route after starting identity work is the public account entry.
- `cancel()` explicitly cancels local AuthFlow pending context, clears material and cancels the task. It cannot prove remote cancellation, so it retains a reconciliation barrier. `invalidateIdentity()` synchronously invalidates AuthFlow and ShellState, clears transient material/task and retains any unresolved-operation barrier.
- Every completion checks the original pending attempt and UI generation after await before projecting FlowState. An external UI-generation change rejects the result and sets a reconciliation barrier. State never grants business access; identityNeedsServerCheck is not signed-in/eligible.
- Unknown/local cancellation are not retryable via another action or identity reset. No reconciliation endpoint exists in CJAuth yet, so this host has no button to remove that barrier. Process restart persistence/real recovery remains an integration gap; no real transport is enabled in this candidate. A future host must not reset/reconstruct the host to bypass an unresolved real operation.

## Input privacy

Password lives in AccountView SecureField state and the exact-attempt material channel only until consumed/cleared. It is not part of observable AccountHost projection, ShellState, navigation, preferences, Codable, model input or logging. Field clears on submit, mode change, identity-generation change and disappearance; email clears on disappearance/identity change. Account view disappearance cancels local waiting. Swift String may have runtime copies; this is bounded retention, not a memory-zeroization guarantee.

The channel returns material once only for its bound attempt and clears it; the adapter must independently obey the supplied current predicate and secure-lifecycle contract. No password values are captured in runtime screenshots. Unit tests use explicit synthetic-only values and assert boolean observations rather than printing material.

## User-visible behavior

Memory → Account contains email sign-in/register/recovery forms, SecureField when applicable and Google/Apple actions. Default actions clearly say not configured/unavailable and cannot dispatch. No false login, email delivery, password reset, provider consent or invitation success. All FlowState cases have bilingual bounded descriptions. Email verification and reset callback routes are still unavailable upstream; no invented callback parser.

## Validation and remaining integration gaps

Six injected-adapter host tests cover default unavailable, one-use material/private cleanup, language stability, unknown/reentry, cancellation/identity-change lateness and recovery separation. Existing shell tests are reused after initial dependency build; no unrelated service suite. Actual SDK adapter tests remain CJ007's evidence, not rerun here. API errors/purpose and SDK one-attempt execution semantics are consumed unchanged.

Required follow-ups through Main: confirm factory/material seam with CJ007; define original-operation reconciliation and durable unresolved guard before any real transport; authorize real SDK/secure storage/platform callbacks and server/invitation checks separately. Missing native capability must be returned as unavailable by adapter capability checks. C2, real OAuth/Keychain/console/user profiles and physical device acceptance remain UNRUN. No root iOS engineering/shared API changes.
