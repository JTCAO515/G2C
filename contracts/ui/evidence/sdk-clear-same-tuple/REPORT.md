# CJ006 same-verification clear counterexample and typed interface gap

Status: **HOLD / reproduced FAIL**, not a production fix. Starting clean1179933617db0245deaed04c889fb528e35b5aaa; Memory40cc/cd09 and Trip3f51/1179933 are preserved. Source AccountHost remains480 behavior. Trip dependencyc782 separately remains HOLD.

Independent input: `cj-testing/CJ-006-clear-lifetime/REPORT.md` and same-verification.log. The old Review harness exits0 while printing FAIL; its printed assertions, not exit alone, are decisive. Author reproduction instead uses Swift Testing and exits1 with two explicit failed host assertions (`before.txt`).

Only changesVerification=false was added to the existing actual SDK replacement test. Seed original A bytes, call host clear; persistence callback performs canonical nested lifecycle.clear → beginTrustedSDKSave → official SupabaseSessionBridge save of B with distinct synthetic token bytes. Keep the same verifier generation/user and shell generation. B's exact bytes, .saved state and new current operation pass; old host publishes blocked(staleOperation), so restore/account submission become false. ChangesVerification=true still passes. Same-original storageUnavailable/staleOperation-named failures remain blocked; normal clear remains cleared even though its previous token retired. No fixture success is substituted for an actual canonical save.

## Minimal canonical consumption gap for Main / CJ007

`SessionLifecycle.clear()` currently allocates its clearing generation internally, calls external persistence, and uses its private generation/current comparison to distinguish original vs displaced completion. Its public surface collapses displaced clear into `SessionFailure.staleOperation`, the same public value a genuine same-original persistence failure may carry. All prior operations normally retire on clear. Trusted verification tuple equality does not prove clear ownership.

Request an additive public typed clear-settlement operation (final naming belongs to CJ007) with three semantic results:

1. Original clear completed successfully.
2. Original clear failed, carrying canonical SessionFailure.
3. Original clear was displaced by another lifecycle operation.

Classify inside the existing lifecycle around the same persistence callback using its already-owned clearing generation/current checks; do not expose private generation or create host authority. Keep existing `clear() throws` behavior/source compatibility for other callers. The proposed result is settlement evidence only, not credential validity, new-session adoption or permission. A replacement can share both verifier fields and can itself end blocked; public state/error snapshots therefore are not a general original-clear ownership substitute.

CJ006 will consume the fixed public outcome under its existing shell/verification guards: only success clears local status, only original failure blocks, displaced result retires old UI bookkeeping without mutating/adopting replacement storage. Do not stage consumer code against a guessed signature. Owner validation should include same-tuple saved replacement, replacement with a failure state, ordinary success and genuine same-original failures (including staleOperation name). This is a proposed minimal interface need, not a claim it exists or has been accepted.

Authorized preparation is complete: exact reproduction, preserved negative log, current API source trace, narrow regression delta. Dependent AccountHost repair awaits CJ007's fixed public typed evidence. No domain source edits, Keychain, real account/provider/network, device, signing or permission change occurred. Existing load/pin/27 positive evidence is retained; this new counterexample prevents blanket host PASS.

Command: established local caches, `swift test --disable-sandbox --package-path ios/Modules/CJShell --scratch-path /tmp/cj006-sdk-host-build --cache-path /tmp/cj006-spm-cache --disable-automatic-resolution --filter IndependentSDKHostClearTests`.
