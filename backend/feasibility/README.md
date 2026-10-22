# CJ-035 deterministic NEEDS checks

Read-only local candidate; see `contracts/feasibility/README.md` for the public
interface, exact NEEDS pin, conclusions and integration limits. Standard library
only. Run from repository root:

```sh
PYTHONPATH=backend/feasibility:backend/needs:backend/auth python3.14 -m unittest discover -s backend/feasibility/tests -p test_validator.py -v
PYTHONPATH=backend/feasibility:backend/needs:backend/auth python3.14 backend/feasibility/demo.py
```

Synthetic fixtures use actual NEEDS validation. No server, SQL, socket, model,
provider request, domain write, root configuration or shared lock changes.

Fixed PLACE estimate consumption is documented in
[ROUTES](../../contracts/feasibility/ROUTES.md); its optional dependency and tests
are separate from NEEDS-only.
