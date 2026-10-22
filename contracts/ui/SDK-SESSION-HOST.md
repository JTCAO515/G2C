# CJ006 official SDK Session host integration

Base main **23e12f28435ab0ddc685d544670564e3fa79db41**, branch `cj/006-session-bridge-host`. Old `cj/006-ui` and 4085470 are preserved. Source intake matches accepted CJ007 **1e63217e2d206c368716d42cde459e34a93a3a73** for SupabaseSessionBridge, SupabaseSDKAdapter and SessionLifecycle. Main relayed CJ007's exact consumption constraints; this new consumer code still requires its own Review/Testing.

## Trust source and default behavior

`AccountSessionVerification` is a narrow trusted composition seam, not a new auth authority/credential schema. One SDK/service verification process supplies BOTH its current verifiedUserID and generation AND verifyInitialSession/revalidateSession hooks using official Auth.Session/SDKSessionCheck. The ID must already come from a trusted current new-environment account binding, never cached Session/JWT/user metadata/form input. AccountHost takes no raw expectedUserID parameter and never derives authority from candidate.user.id. A missing verified identity disables the SDK flow before any store/SDK call; restore is also unavailable. Production implementation of this verification process is NOT fabricated here.

The existing default AccountHost(shell:) remains UnconfiguredSDKAdapter/no store/no verifier. New explicit SDK initializer composes actual SupabaseSDKAdapter with the existing AccountMaterialChannel; configuration must be supplied and fetch defaults to local offline failure. This convenience supplies email material only: Google/Apple remain hostCapabilityRequired even if client ID strings exist, because no platform-token flow is installed. A trusted custom existing adapter factory can consume the same callback seam later; no native/OAuth flow is invented now.

Package only adds the already existing CJAuthSupabase product. No new library/version/lock changes. Brand resource declaration, AssistantShell, BrandAvatar, Resources, scripts/signing and all domain sources remain unchanged.

## Initial login: original operation → verification → secure save → publication

1. Existing explicit identity-start cleanup rules apply. Before SDK work, host captures original AuthAttempt, ShellGeneration, original beginTrustedSDKSave SessionOperation, verification process generation and verified user ID.
2. Actual adapter's onSessionForSecureStorage delivers official Session to AccountMaterialChannel.receiveSDKSession. Host accepts only its exact pending attempt and current captured context, retains one transient candidate and ignores duplicate completion. No password/session enters UI projection, preferences, model input or logs.
3. After SDK returns identityNeedsServerCheck, host awaits the SAME trusted process's verifyInitialSession. It rechecks attempt/UI/session operation/process generation/verified ID. A mismatch/stale flow cannot store a candidate for a replacement account. No late callback mints a new SessionOperation.
4. Only verified official Session is passed to SupabaseSessionBridge.saveTrustedSDKSession with the pre-captured original save operation and trusted expected ID. Successful storage is rechecked against current operation before publishing sessionBridgeResult.stored and committedSessionOperation. Failure is separate from SDK identity discovery and maps to blocked/unknown/rejected as applicable; no false stored result.
5. Publication remains identityNeedsServerCheck / local needsVerification; CJ server principal/invitation/business permission is separate and canUseRestrictedBusiness stays false. A stored SDK session is not a business grant.

## Explicit restore: revalidate → host check → persistVerified

Host load is explicit, never automatic. The official bridge is created for the original load SessionOperation and the trusted current identity/process. Its verifier returns readyToSave without saving. Host then checks original UI/operation/process binding BEFORE persistVerified. Commit intentionally advances the SessionOperation; host adopts bridge.committedOperation only after stored/current checks, not by checking/replacing the old load operation after commit.

For authoritative invalid, UI/private content was already fenced at restore start. After the original binding check, host calls clearAuthoritativelyInvalid. Real clear failure stays blocked and preserves underlying material; mismatch/malformed values do not become authority to delete another session. Network unknown preserves original store bytes, publishes unknown and blocks replacement operations; it does not clear credentials or create a new operation/bridge to repeat a possibly consumed refresh.

Callback/error settlement checks the exact owned restore operation as well as UI/process generation. Stale old load/save/verify results cannot block or publish a newer B. If only an external UI fence invalidates an otherwise owned pending restore, it resolves that old waiting state to unknown without mutating replacement persistence. Current real storage failures remain blocked. Initial/task/channel state is retired before callback-producing invalidation/cancellation, with callers rechecking returned UI generation afterward.

## Compatibility / privacy

Legacy verifyRestored closure remains available for prior projection-only consumers and does not claim SDK persistence. Actual new SDK path uses official types/codec and bridge, not a parallel Session model. Official candidate Session exists privately only for original verification work; final persistence uses SessionMaterial. SDKSessionCheck and SessionBridgeResult are presentation/coordination outcomes, not signed membership. Strings/runtime copies are not claimed memory-zeroized.

The verification implementation is trusted code: it must map transport/uncertain errors to unknown and reserve invalid for authoritative rejection of that original session. No production verifier, automatic refresh/background worker, keychain namespace, access group, endpoint or real credentials are inferred from this candidate. Session material/token/digest is never a message key.

## Local delivery evidence

11 new AccountSDKSessionHostTests use actual official SDK signIn decoding with in-process fetch, official Session codec/bridge and injected memory SessionPersistence. They prove duplicate callback handling, pre-commit verification ordering, adoption of committed operation, missing trusted identity zero calls, unknown byte preservation/no repeat, current invalid/clear-failure handling, stale verification/old-account completion, identity mismatch, actual storage failure, old-save exception preserving replacement B bytes/operation, and unsupported native capability rejection. Related account/session/reentry tests bring the focused run to32 functions PASS. iOS module compile PASS; no signature/device/probe execution.

The exact live account binding/verifier/SDK network implementation and real Keychain path remain unconfigured/UNRUN. Keychain failure probe remains stopped. No raw token output was captured. Producer semantics confirmed through Main are implemented; independent acceptance of THIS host and eventual real resource wiring are separate gates. Evidence is in `contracts/ui/evidence/sdk-session-host/` to remain within this slice's explicit write lease.
