# CJ015 Trip client local validation — 2026-10-22

Historical author validation for `c782339b6c91a80b3d156f59ee7c06b15eb6d50b`.
Subsequent independent Review found two P2 boundaries; this old PASS does not waive
them. Current repair and hashes are in `repair-c782339/REPORT.md`. Product diff base:
`2530a6e77059ee313ae78b114118e59ce1e2384b` (repository base `7b98f00`, followed
by separate fixed dependency preparation `530d32b` and `2530a6e`).
Product changes are exclusively `ios/Modules/CJTripClient/**`.
Fixed source/fixture hashes: `source-sha256.json`; input provenance: `dependencies.json`.

## Actual evidence

| Check | Result | Scope |
|---|---|---|
| Official `Action.raw` fixture | PASS | `check_action_fixture.py` executes public domain code from fixed producer 5fd in memory; exact accept/reject bytes and scoped synthetic proposal hash. No DB/network. |
| Generated Client transport/decoding and client state | PASS | `tests.txt`: 26 Swift Testing tests, 3 suites; parameterized tests additionally cover 5 proposal states, 4 illegal null fallbacks and 3 bad cursors. Official CJAPI Client exchanges with in-process interceptor. |
| Dependency identity/bytes | PASS | 3 imported owner-authored paths and all 16 official generated export files match fixed commits. No rewritten SDK or duplicated package identity. |
| Unsigned iOS Simulator SDK compilation | PASS | `ios-build.txt`, Xcode 27.1 / Swift 6.4, generic iOS Simulator, CODE_SIGNING_ALLOWED=NO. No simulator process/app launched. |
| Diff whitespace / owned paths | PASS | `git diff --cached --check`; product paths restricted to CJTripClient. |
| Public production POST gate | PASS (local) | Reading/displaying proposal cannot enable `choose`; even internal fixture submission on a public live-read client is rejected before network. |

Tests cover actual official generated request bodies and decode behavior; immutable
pending persists before credential suspension, fsync/reopen, repeated clicks with no
new ID, original query after lost ACK, null remaining unknown, reject required null,
invalid oneOf values, wrong receipt hash/version, historical version1 vs current
formal version9, list/detail agreement, pending facts, ASCII C keysets, short-page
continuation, exact next boundary, foreign cursor, terminal/elapsed candidates,
content projection mismatch, duplicate JSON/item IDs and trace mismatch.

Lifecycle/storage negatives cover original CJSession operation replacement even
when host binding is unchanged, credential account switch, same-account proposal
selection, old query success after new identity, old read failure, page response
after refresh, synchronous key callback replacing owner, old pending-click callback,
canceled submission and query, repeated query click, directory replacement during
credential await, key loss, wrong key/namespace, symlink/hardlink and truncated
ciphertext. Storage tests use new task-private temporary directories and synthetic
in-memory CryptoKit material; tests clean their own files. No Keychain calls.

## Failures preserved and fixed

- Initial test compilation failed because a throwing expression was inside a
  Swift Testing macro in a callback. `initial-compile-failure.txt` preserves the
  diagnostic excerpt; moving the read to a local throwing statement fixed it.
  No test execution was claimed for that compile.
- A new cancellation negative actually failed: current UI remained `reconciling`
  because cancellation was conflated with ownership. `cancel-before.txt` is FAIL.
  Ownership checking now permits cancellation settlement only for the still-current
  binding; the UI returns to unknown, and concurrent reconciliation is deduplicated.
  `cancel-after.txt` proves cancellation, another original query and duplicate-click
  suppression. Final full suite in `tests.txt` is PASS; old failure is not erased.

## Unrun and unresolved

- Independent Review/Testing: PENDING; this is author validation only.
- CJShell integration, actual CJ014 candidate/confirmation issuer, real account
  policy, real App acceptance/rejection, App restart on device, SwiftUI rendering,
  Dynamic Type/VoiceOver and physical device: UNRUN.
- Product HTTP, SQL/database, provider facts/model, Keychain, cloud, permissions,
  paid operations, CI, deployment, push/PR/merge/Issue closure: UNRUN.
- Real confirmation issuer and production pending retention/cleanup/anti-rollback
  activation remain unavailable. Public POST stays closed. These tests are not
  server-held real-user confirmation or end-to-end acceptance.
- Internal fixture dispatch uses a synthetic confirmation-reference fixture and
  intercepted server responses. It is not a fake production approval or provider
  verification; formal producer transactions remain the original owner's evidence.
- Entire ledger loss/backup rollback and arbitrary hostile same-UID file races are
  not solved by this local file store. Missing configuration fails visibly; no
  restore/new-key fallback or automatic resend/deletion exists.

Requested model Astra/high; effective model and fast service tier were not independently
verified here. No global model, key, permission or service configuration was changed.
