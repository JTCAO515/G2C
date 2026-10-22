# Author repair of Testing's four findings

Parent: `623d40d82124c03e0f8ecffb94fc816946369af2`.
Only CJMemoryClient source/tests/docs change; Auth, shared export, CJShell and
server wire remain untouched. Prerequisite pins from the initial candidate remain.

Original independent report:
`/Users/jtsm5p/Documents/Codex/2026-10-21/cj-testing/CJ-011-ios-memory-client/REPORT.md`.
The Testing source is preserved verbatim in
[testing-original-cases.swift.txt](testing-original-cases.swift.txt).
Before changing implementation, executing those cases on 623 reproduced **4 FAIL,
7 issues** ([repair-before.txt](repair-before.txt)); old 20 PASS is not a waiver.

## Changes

1. Directory identity is rechecked after key/binding callbacks and write/fsync.
   Pending reads recheck after key callbacks and before returning. The POST
   transport validation checks the canonical directory and exact persisted
   original bytes/hash after credential/body suspension, before dispatch, and
   across response processing. Displacement rejects dispatch; no old directory
   or ciphertext is deleted, rewritten or automatically restored. This is callback
   and await-boundary fencing, not immunity to arbitrary simultaneous same-UID
   filesystem attacks or rollback. Production POST remains disabled.
2. Exact op/item/hash/version checks stay. Both authoritative candidate and active
   receipts can settle non-inference actions. Inference still cannot settle as
   active. Candidate UI remains distinct; no historical receipt grants current
   effective-context eligibility.
3. Remote item/operation IDs use the fixed nonblank 1–4096 Unicode-scalar string
   contract, without normalization; detail matching/cursor order stay byte-exact.
   Local pending also accepts opaque IDs and hashes original operation-ID UTF8
   into filenames. Legacy UUID filenames remain readable; duplicate original
   actions cannot be appended under the new format. Confirmed identities use Data,
   avoiding Swift String canonical-equivalence collisions. Local account/binding
   identifiers remain UUIDs and never act as server owner authority.
4. The form now requires explicit approximate-time display text. Empty, whitespace
   and oversized manual fields are rejected before append/credentials/network;
   no timestamp or unknown-time value is filled for the user. Synthetic author
   fixtures now explicitly supply `date unknown` instead of an illegal blank.

## Evidence

- PASS: **29 tests / 2 suites**, including the imported original three behavior
  assertions, the fourth case updated to assert the chosen *reject-before-stage*
  behavior, and five adjacent controls. [repair-after.txt](repair-after.txt).
  The fourth test no longer calls a now-invalid operation without catching its
  error: it requires rejection of blank/whitespace and accepts explicitly supplied
  unknown display text. This follows Testing's allowed repair; it does not relax
  the server requirement or insert fake time.
- Adjacent controls: credential-callback directory replacement sends zero calls
  and retains exact original ciphertext; inference-active rejected; blank/time
  bounds rejected before persistence or credential callback; opaque NFC/NFD IDs
  stay separate plus legacy-file read; normalized-but-different detail ID rejected.
- PASS: iOS Simulator SDK build, signing disabled ([repair-ios.txt](repair-ios.txt)).
  Full local log retained at `/tmp/cj011-repair-ios.log`.
- Exact checked input hashes: [repair-source-sha256.json](repair-source-sha256.json).
- PASS: own diff whitespace/scope checks.

All above are **author regression evidence**, not independent gate acceptance.
No actual account/provider/Keychain/network/App was exercised; no POST gate opened,
no source files outside this module changed, no push/merge/Issue closure. Original
Review/Testing must evaluate the new fixed candidate. App/next-answer/effective
memory and all original real-integration gates remain UNRUN.
