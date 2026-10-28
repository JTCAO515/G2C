# CJ-035 deterministic NEEDS checks

Read-only local candidate; see `contracts/feasibility/README.md` for the public
interface, exact NEEDS pin, conclusions and integration limits. NEEDS/route checks
use the standard library; the separate bounded solver uses module-local OR-Tools. Run from repository root:

```sh
PYTHONPATH=backend/feasibility:backend/needs:backend/auth python3.14 -m unittest discover -s backend/feasibility/tests -p test_validator.py -v
PYTHONPATH=backend/feasibility:backend/needs:backend/auth python3.14 backend/feasibility/demo.py
```

Synthetic fixtures use actual NEEDS validation. No server, SQL, socket, model,
provider request, domain write, root configuration or shared lock changes.

Fixed PLACE estimate consumption is documented in
[ROUTES](../../contracts/feasibility/ROUTES.md); its optional dependency and tests
are separate from NEEDS-only.

The bounded CP-SAT candidate and its module-local dependency/reproduction are
in [SOLVER](../../contracts/feasibility/SOLVER.md).

## Runtime startup (#176)

The solver module loads CP-SAT during process initialization. The API factory
imports it before creating the application, and the worker imports it before
accepting work. A dependency loading error aborts startup; it is not converted to
an `UNKNOWN` solver result. The existing root dependency pin remains unchanged.

`max_solve_seconds` still starts at `solve()` entry and covers preparation, model
construction, search and output verification. Process-level dependency loading is
outside that request budget, per the accepted [#176 decision](https://github.com/JTCAO515/G2C/issues/176#issuecomment-6460752372).
Budget values, cancellation, TIMEOUT/UNKNOWN and model/search/output checks are
unchanged. `tests/test_startup.py` verifies API/worker startup in fresh processes,
real first-request solving, fail-fast loading, and model-budget exhaustion.
