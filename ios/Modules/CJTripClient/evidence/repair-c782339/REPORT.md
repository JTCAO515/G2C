# c782339 two-P2 repair — author evidence

Repair base `c782339b6c91a80b3d156f59ee7c06b15eb6d50b`; repaired head is the commit
containing this report. All changed paths remain in `ios/Modules/CJTripClient/**`.
Original product/dependency bases and fixed owner inputs remain unchanged.
Independent Review/Testing of this repair is PENDING, not author approval.

## Actual before/after

Original reviewer source/report:
`<local>/Documents/Codex/2026-10-21/cj-review/CJ015-client-c782339/`.
`original-replay-before.txt` reruns that fixed reviewer executable against a fresh
module-private synthetic directory and the original fixture. It reproduced all
three reported observations: old accept click queried reject, reentrant newer
reject selection was overwritten by accept, and the last binding callback displaced
storage yet one generated POST escaped (canonical reopen0; displaced ciphertext1).
The original executable exits0 while printing FAIL for these expected reproductions;
exit0 is not a successful boundary check. The displaced synthetic records remain
under the module's ignored `.build/repair-probes-*`; no recovery/restoration occurred.

Two setup attempts are also preserved: an already-existing runner target and a
Foundation temporary-path `storageUnavailable` result. Neither exercised the full
reproducer; the successful local-directory invocation above is the reproduction.

`regressions-before.txt` runs three assertions against unchanged c782 product
sources and actually fails all three. `regressions-after.txt` passes those three
assertions after repair. Full affected local package `tests.txt` passes34 tests in
4 suites: the original26 are retained (presentation calls migrated to the opaque
work API, assertions retained), plus8 new boundary/adjacent tests. The older
cancellation FAIL/PASS and all old evidence files remain preserved.

## Repair

1. Synchronous `prepareProposal`, `prepareTrip`, `prepareTrips`, and
   `prepareReconciliation` capture immutable original work **before Task creation**.
   `TripPresentationWork` has no public constructor or mutable fields, and includes
   presentation owner, lifetime, binding, per-lane selection/request token and exact
   target/action/cursor. `perform(work)` checks and claims that original once;
   duplicate work cannot dispatch. New same-binding selection, refreshed list,
   another owner or replaced lifetime rejects old work without affecting new UI.
   All asynchronous buttons now use this API. No legacy no-origin async method
   remains in production; CJ006 must use the public prepare/perform pair.
2. `selectPending` rotates the proposal selection token before reading storage;
   `loadPending` has its own request token. Both recheck after resource callbacks.
   A nested newer selection survives an older outer completion or exception.
3. `requireOriginal` authenticates the frozen record and captures its exact encrypted
   bytes. After the final binding callback, `validateDurability` rechecks canonical
   directory identity, original filename/metadata and ciphertext bytes with **no key,
   host callback or await**. This final fence also precedes receipt settlement.
   It rejects both complete directory displacement and removal of only the original
   file while leaving the directory unchanged. Displaced bytes are preserved; no
   automatic restoration, new key, resend or cleanup was added.

Adjacent tests cover queued detail selection, one-use work, foreign presentation,
queued keyset page after refresh, queued reconciliation after lifetime replacement,
new same-account selection followed by old key failure, and original-file-only
removal at the final callback. The original three regression tests use the actual
shared official generated Client and encrypted pending store, with intercepted
transport; their after assertions require **zero outbound requests** in stale or
non-durable cases and retain the new selection/displaced ciphertext.

## Validation / limits

- PASS:34 local Swift Testing tests, including all26 original tests and8 repair tests.
- PASS: unsigned generic iOS Simulator SDK build (`ios-build.txt`); no app launched.
- PASS: exact fixed Action.raw fixtures and dependency checks are unchanged/reused.
- PASS: scoped diff whitespace and new source hashes (`source-sha256.json`).
- Public real POST remains unavailable. No backend, wire, generated SDK, key provider,
  CJShell, shared package or lock was modified by this repair.
- No PG, real Keychain, product HTTP, real account/confirmation, provider, device,
  rendered UI, CI, deployment, push/PR/merge or Issue closure.
- The last callback fence does not claim atomicity against arbitrary hostile
  same-UID filesystem mutation, process races or backup rollback. Real confirmation
  issuer/account policy/storage activation are still absent, so no live activation.
