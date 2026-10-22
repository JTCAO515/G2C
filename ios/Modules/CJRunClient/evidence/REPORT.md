# CJ-010 scoped client author evidence

2026-10-22 Asia/Shanghai. Candidate is the product commit containing this report;
source hashes are in `provenance.json`. Worktree `cj-010-run-client`, branch
`cj/010-run-client`, base000b6d4. Dependency prepc4e59dc is separate and remains
CJ009-owned bytes (540da02 export, official c02 inputs). No source dependency edits.

PASS — macOS Swift 6.4 targeted suite: 19 test functions / 54 cases. Full final output
`tests-final.log`. Actual official generated Client uses an in-process transport;
SessionLifecycle uses in-memory synthetic persistence. No actual credential or
Keychain access. Tests cover:

- Seven status/partial/complete pairs, exact Unicode, actual empty queued body,
  event highwater distinct from message sequence, server trace and exact GET query.
- Every original reference mismatch, Unicode canonical-equivalent ID mismatch,
  missing fields/snapshot, null, malformed JSON, duplicates, extra fields, unknown
  enums, wrong complete/partial pair, bool/negative sequence and inconsistent queued.
- Missing/mismatched trace, absent/cacheable header, redirect; generated BASE
  401/413/503/429 errors (synthetic), exact byte limits; no retries or fallback answer.
- Single-use prepared work, duplicate snapshots, increased complete snapshot,
  lower/equal-conflicting/non-prefix/terminal-revival snapshots.
- Selection/background/session/source invalidation before queued work; credential
  callback replacement; reentrant prepare/select; late transport callback changes;
  cross-model and different-message work rejection; task cancellation; session clear
  and already-loaded source invalidation. New selections survive old completion.
- Redacted value/state descriptions; meaningful English and Chinese labels.

PASS — unsigned iOS simulator module build via xcodebuild, Xcode27A9275 /
iPhoneSimulator27.1 SDK, deployment target17 (local package baseline, not product
minimum). arm64 and x86_64 outputs compiled, **BUILD SUCCEEDED**. No app launch,
simulator interaction or device runtime is implied. Product source was unchanged
between this build and final tests (only additional test cases were added).

PASS — fixed export16 files match exact rootc02 blobs; prep3 files match CJ009540
blobs; all11 resolved dependency revisions match existing base CJShell lock pins.
`git diff --check` passed; changes outside this module are only the prep3 paths.
No unrelated tests were rerun. No API/schema/root SDK/AUTH/other client/CJShell edits.

Initial SwiftPM dependency resolution encountered a swift-collections cache update
SSL error, then fetched successfully. This is preserved in raw first-build.log;
no credentials/config changes or lock upgrades were used. Two initial overlapping
SwiftPM invocations serialized using its built-in lock and both finished successfully.
Final targeted suite ran after the new cases. Generated dependency unused-public-import
warnings are preserved; no generated files were edited to suppress them.

Raw build/initial-test logs remain in `.build/author-raw/`; hashes and sizes are in
provenance.json. Concise iOS result is in `ios-build-result.txt`. No known failed
product assertions were discarded. Public trace validation does not prove server
provenance when using an interceptor.

UNRUN — real HTTP/PG/Auth/provider/worker, physical device, accessibility interaction,
CJShell/CJ006 integration, full App unified package graph, streaming/server stop,
Issue11 I acceptance, CI/deployment/release. Source root's separate PG/HTTP evidence
is not claimed as this client run. Review/Testing are pending existing owners.

Next: Main routes this fixed candidate to original Review/Testing. CJ006 may then
consume the documented public model/source/view after Main assigns its own exact
scope. No public-interface blocker found. Do not push, merge or enable writes based
on these author results. Model requested Astra high/default; effective UNKNOWN.
