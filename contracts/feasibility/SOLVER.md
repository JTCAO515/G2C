# Bounded conditional CP-SAT candidate

`CJ-FEASIBILITY-BOUNDED@0.1.0-candidate.1`, CJ-035 / Issue 18. Local owner slice
after `e7257ad36f9ecb566f8d6a888f32db2a920a38ef`. No domain writes or authority.
Source: `backend/feasibility/cj_feasibility/solver.py` and `output_check.py`.

Uses the actual OR-Tools CP-SAT implementation. Official primary references:
[integer constraints and solver states](https://developers.google.com/optimization/cp/cp_solver),
[search limits](https://developers.google.com/optimization/cp/cp_tasks),
[upstream solver guide](https://github.com/google/or-tools/blob/stable/ortools/sat/docs/solver.md),
[official installation](https://developers.google.com/optimization/install/python).
CP-SAT's integer requirement is handled by exact rational scaling; a stopped or
limited search is not an infeasibility proof. Dependency/lock is module-local;
no root dependency/configuration or provider is involved.

## Explicit inputs, narrow meaning

```python
from threading import Event
from cj_feasibility.solver import Problem, StartWindow, Limits, solve
from cj_feasibility.output_check import verify_output

outcome = solve(problem, limits, stop=Event())
check = verify_output(problem, explicit_candidate, limits)
```

`Problem` retains the original NEEDS Snapshot/revision tuple, the pre-write
Candidate, exact selected_fields/item_ids, explicit StartWindow tuple and actual
RouteAssessment tuple. No other domain model is copied. `StartWindow(item_id,
earliest,latest)` is this owner's minimal internal candidate: inclusive **aware
instant** bounds on that existing item's start. It is not a Trip schema or wall
date inference. Mapping a future draft type to it remains consumer work.

All existing items must have unique known start/end instants and known booking
status. DST ambiguous/nonexistent/missing date/time/zone is UNKNOWN. Duration is
the original candidate's exact elapsed end-start and must be preserved. This
slice schedules the existing item set; it does not add/delete/reorder items,
choose places, change duration, infer costs, translate conditions, or create a
full travel plan. Other NEEDS arrival/departure, budget, pace or condition text
is retained but not implicitly compiled into constraints: callers must supply
explicit applicable start bounds; unmapped broader meaning remains UNKNOWN. Shared-subject active appointment/transport occupancy uses
the already accepted deterministic declaration rule; hotel/intent overlap is
not invented into exclusive occupancy. Cancelled items are not treated as active
occupancy. These are user declarations, not verified supplier facts.

Only explicitly selected items whose original and candidate lock observations
are both known false may move. Such items **require explicit start windows**.
Others are pinned to their exact original candidate instants, including unknown
locks; a supplied window cannot relax a pin. Initial public `protect` must pass.
Start windows on fixed/unselected items may prove the supplied constraints
inconsistent, but never grant movement. No selection expansion or token is made.

## Exact quantities, original route applicability

PLACE remains fixed at `80ba4ae5527875ce375d22f3439f8e3256e2c4d6`. RouteAssessment
is retained whole with original Result/Source/query/IDs/roles/GCJ02/times/policy.
The compiler **re-runs public assess_route** on original objects rather than
trusting a caller-edited assessment status or numeric details. Unknown route,
duration, buffer/rest, source, freshness, endpoint/time binding or applicability
blocks that dependent search with UNKNOWN; no zero or guessed provider value.

Each supplied route imposes the exact estimate+explicit buffer+explicit rest gap.
Since current PLACE supports only at-query-time estimates, that route's origin
start is also pinned so origin end remains the original query instant. Moving it
would extrapolate a route estimate to another departure and is not supported.
Only the destination or other selected items can shift within explicit bounds.
Synthetic/unverified categories remain visible; even a checked solution has
**overall UNKNOWN** and is never a real travel feasibility claim.

NEEDS event times represent whole seconds. Decision start instants therefore use
whole-second positions relative to an explicit UTC-normalized epoch. Durations
remain whole seconds; original timezone/place declarations are retained. Decimal
route/buffer/rest amounts are converted through `Decimal.as_integer_ratio()` and
integer divmod at the explicit ticks_per_second. Every component must scale
exactly; no rounding, float conversion, or hidden zero. Fractional amounts can
constrain whole-second starts exactly (e.g. 3600.000001 requires a gap strictly
larger than 3600 seconds). Unrepresentable precision is UNKNOWN/INEXACT_TIME_SCALE.

All absolute tick bounds are explicit and at most 2**60-1, a conservative CP-SAT
integer-expression safety ceiling, **not a travel/business horizon policy**.
Horizon*scale and each component/sum must fit. Every entire supplied start-window
range **including preserved duration** must fit the representation horizon. A
resource horizon refuses an unsupported problem with UNKNOWN; it must not truncate
user windows and manufacture an UNSAT result. Larger/inexact inputs are refused
rather than overflowing or changing a hard constraint.

## Explicit bounded execution

`Limits` has no defaults: epoch, horizon_seconds, ticks_per_second, max_abs_ticks,
max_items, max_edges, max_revisions, max_solve_seconds, max_deterministic_seconds,
max_conflicts. Values are checked before constructing CP-SAT. Existing NEEDS
field/byte/list bounds also apply. The minimal adapter uses exactly one native
search worker and one feasibility search, no objective, retry or enumeration.

Wall budget includes preparation/import/model construction and post-check phases;
remaining time is passed to CP-SAT with explicit deterministic/conflict limits.
Budget is checked at phase boundaries; it is not a hard OS process kill or memory
sandbox. `stop` is an explicit threading.Event, checked before/after phases; an
in-progress native call is bounded by remaining search limits, then its output is
withheld if stopped. No unbounded callback, background monitor or provider call.
Embedding hosts must enforce any stronger process/memory isolation separately.

## Independent output check and results

Before publishing a candidate, `verify_output(problem, candidate, limits)` reads
actual original/output field bytes. It imports **no CP-SAT** and receives none of
the compiler's scaled domains, movable booleans, order variables or solver status.
It verifies original route-candidate binding, invokes public protect again;
compares identities/order, non-time fields,
timezone/place, preserved durations, original lock/selection scope, horizon and
explicit start bounds; directly compares applicable interval overlaps; and
re-runs public assess_route against the **output**. Each route must return the
conditional within-gap relation. Changed origin/future applicability or any
ambiguous local output is rejected. No simulated revision/user source is created.

Conversion back to local wall time never chooses a fold for an ambiguous NEEDS
output: if the existing field model cannot express a uniquely checkable instant,
the independent check rejects that candidate and returns UNKNOWN. This slice
does not retry with a guessed fold or rewrite source semantics.

`SolveResult` retains Problem/Limits, stable status/reason, native status when
available, optional independently accepted Candidate/Verification, same-decision
Chinese/English explanations and `overall='UNKNOWN'`:

| Status | Meaning |
|---|---|
| CONDITIONAL_SOLUTION | Native FEASIBLE/OPTIMAL, then independent candidate check passed within budget; only conditional on exactly supplied constraints |
| CONDITIONAL_UNSAT | Native INFEASIBLE under the exact compiled, explicit constraints; not a claim about missing reality facts |
| TIMEOUT | Phase budget exhausted or CP-SAT UNKNOWN after bounded search; **not unsat** |
| UNKNOWN | Missing/inexact/unsupported data, model error/exception, stopped event or independent output rejection; no candidate published |

No solver status alone publishes a candidate. A verification rejection drops the
candidate entirely. Failures and limits do not relax a hard constraint or silently
expand selection. Results remain private read-lifetime data; no persistence or
production cleanup promises are added.

## Local execution and remaining gates

The module-local `pyproject.toml`/`uv.lock` pin OR-Tools. From repository root,
use an exact export of fixed PLACE at PLACE_EXPORT:

```sh
uv sync --project backend/feasibility --frozen
PYTHONPATH="$PLACE_EXPORT/backend/place:backend/feasibility:backend/needs:backend/auth" backend/feasibility/.venv/bin/python -m unittest discover -s backend/feasibility/tests -p test_solver.py -v
```

The caller-supplied route as_of is an explicit evidence point, not a live AUTH
or clock assertion. Hosts must revalidate current evidence/admission before any
future real publication or write; this pure candidate interface grants neither.

The old NEEDS/route tests and their accepted evidence are reused; this slice's
synthetic tests use actual OR-Tools and fixed NEEDS/PLACE types. Provider, Auth,
PG, App, actual route/date evidence, complete cost/rest model, production runtime
and all Issue18 I/acceptance gates remain UNRUN. No formal Trip writes, new
permissions, root wire, PR/push/merge/deploy or claim of Issue closure.
