# CJ-022 one-attempt reentry repair

Fixed repair base: `294204087d855f44f341ec9d8ea56b2b48354e97`. Candidate head is the commit containing this report. The old294 combination remains HOLD until independent revalidation; this report is author evidence only.

## Reproduction

Original independent probe copied byte-for-byte from cj-testing/CJ-022-accepted-source-consumer/snapshot/ios/Modules/CJOfflineTrip/Tests/CJOfflineTripTests/IndependentAcceptedSourceAttemptTests.swift. Both copies SHA256: `48ba1edba86945c0ef5af7df78bcfd7a7b444ad6d5b02218e62332cb84e66351`.

Ran the exact probe against unchanged294 implementation before the repair. `reentry-reproduced-fail.log` records the same three failed assertions: two successful receipts, two rename commits, and old outer ciphertext replacing the already committed nested ciphertext. There was one getTrip and zero key adds/removes. Original independent report/log remain untouched in Testing's workspace.

## Minimal repair

Only product change: reserve `attempted = true` before `validateOriginal()` invokes Trip's external currentBinding callback. The reservation is permanent even when source validation fails. Nested writeOnce sees the reservation and rejects before source validation, canonical key lookup, seal/nonce generation or file mutation. No reset/defer/cleanup can release another attempt's ownership. Pending-unknown check stays first, ahead of reservation/key/nonce; original ciphertext reconciliation is unchanged.

No Trip producer, AUTH, canonical key adapter, codec, file-store primitive, policy, App factory, SDK input, Package or lock changes.

## Actual checks

PASS: `reentry-fixed-tests.log`,13 selected functions in3 suites:

- Exact independent probe now passes: one receipt and one commit; nested write denied.
- Added failedSourceValidationKeepsReservationAcrossReentry: validation callback reenters, nested call is denied, then original source retires; outer fails and cannot retry. Zero key lookups, zero commits, no cache bytes.
- Existing9 accepted-source combination functions, including unknown-write blocking/original-byte reconciliation, final callback replacement and source/session/await retirement, pass.
- Existing2 canonical reentry/unknown-write controls pass.

PASS: unsigned iOS simulator-target module compile (`reentry-fixed-ios-build.log`); no simulator run/install or device result. `git diff --check` PASS. Old codec9/canonical9 and producer/key evidence are reused at unchanged scope, not rerun as unrelated suites. Original failures remain retained.

No real Keychain, account/data/cache, offline authorization/production TTL/trusted time, CLEANUP, App/UI, formal POST, provider, CI/deployment or full Issue24/I acceptance. No push/PR/merge/deploy. Await original independent Review/Testing on the new fixed candidate.
