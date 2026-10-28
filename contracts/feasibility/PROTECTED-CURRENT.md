# Protected current NEEDS evaluation entry

`CJ-FEASIBILITY-PROTECTED-CURRENT@0.1.0-rc.1`, after CJ035
`af52cbdfadf06cc79d511b6c1b06f756a1896594`. Internal host-composition candidate,
not a registered HTTP API/root factory. This consumer's independent gates pending.

## Fixed public input and surface

NEEDS `4cc9c815293a4e03225b26adfa228fdd0b50b2e7`, public
`CJ-NEEDS-PROTECTED-READ@0.1.0-rc.2`, as specified by its original owner in
`contracts/needs/PROTECTED-READ.md`. Required AUTH remains exact
`8b6abb236cf10c1865a9cc8c6155bd8ac732c07e` and its canonical protected read boundary.
Main supplied producer Review/Testing PASS; this report proves consumer behavior,
not independent re-performance of producer's review or full 33-case suite.

```python
from cj_auth.read_context import ProtectedReadBoundary
from cj_needs.protected_read import ProtectedReader, ReadConfiguration
from cj_feasibility.current_read import ReadLimits
from cj_feasibility.protected_current import CurrentNeedsRead

# Explicit trusted host composition; not request fields or an allow callback.
auth = ProtectedReadBoundary(canonical_checker, max_response_bytes=auth_cap)
reader = ProtectedReader(auth, approved_host_resolver,
    configuration=ReadConfiguration(environment, issuer, audience, producer_cap))
entry = CurrentNeedsRead(reader, ReadLimits(max_revisions, max_input_bytes, projection_cap))
raw = entry.read(original_token, explicit_needs_id)
```

Only token and needs_id are request-selected. No owner, scope, resolver,
environment, snapshots/history, candidate, projector or result cap is accepted
by the entry's read method. Host limits and reader are immutable facade fields.
Since producer rc.2 the reader captures its configuration once per read; host
configuration replacement affects only later reads and is not fenced mid-read.
`CurrentNeedsRead()` has no resolver/reader/limits and refuses before IO.
No root route, factory registry, token storage, service defaults or new authority.

The facade supplies only its fixed `project_current` callback to actual
`ProtectedReader.read`. Original projector is byte-unchanged from af52: same
Snapshot/revision reads, exact history/evaluate validation, limits, complete
immutable bytes, operation/context principal binding and final current Snapshot
reread; fresh canonical AUTH at entry and before bytes escape comes from the
enclosing ProtectedReadBoundary; the projector no longer repeats
context checks around each read (#186).
The facade returns the exact producer-returned bytes. No IO, extra encoding,
projection/provider callback or second auth wrapper follows producer settlement.
The evaluator still reports only local CONFLICT/UNKNOWN and overall UNKNOWN.

## Original two failures: current status (rc.2)

Original af52 FAIL log `current-read-seam-fail.txt` is preserved byte-for-byte.
The new integration does not patch legacy Boundary or suppress those failures.

- Ordinary close failure: still rejected. An actual test PG connection closes,
  then raises an ordinary exception; the read is withheld with exactly one
  connection opened/closed and no bytes (strict close is unchanged in rc.2).
- Trusted resolver scope remapping, or configuration replacement, on first close:
  **no longer checked** since producer rc.2. Host composition is trusted and is
  resolved once per read; the rc.1 tests for these were removed (#186). The
  supplied-environment rule for the resolver is unchanged.

## Final byte and identity lifetime

Projector output cap, producer ReadConfiguration cap and outer canonical AUTH cap
all apply to the fully encoded result; none is bypassed or replaced by a caller
flag. Correct owner can read the actual version2 record/full original history;
missing/other owner shares a safe refusal. Missing history or advancing current
version after historical reads is withheld. There is no domain write by evaluation.

A test arms revocation only after the fixed projector returned complete bytes; the
next admission is the canonical AUTH final check, and it rejects. Configuration
mutation during that callback is no longer compared (rc.2, #186).
These tests inspect only public configuration and test identity hooks; no private
repository fields/transaction state or copied producer algorithm in runtime code.

The result here is just an internal evaluation byte projection, not a Trip write,
confirmation token, real feasibility proof or resource transaction receipt. Inputs
and output are private read-lifetime data; this module adds no persistence.

## Validation and reproduce

`protected-current-first.txt`: 11 targeted new integration methods PASS.
`protected-current-final.txt`: final 12 PASS including current version advance.
Each run creates a NEW empty private PG17 cluster, Unix-only socket/explicit DSN,
canonical AUTH + actual fixed NEEDS readers, synthetic accounts/content. Both
clusters are stopped and preserved with STOPPED/postmaster.pid-absent evidence.
Original af52 consumer12, solver20 and route evidence are reused, not repeated.
No original NEEDS/AUTH/producer/root/SQL changes or copied DTOs.

Let INPUT_EXPORT contain exact NEEDS4cc9 + AUTH8b, from repository root:

```sh
PYTHONPATH="$INPUT_EXPORT/backend/auth:$INPUT_EXPORT/backend/needs:backend/feasibility:backend/feasibility/tests" PYTHONDONTWRITEBYTECODE=1 <local>/Documents/Codex/2026-10-21/cj-013-needs/backend/needs/.venv/bin/python -B -m unittest test_protected_current.ProtectedCurrentTests -v
```

Existing CJ013 Python/psycopg runtime is used read-only with -B; no dependency
installation or source write there. Tests reuse fixture setup functions only;
none of old PrivateReadTests methods is inherited/run by this new test class.
Input hashes, actual tested files and private cluster settlement are in
`protected-current-input-manifest.json` and PROTECTED-CURRENT-VALIDATION.md.

Local author integrated entry PASS; own independent Review/Testing pending.
Root registration/public access remains closed until those gates and original
root owner wiring. Actual JWT/account/provider, production DB/RLS, App/UI,
overall real feasibility and Issue18 I acceptance remain UNRUN. No push/PR/merge,
deployment, credentials, new permission or formal Trip write.
