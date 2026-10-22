# activate/load reentry P2 correction

Exact parent b722281001f57cc7bc1c7df8dd38f2543e7dc250. Backend history/draft slice was
committed and its private PG safely stopped before this client-only edit. The client
source at parent is the reviewed 3828e9d content; b722281 changes backend only.

Before: four targeted tests, 2 test methods FAIL (3 recorded issues), 2 PASS;
activation-before.txt. A synchronous storage.load hook activates B then old A returns:
A replaces B's scope/lease. A hook that only invalidates also allowed A to reactivate.
This is local state exposure/identity overwrite, NOT renewed POST permission.

Fix: an independent activationGeneration rotates on every invalidate, including at the
start of activate. Capture it BEFORE storage.load and require equality immediately after
load returns, before snapshot validation/observed-ID registration/scope/lease publication.
A stale call throws inactive without invalidating or replacing the newer lifecycle.
A load exception propagates without touching B; no cleanup of new account is introduced.

PASS: 4 ActivationReentryTests on Swift6.4/macOS (activation-after.txt): callback activates
B, callback invalidates, callback activates B then throws, normal activation/load failure/
subsequent recovery. B lease stays usable, B action visible and A action absent. No actual
Keychain/storage credentials/network. No other suites or PG rerun. Production change is
only six added lines in Recovery.swift; history/draft and transport source unchanged.
Existing anti-rollback rules and live POST prohibition stay intact. Independent delta
review required; not a claim of full Issue10/host/Keychain acceptance.
