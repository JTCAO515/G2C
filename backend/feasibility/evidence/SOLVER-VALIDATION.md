# CJ-035 bounded CP-SAT + independent output checker: author evidence

Base/previous fixed: e7257ad36f9ecb566f8d6a888f32db2a920a38ef.
Original NEEDS/route/fold fixed points and their FAIL logs remain in history.
Branch cj/035-feasibility; only backend/feasibility + contracts/feasibility changes.
NEEDS/PLACE/root/Trip source, root locks/config and existing 29/route evidence unchanged.

## Actual implementation and dependencies

First business source: cj_feasibility/solver.py. Minimal explicit StartWindow,
Problem, Limits, real CP-SAT model and immutable SolveResult; separate
output_check.py reads actual candidate bytes and public protect/assess_route,
without CP variables/status/internal compiler booleans. No empty solver adapter.
All scope/quantity/time/search bounds are explicit. Selected/unlocked starts may
move; fixed/unselected/unknown-lock content stays pinned. Source-query origin
cannot move beyond that query instant. Output duration, fields, identities,
original endpoints, scoped locks, windows, horizon and routes are rechecked.

Actual runtime: module-local .venv, CPython 3.14.7, OR-Tools 9.15.6755. Actual
native smoke returned OPTIMAL, x=1 (`solver-runtime.txt`). Module-local pyproject
and uv.lock pin the dependency graph; no root dependency/configuration changed.
`solver-dependency-check.txt` confirms all 10 installed packages compatible.
Official primary documentation is linked in contracts/feasibility/SOLVER.md.

Installation issues were real, not hidden: initial uv lock metadata request
failed after three retries (44.5s timeout), then --frozen sync lacked a lock.
Offline attempt lacked cached ortools metadata. A bounded-timeout retry resolved
11 lock entries in 35.25s (`solver-install-retry.txt`). Subsequent uv sync download
made no completion over several minutes and was terminated; its incomplete log is
`solver-install-sync.txt`, not an installation PASS. Direct official wheel GET
showed ~50KB/s and hit 90s at 4,519,958/21,923,649 bytes (curl exit28; tool record).
Final install used bounded parallel HTTP ranges from the **same official PyPI
URLs in uv.lock**, reassembled and SHA256-verified every entire wheel against the
lock, then uv pip sync --no-index into the same isolated .venv. No mirror, version
change, auth/protection bypass or unchecked artifact. `solver-download-verified.txt`
and `solver-wheelhouse.json` retain the exact versions/URLs/full-file hashes.
Those temporary wheel paths are not product/runtime dependencies.

## Test evidence and original failure preserved

`solver-first.txt`: actual first 18 methods = 17 PASS / 1 FAIL. The failure was an
incorrect test expectation: with a latest start giving exactly a 3600-second
route gap, 3600.000001 seconds is correctly unsatisfiable. No solver code was
weakened. Corrected precision test now asserts exact-scale UNSAT at that bound,
then CONDITIONAL_SOLUTION only after explicitly extending latest start by one
minute; scale1 remains UNKNOWN/INEXACT_TIME_SCALE. Original FAIL retained.
`solver-precision-corrected.txt`: affected precision method PASS.

An extra independent original-route-candidate binding check and counterexample
were added before fixing head. `solver-output-binding.txt`: four independent
output methods PASS, including mismatched assessment candidate rejection.
`solver-final.txt`: full **affected new solver suite, 19 methods PASS**. Reran
this new suite after the output checker binding change; did not rerun old domains.

The final 20 methods cover:
- actual native conditional solution, conditional INFEASIBLE and a six-bound
  brute-force oracle independent of CP-SAT variable/order construction;
- 60 minutes cannot fit a pinned 15-minute gap; selected destination can move
  only inside explicit bounds; locked/unselected source cannot move;
- missing duration/buffer remains UNKNOWN, no guessed zeros;
- exact Decimal scaling, integer safety ceiling, whole-second representation,
  extra microsecond boundary and explicit widened window; representation horizon
  never truncates a user window to manufacture infeasibility;
- cross-day/duration preservation, missing/DST-ambiguous input UNKNOWN, and an
  output falling into a wall-time ambiguity rejected independently;
- explicit limits, real pre-search exhaustion, stop before/after search,
  exception/MODEL_INVALID/UNKNOWN status distinctions, no unsat from timeout;
- deliberately altered window/fixed item/duration/description/ID/horizon/record
  or route candidate binding rejected independently, and no native status bypass.
Fault-injected engine states/errors are labeled tests, not native solve proof.

A final model-boundary audit reproduced a real local issue in
`solver-domain-before.txt`: a 1-hour item with explicit start at the 2-hour
representation horizon was incorrectly classified conditional UNSAT because its
end lay beyond the resource domain. Fixed preflight to return UNKNOWN when the
**entire** supplied window+duration is not representable; no silent clipping.
`solver-final-domain.txt`: final affected solver suite **20 PASS** after that fix.
Earlier 19-PASS log and original horizon FAIL are both preserved.

`solver-native-limit.txt`: extra genuine 12-item native search under explicit
1e-9 deterministic budget/max_conflicts1 returned **CP-SAT UNKNOWN**, mapped to
TIMEOUT/BOUNDED_SEARCH_INCOMPLETE, no candidate. No mock in this probe.
`solver-demo.txt`: actual public-type/native consumer shows conditional OPTIMAL,
conditional INFEASIBLE, preparation TIMEOUT and rejected altered candidate. A
trivial model may still solve within a tiny deterministic budget; its actual
OPTIMAL is recorded, not relabeled timeout. All examples retain overall UNKNOWN.
Compileall and staged whitespace check PASS.

## Reproduction

Use an exact PLACE80ba export at PLACE_EXPORT; from repository root:

```sh
uv sync --project backend/feasibility --frozen
PYTHONPATH="$PLACE_EXPORT/backend/place:backend/feasibility:backend/needs:backend/auth" backend/feasibility/.venv/bin/python -m unittest discover -s backend/feasibility/tests -p test_solver.py -v
PYTHONPATH="$PLACE_EXPORT/backend/place:backend/feasibility:backend/needs:backend/auth" backend/feasibility/.venv/bin/python backend/feasibility/solver_demo.py
```

## Conclusions / gates

Source and local synthetic/native OR-Tools + independent invariant behavior:
PASS (author only). Prior accepted NEEDS/route source evidence reused unchanged.
Independent Review/Testing for this new fixed slice PENDING. All real-service,
Auth/provider, database, device, root wiring/Trip writes and complete Issue18 I
acceptance UNRUN; no push/PR/merge/deploy or new authority. Real route/date/mapping,
rest/cost and broader travel condition facts remain UNKNOWN. Only explicitly
supplied start-window, duration/occupancy and applicable conditional route
constraints are solved, not all text/arrival/budget meaning in a NEEDS record.
No overall real-world feasible or proven-impossible conclusion is produced.
