# CJ006 account host delivery evidence

2026-10-21 Asia/Shanghai. Source candidate **33754a2a0925f2555e095e1b2222a7c6e45a9cf7**, first implementation e4fc8c1d10c54b65196c5ef57abca62dd108cea5. This evidence commit does not change executable source.

## Base / scope

Started clean at b4454241e2ccaf3a43148fcbf4afb52dde7bc3f2. Local Publish source initially lacked the requested merged main object, so fetched the canonical repo main directly into this clone; FETCH_HEAD read back exactly 7cd587bf1476cbdbbee433068fcc7f8fd79427a8. Verified accepted CJAuth 29438a6 ancestor. Normal merge 4a549efdad7259d2c029835a87db13d3008647bb succeeded without conflict; no reset. Prior b445424 and 0c2462f remain ancestors.

Review implementation diff **4a549ef → 33754a2**, not the inherited main merge as author-owned changes. All authored changes limited to contracts/ui and ios/Modules/CJShell. `git diff 7cd587b -- ios/Modules/CJAuth` empty. Root iOS project/API untouched. Own package lock matches all eight accepted CJAuth pins. Copied read-only local bare dependency cache into /tmp/cj006-spm-cache; no global cache/config changes. Standalone demo statically links accepted adjacent CJAuth core and does not initialize Supabase SDK/network.

## PASS — author tests / build

- New AccountHostTests **6/6 PASS** (account-host/host-tests.txt): unavailable capability, exact-attempt one-use material, private projection clearing, language/generation retention, duplicate/unknown fencing, cancellation + identity-change late completion, recovery distinct from login. Controlled adapter uses real AuthAttempt/SDKEvent/FlowState and holds continuations; no sockets/services or real identities. `canUseRestrictedBusiness` stays false.
- Initial dependency build also ran the six existing ShellState tests PASS; existing independent shell validation is reused, no unrelated full suite repeated.
- Final iOS Simulator arm64/iOS17 target compiled and signed (account-host/ios-build.txt). Swift 6.4, installed Simulator SDK27.1. This is not iOS17 runtime proof.
- Source change after host tests only adds same-shell injection precondition/helper and explicit account field AX labels; final iOS compile covers these. Async behavior tests apply unchanged. Actual label change was driven by runtime evidence: initial fields exposed placeholder but blank label; final snapshots expose Email address and Password explicitly.
- Dependency pins compared programmatically against CJAuth, PASS; `git diff --check` PASS.

Reproduce focused tests from repo root, with fixed dependencies available:

```sh
env CLANG_MODULE_CACHE_PATH=/tmp/cj006-clang-cache SWIFTPM_MODULECACHE_OVERRIDE=/tmp/cj006-swift-cache \
  swift test --disable-sandbox --package-path ios/Modules/CJShell \
  --scratch-path /tmp/cj006-host-build --cache-path /tmp/cj006-spm-cache \
  --disable-automatic-resolution --filter AccountHostTests
bash ios/Modules/CJShell/scripts/build-demo.sh /tmp/cj006-account-demo
```

## PASS — bounded actual simulator observation

Own CJ006-Shell-20261021 / iPhone17 Pro / iOS26.5, UDID 824A7623-8882-45C9-94A7-7BD2F758B685. No other owner's device touched. Reused prior device/app; installed newly compiled local.cj006.shell.demo.

- Normal Chinese Memory → Account: shows unverified/no-grant text, sign-in form and disabled/unavailable actions. Changed mode to Register: password field remained; changed to Recover password: password field absent. Captures account-default-zh/recovery-zh are e4fc8c1 before explicit AX-label fix; final UI unchanged visually except accessibility labels.
- On final 33754a2 source, gallery switches read back accessibility3 on and Memory selected. Opened Account, scrolled to Google/Apple; both explicitly unavailable, neither is an actionable AX target. Their provider flows were not invoked.
- Scrolled to input fields at large font; AX shows explicit Email address/Password labels. Focused the empty email field, observed keyboard and Done, operated Done and verified it disappeared; back returned to Memory with Account target available.
- No password or actual account input was entered during UI observation. Images contain empty fields only. Synthetic material used only in unit tests is not logged or screenshotted. No account submit action possible in the default unconfigured UI.
- Images were opened/visually inspected, snapshots read back; tool ACK alone was not counted. Generic gesture without visible change was superseded by verified visible scroll. Device stopped and read back **Shutdown** at completion.

This is not real auth, VoiceOver speech, every accessibility size/device, or successful email delivery. Gallery's labelled close control is demo-only. Runtime snapshots/images in account-host; sha256.txt provides artifact hashes.

## Boundary / next

Host/material lifetime and mapping: contracts/ui/ACCOUNT-HOST.md. Default adapter is UnconfiguredSDKAdapter, no configured endpoint, real OAuth, Keychain, console or user profile. All results remain UI presentation pending server/invitation verification; login does not grant beta/business access.

CJ007 interface follow-up required through Main: confirm trusted factory + one-use material mapping into SDKMaterial and original-attempt predicate; no CJAuth source edited. There is currently no original-operation remote reconciliation API. Host therefore blocks another attempt after unknown or dispatched local cancellation, including after identity reset; a new host/process must not be used to bypass this for real operations. Durable unknown recovery, actual secure storage/platform callback composition and provider capabilities remain UNRUN/unconnected.

Independent review/testing of this new delta, real service, physical device and C2 remain pending. Issue not closed; no push/remote PR/merge/deploy or external account action. Local normal merge above was explicitly authorized dependency intake, not shared integration.
