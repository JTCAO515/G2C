# CJ006 explicit local session UI evidence

2026-10-21 Asia/Shanghai. Source **00ae54bc3697b70babd3ca7c22120a1ca81bf668**; evidence commit adds no executable changes. Intake merge **9e4425a19741ee68e831a9fa270de432393e39cb** imports exact fixed CJ007 b5ef9e57be6d48afaf673bb872c7246552d14c1c normally, preserving prior ef49452 delivery. Review authored 9e4425a → 00ae54b diff. No CJAuth/root engineering/shared API edits. b5ef9e57 SessionLifecycle interface matches ef2c7da. No moving Keychain source was consumed; no live Keychain store was instantiated.

## Author-local PASS

- `LocalSessionHostTests`: **9/9 PASS**, log session-host/tests.txt. Real CJSession interfaces + injected memory store/controlled asynchronous verifier. Tests cover explicit load/no access grant, clear failure fences UI and blocks restore/new auth dispatch, successful explicit cleanup retry, late callbacks, unknown preserving storage and generation, language preserving operation, load failure distinct from missing, stale external UI invalidation resolving waiting to unknown, and original AuthAttempt unknown still blocking after successful cleanup.
- Actual source compilation / iOS Simulator arm64 iOS17 target bundle build PASS (session-host/build.txt), Swift6.4 / Simulator SDK27.1. This does not prove iOS17 runtime behavior.
- The affected six AccountHost tests passed once during initial integration of session hooks; retained prior shell/navigation evidence rather than rerunning unrelated full suites. New tests were rerun only after additions and the observed clear-route repair.
- `git diff --check` PASS; diff against fixed dependency for ios/Modules/CJAuth is empty. Existing eight pinned dependencies unchanged; new product is the adjacent package's CJSession.

Reproduce with fixed dependency checkout and prior local cache:

```sh
env CLANG_MODULE_CACHE_PATH=/tmp/cj006-clang-cache SWIFTPM_MODULECACHE_OVERRIDE=/tmp/cj006-swift-cache \
  swift test --disable-sandbox --package-path ios/Modules/CJShell \
  --scratch-path /tmp/cj006-host-build --cache-path /tmp/cj006-spm-cache \
  --disable-automatic-resolution --filter LocalSessionHostTests
bash ios/Modules/CJShell/scripts/build-demo.sh /tmp/cj006-session-demo
```

## Bounded simulator observation

Own CJ006-Shell-20261021, iPhone17 Pro/iOS26.5, UDID 824A7623-8882-45C9-94A7-7BD2F758B685, bundle local.cj006.shell.demo. Explicit `--session-demo` visibly labels the memory-only synthetic store; no namespace, Security API call, real credential, provider or network. Existing device reused, no other owner's device touched.

- An initial explicit restore displayed “local material read, server/invitation verification still required”, never signed-in. During cleanup observation the account page popped back to Memory, hiding the result. Fixed by retaining only the public Account route for a user cleanup; external identity invalidation still clears navigation. This preliminary observation is not substituted for final-version screenshot proof.
- Final source `--session-demo --clear-fails`: operated local cleanup; account page remained visible, storage-blocked explanation appeared, Restore and email action were no longer actionable targets. Screenshot clear-failed-final.jpg and corresponding semantic snapshot.
- Final source `--session-demo --restore-unknown`: operated Restore; unknown explanation and reconciliation barrier appeared, no replacement restore/action target. Screenshot restore-unknown-final.jpg.
- Then operated local cleanup successfully on the same host. UI displayed local cleanup completed, explicitly not server sign-out; original reconciliation warning remained and Restore stayed disabled. Screenshot clear-success-unknown-still-blocked.jpg. This directly observes the barrier rather than inferring it from a tool ACK.
- Images were opened and inspected; actual displayed text/targets read back. No token/password value was entered, logged or captured. All three stored images and snapshots correspond to final executable source; preliminary screen is not included. Hashes in session-host/sha256.txt.
- App stopped and device read back **Shutdown**. Prior large-font account/navigation evidence reused; this slice does not claim a new full typography/device/VoiceOver pass.

## Remaining / delivery boundary

Default production path still has no store and cannot restore. Missing-store behavior is directly tested; the existing host uses UnconfiguredSDKAdapter. Restored material cannot grant access: trusted verifier callback has only needsServerVerification/rejected/networkUnknown outcomes. Actual SDK decoding, session export/save, server verification/invitation, durable unknown reconciliation and namespace/entitlement choices remain unconnected. CJ007's real Keychain -34018 FAIL/BLOCKED is preserved, not replaced by injected PASS. No real Keychain/token/provider/physical-device verification and no deployment performed.

Independent review/testing of this new delta remains pending. Contracts and ownership details: contracts/ui/SESSION-HOST.md. No remote push/PR/merge, no client storage expansion beyond injected accepted interface. Whole CJ006 ticket stays open.
