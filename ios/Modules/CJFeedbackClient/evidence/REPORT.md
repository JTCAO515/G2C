# CJ023 Feedback client — local candidate evidence

2026-10-22, owner branch `cj/023-feedback-client`, isolated clone
`<local>/Documents/Codex/2026-10-21/cj-023-feedback-client`.
Base **eeb9b9cdf11ff619494a7afd5cbef2833501df7d**. Separate original dependency
preparation commits **888a402** and **c755f9f8bb405e89ff458939ac4608fd52ceb1b8**;
product diff begins at the latter and is restricted to `ios/Modules/CJFeedbackClient/**`.
Final head is the commit containing this report (recorded in owner final response).

Shared module tree `4a7d9656bef41d0e527addcb5829705c9175ab97` equals fixed514e;
AUTH tree `3ba7e7f5390b48ba523342131f25b73c996b4410` equals fixedf2c.
These are preparation only, not Feedback product work. Imported AUTH evidence
includes upstream keychain records; this owner did not run any platform Keychain test.
Sole CJFoundation path in package-graph.json is the official shared201156 export.
Its16 source/package files match shared generated-pin.json. No root or shared lock edit.

Contract inputs read at fixed heads: cf481 FEEDBACK README;201156 formal SDK/API;
81a2 root FEEDBACK-WIRE;514e shared export;f2c key-purpose contract. Original GitHub
Issue15 was fetched read-only (connector returned empty, gh read fallback returned
OPEN). Current Main assignment supersedes its historical planning-status wording;
actual App/I acceptance remains open. No issue changes, push, PR or merge.

Implementation provenance: directory/encrypted pending and strict JSON algorithms
adapted locally from fixed Trip **12df1c1590174ab327d7d01782d736bd20ec199c**, itself
using accepted Memory persistence patterns. The c782 pre-fix lifecycle is not used.
No generic intermediary, second SDK, handwritten wire/date codec or key provider.

## Commands and results

Toolchain: Xcode27.1 (27A9275), Apple Swift6.4. iOS17/macOS14 module minimums.
Working directory is clone root except xcodebuild (module directory).

1. `python3 ios/Modules/CJMessageClient/scripts/prepare_generated.py <local>/Documents/Codex/2026-10-21/cj-005-foundation`
   PASS: existing script exported16 unchanged official files. This ignored export
   is not another generated source tree committed by this module.
2. `swift test --package-path ios/Modules/CJFeedbackClient`
   PASS final: **33 functions /60 expanded cases /5 suites**, tests-final.txt.
3. A stronger general-null negative case was then added: syntactically valid linked
   source supplied for general feedback (instead of malformed source). Targeted
   `swift test --package-path ios/Modules/CJFeedbackClient --filter FeedbackClientTests.malformedReceiptRejected`
   PASS9 variants in general-null-targeted.txt. No production behavior changed;
   only provenance comment and this test changed after full suite/iOS build.
4. `xcodebuild -scheme CJFeedbackClient -destination 'generic/platform=iOS Simulator' -derivedDataPath .build/ios-unsigned CODE_SIGNING_ALLOWED=NO build`
   PASS unsigned arm64/x86_64 module compile, including SwiftUI view/previews.
   No simulator boot, render, launch, device or signing. See ios-build.txt and lossless
   ios-build-full.txt.xz (original SHA256 recorded in summary).
5. `swift package --package-path ios/Modules/CJFeedbackClient show-dependencies --format json`
   PASS: one unique CJFoundation package location, shared official201156 path.
6. Diff whitespace, source hashes, exact dependency tree equality and exported
   file hashes checked before commit. source-sha256.json captures final source/tests/manifest/lock.

## Risk-directed coverage

- Actual official Client POST/GET intercepted in-process: exact original octet bytes,
  minimal action keys, no owner/diagnostic fields, actual path/query, credential injection,
  persisted feedback hash, source-null vs linked and whole/fractional UTC decode.
- Canonically equivalent but byte-different Unicode refs, wrong action/hash/message/run,
  message hash substituted for feedback hash, missing/additional/duplicate response keys,
  required null and invalid generated oneOf fallbacks all reject.
- Unsupported run-only/Trip/Memory/proposal/duplicate refs, bad text/IDs/byte limits.
- Lost ACK then new client/opened encrypted store: only original query, no repeat or
  new-ID POST; null/non-null fallback/error/cancel never releases unknown.
- Environment/account/generation/selection transition before/after callbacks/await,
  same-binding credential/key/current-binding reentry, client-instance mismatch.
- Opaque UI work captured before Task: queued old submit/query cannot act on new
  selection; same-binding key/binding callback reentry cannot publish/clear new state;
  duplicate work is one-shot; cancellation/missing binding never leave busy hanging.
- Final key and final binding callbacks replace canonical directory or original
  ciphertext before outflow; after response replacements also withhold confirmation.
- Canonical provider through injected persistence with original Feedback purpose/key;
  wrong account/environment/purpose/key, absent/unknown/unknown-create are unavailable
  without extra create/delete/network. AES-GCM reopen, exclusive append, symlink and
  hardlink defenses, no plaintext body in ciphertext.
- 409 keeps problem, expectation and immutable recovery record; original query null
  remains unknown. Public production constructor cannot POST, even with synthetic
  current SessionLifecycle and local resources; credential callback remains uncalled.
- Synthetic private transport exception becomes only exchangeUnknown. No log calls
  in production sources. No transcript prefilling or inferred model/tool facts.

All test bindings, endpoints (.invalid), tokens, records and persistence are explicitly
synthetic. Nothing here verifies ownership of an actual user's message/run. Server-side
real ownership enforcement and cross-domain read-time semantics remain upstream gates.

## Preserved failures

- first-build.txt: core compiled; swift test exited nonzero because tests had not yet
  been authored (“no tests found”). Not a test PASS.
- tests-first.txt: first8 functions passed, before lifecycle coverage existed.
- lifecycle-first.txt:25 functions ran; one conflict UI assertion FAIL. Test409 body
  omitted official ErrorInfo.category/outcome, so generated Client rejected decoding
  and client correctly classified exchange unknown. Fixture corrected to formal schema;
  assertion was retained. Final run passes this test. No failed log deleted/rewritten.
- Initial staging included local .build because the root ignore only covers ios/.build.
  Removed these entries from the index without deleting build evidence; added this
  module's own .gitignore for .build/.swiftpm. No build artifacts/submodules committed.
- Official generated SDK emits unused-public-import warnings; no generated files edited.

## Boundaries and remaining work

Author code/targeted tests/unsigned module compile: PASS as scoped above. Independent
Review/Testing: PENDING; upstream key/wire/shared-export gates remain separate. App
combined package integration and both actual Answer/Memory entrypoints: UNRUN, owned
by CJ006. Preview/render/accessibility/keyboard/device acceptance: UNRUN. Real account,
Keychain, live HTTP/SQL/provider/model/tool results, signing, deployment and release:
UNRUN. No PG was started and no old server/domain suite was repeated. Public POST
remains disabled. Server model/rule versions, duration, usage and tool results are
not supplied by this contract; UI does not infer them. Cleanup/retention is not integrated.
Original Issue15/I remains OPEN; no claim of repaired/trained/operator-delivered feedback.
