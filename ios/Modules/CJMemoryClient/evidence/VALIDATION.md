# CJ011 author validation, 2026-10-22

Scope: only CJMemoryClient own package, on prerequisite base
`d7cc48c612326ccd74a5d0fed79cab65a065ee1a`; exact checked sources are recorded in
[source-sha256.json](source-sha256.json). Dependency source hashes remain the
original CJ009 fixed exporter evidence; no independent CJAPI copy exists.

- PASS — `swift test --package-path ios/Modules/CJMemoryClient`: 20 test functions
  including two official whole/fractional date cases. [Full compact output](tests.txt).
- PASS — generic iOS Simulator SDK build of CJMemoryClient with signing disabled.
  [Result](ios-build.txt); complete local output retained at `/tmp/cj011-ios-final.log`.
- PASS — own diff whitespace check and shared-package identity compilation.

Tests exercise five generated operations (including intercepted binary POST),
original nine-key UTF-8/NFD preservation, persisted hash receipt matching,
query-only reopen/null, wrong receipt hash, candidate classification, cancellation
before settlement, actual task cancellation after dispatch, credentials suspension
reentry, account invalidation before dispatch/after response, expired-auth errors,
malformed non-null fallback and duplicate JSON keys, item-ID mismatch, keyset page
termination and cursor ownership, AES-GCM private-file reopen/corruption,
wrong key/key ID/account associated data, exclusive immutable append, missing key,
prewrite binding failure, directory replacement/unknown files, and official
CJMessageKeys Memory purpose/expected ID/invalidation through injected persistence.

The initial no-test build, nullable-container syntax errors and corrupted-file
assertion mismatch were diagnosed and corrected before final checks. Earlier local
logs `/tmp/cj011-build.log` and `/tmp/cj011-tests*.log` remain available; only the
final successful candidate results above are acceptance evidence. The corruption
case now verifies authentication failure and that ciphertext was not overwritten.

UNRUN — live network, real accounts/provider, actual Keychain, app launch/render,
physical device, CJShell container wiring, next-answer effective memory integration,
independent Review/Testing/Publish. These tests and SDK build do not imply those
layers passed. No infrastructure, business data, signed permissions or root wire
contracts were changed. Live POST is unavailable by construction.
