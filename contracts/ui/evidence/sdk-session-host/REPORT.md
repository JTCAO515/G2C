# CJ006 official SDK Session host candidate

2026-10-22 Asia/Shanghai. Base **23e12f28435ab0ddc685d544670564e3fa79db41** → source **6f9393efe3ecef25ddb17e393863759bcab8e58f** (initial implementation030285a). Branch `cj/006-session-bridge-host`, same owner/worktree. Previous `cj/006-ui@4085470` remains intact. This evidence commit adds no executable changes.

## Executed implementation

Actual AccountHost code consumes accepted SupabaseSessionBridge/SessionLifecycle and official SDK Session. Initial login path: original AuthAttempt/UI generation + pre-captured trusted save operation → actual SupabaseSDKAdapter Session callback → one trusted SDK/service verification flow → official encoding/save → current stored-operation publication. Restore path: explicit load → bridge.revalidate → original host/operation check → persistVerified → adopt committedOperation; authoritative invalid uses explicit checked clear, not a premature callback save/delete.

One injected AccountSessionVerification supplies current trusted verified user ID, verification generation and official Session hooks. Host has no raw expected-ID input and does not promote cache/JWT/candidate IDs into authority. Missing identity rejects before SDK/storage, and default App composition remains unconfigured. The concrete convenience provides email material only, rejecting unimplemented native provider flows before clearing/dispatch. Legacy projection-only hooks remain compatible and are not mislabeled persisted sessions.

Publication is sessionBridgeResult.stored + current committedSessionOperation, not business/eligibility grant. Existing UI state remains identityNeedsServerCheck/needsVerification; canUseRestrictedBusiness is false. Unknown restore preserves original bytes and prevents replacement operations. Initial sign-in retains the already-accepted explicit new-identity cleanup policy; a network error itself does not initiate another clear. Raw Session values stay private/transient; no plaintext session/token/password logging, preferences or model output, no session-to-message-key conversion.

## PASS — local evidence

**32 test functions PASS across five affected suites**: new AccountSDKSessionHostTests11, existing AccountHost6, LocalSessionHost9, IdentityCallbackReentry2, IndependentHostReentry4. Parameterized cases retained; tests.txt is actual final output.

New checks include actual official SDK decoding of an intercepted synthetic sign-in response; duplicate callback/repeated submit gives one verification/store; verification before persistence and post-persistence publication; current committed operation adoption; zero SDK/store calls without trusted identity; unknown byte preservation/no second restore; authoritative invalid vs failed clear; identity mismatch without deletion; current storage failure blocked; old async verify/identity result discarded; old persistence error cannot invalidate replacement B bytes/operation; native provider IDs alone do not pretend platform capability exists.

The verifier/store/fetch are explicitly synthetic and in-process. SDK objects/codec/adapter/bridge/lifecycle are actual pinned implementations. No actual token/signature/server authentication, provider, Keychain or network is claimed by this injected PASS. Official SDK2.55.4 Session constructors/encoder/decoder were inspected in fixed local source. A changelog fetch attempt returned unsupported markdown content-type; no SDK version/API was changed or inferred from unavailable current docs.

An affected old test initially exposed a stuck wait after an external UI fence. Corrected ownership checks now settle an otherwise owned old wait to unknown without touching a replacement persistence operation. Old callback/persistence state protections remain; final32 PASS. Tests reran only after those relevant code changes. No unrelated full-suite, device or backend testing.

**iOS module build PASS**, ios-build.txt: actual CJShell + CJAuthSupabase package graph, Swift6.4, arm64 iOS17 simulator target, installed SDK27.1. Module compile only: no code signing, App launch, device/probe retry or credential access. Brand resources are compiled unchanged, not revalidated as new imagery/runtime evidence.

## Exact scope proof

Package.swift differs from base ONLY by `.product(name: "CJAuthSupabase", package: "CJAuth")`; removing that literal produces the original bytes including brand resource declaration. Package.resolved, AssistantShell.swift, BrandAvatar.swift, Resources, build scripts/signing files, CJAuth/CJMessageClient/domain sources and ios/Branding have no diff. The three consumed bridge/adapter/lifecycle files at base match CJ0071e63217 git blobs exactly. `git diff --check` PASS. No new library, lock upgrade, frame, wire type, credential schema, root config or parallel storage authority.

Evidence stays under contracts/ui as required by this slice's narrower lease. No HANDOFF/main state file edited. Input semantics were confirmed by CJ007 via Main; this new host delta still needs independent Review/Testing and exact consumer confirmation, not author self-approval.

## Reproduce / remaining

```sh
env CLANG_MODULE_CACHE_PATH=/tmp/cj006-clang-cache SWIFTPM_MODULECACHE_OVERRIDE=/tmp/cj006-swift-cache \
  swift test --disable-sandbox --package-path ios/Modules/CJShell \
  --scratch-path /tmp/cj006-sdk-host-build --cache-path /tmp/cj006-spm-cache \
  --disable-automatic-resolution \
  --filter 'AccountSDKSessionHostTests|AccountHostTests|LocalSessionHostTests|IdentityCallbackReentryTests|IndependentHostReentryTests'
```

The iOS command uses `swift build --target CJShell --triple arm64-apple-ios17.0-simulator --sdk <installed simulator SDK>` with SDKROOT unset for the macOS manifest; no build/signing script is edited or run.

Remaining actual-resource prerequisites: trusted real-account verification implementation/current binding, configured approved SDK fetch and service validation, actual Keychain/entitlement/storage acceptance, real OAuth/email and device/server invitation acceptance. New users without a trusted binding stay unavailable; no cached/unverified bootstrap path was invented. Keychain failed probe stays stopped. No push/remote PR/merge/deployment or live service operation. Entire #7/#8 not closed by this local candidate.
