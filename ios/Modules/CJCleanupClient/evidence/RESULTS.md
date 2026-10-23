# CJ024 cleanup client — author evidence

2026-10-23 Asia/Shanghai. Source commit **aa5368ef4b0f551a464cb44a761d0f46608d4759**;
base **b33184fdc14c55098f2f21cd7e33d05b8a5d01f0**.
Final evidence commit is the branch HEAD; its source matches this fixed commit.
Only `ios/Modules/CJCleanupClient/**` is changed. No push/PR/merge or external message.

## PASS — bounded local implementation

- Official typed original-operation GET, one consumption per explicit preparation.
- Current account/environment/canonical SessionOperation/request generation binding;
  pre/post await and callback fences, local cancel/dismiss invalidation, stale state
  clearing, old success/error unable to replace a newer loaded projection.
- Bounded whole response and steps; no truncation or numeric completion estimate.
  Strict JSON/duplicate-key and official generated shape/enum validation. Limited
  frozen-operation completion text in both languages, no all-data deletion claim.
- Explicit nondefault NoRedirectTransport and current credentials injection only;
  no factory/CJShell/backend/API/shared changes, no new persistence/Keychain path.
- Immutable fixed shared export (65 files, source SHA256 verification), official
  f87 SDK only. `dependency-pin.json`, `inputs.json`, `package-graph.json` and
  `single-sdk.txt` record reproducible provenance and one path for each shared
  CJFoundation/CJMessageClient/CJAuth identity. No hand-written second wire SDK.

## PASS — actual author verification

- `tests-final.txt`: **19 Swift Testing functions passed**, in-process intercepted
  transport and no-secret SessionPersistence fixture only. Includes original GET,
  repeat ticket consumption, blocked/unknown/in-progress/failed/scoped-complete,
  malformed/extra/null/duplicate/unknown wire, wrong operation, invalid numeric
  revision, response/step budget, cache/request-id, 401/403/404/503/redirect,
  missing config/invalid original ID, credential callback switch/logout,
  late response/error, same-user new session, environment/owner mismatch,
  actual Task.cancel with noncooperative transport, callback reentrancy,
  newer loaded generation preservation, loaded state logout clearing,
  UTF-16/32 duplicate-key rejection and bilingual labels.
- `ios-compile-final-pin.txt.gz`: **BUILD SUCCEEDED**, generic iOS Simulator,
  code signing disabled, final Package manifest and source. No simulator boot,
  App install/launch, rendering or device access. Earlier compile logs retained.
- Fixed dependency export/hash preflight rerun PASS without modifying export bytes.
- Package graph PASS: 15 unique identities, one f87 CJFoundation; canonical host
  dependencies are siblings. Verification-only build switch selects local fixed
  exports within this lease and must be unset for eventual host integration.
- Own source/staged diff and whitespace checks PASS. Source file SHA256 and complete
  delivery file list in `file-manifest.json` (manifest itself excluded).

## Preserved failures and corrections

- `first-build.txt.gz` / `tests-1.txt.gz`: FAIL, missing `try` for generated response
  body's throwing accessor. Corrected; `tests-2.txt` has initial 12 PASS.
- `tests-3.txt`: 16-test run FAIL on precise redirect classification, because the
  OpenAPI runtime wraps a transport error in ClientError. Corrected by retaining
  only its safe typed CleanupFailure, never the request/bearer-bearing error.
- `tests-18.txt`: 18 PASS after that correction. `encoding-before.txt`: new encoding
  negative already PASS; explicit UTF-8/root-object parser guard was then added
  as defensive hardening. Final 19 PASS and final iOS build cover the change.

## Pending / UNRUN / UNKNOWN

- Producer 514/663/root f87/shared507 independent Review/Testing/Publish gates are
  separate and pending as delegated. This candidate does not admit them.
- Own independent Review/Testing, remote CI, merge, production activation: UNRUN.
- Host App wiring, accepted original-operation source, accurate current binding /
  synchronous invalidate calls, common f87 host package graph: not integrated.
  Until trustworthy provenance/config is available, unavailable is intentional.
- Real account/AUTH/API/network/PostgreSQL cleanup, provider/fees, actual revocation,
  hooks/destructive actions, backup/offline/external retention and true end-to-end:
  UNRUN. No real bearer, Keychain or account touched.
- UI rendering/interaction/VoiceOver/device acceptance: UNRUN. This is a compiled
  SwiftUI component, not an operated App or product acceptance.
- Postlogout restricted progress capability is undefined/closed; no credentials or
  permission recovery added. Issue #27 whole acceptance/I dependencies remain open.
