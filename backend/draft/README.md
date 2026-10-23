# CJ014 local review candidate

Read [internal scope and remaining seams](../../contracts/draft/README.md).
Only already-generated canonical structured results are accepted. Production
factory is closed and no source registry, candidate persistence or formal Trip
write exists. All tests use explicitly synthetic historical canonical records.

From repository root, using the already installed Python 3.14:

```sh
env PYTHONPATH=backend/draft:backend/trip:backend/needs:backend/memory:backend/feasibility:backend/auth /opt/homebrew/bin/python3.14 -m unittest discover -s backend/draft/tests -v
```

No installation, global package change, database, model, real tool, credentials
or external resources are required. The existing FEAS NEEDS evaluator is imported
directly; this slice does not load/install the solver's optional runtime.
