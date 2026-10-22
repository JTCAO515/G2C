# CJ010 RUN internal core

Standard-library-only Python 3.10+ module; no installed dependencies or root lock
changes. Execute from repository root:

```sh
PYTHONPATH=backend/run python3 -B -m unittest discover -s backend/run/tests -v
```

`core.py` contains immutable state transitions, pagination and repository protocol.
`fixture.py` is a synthetic process-local transactional adapter, never a production
repository. Reconstructed Service tests reuse memory; they do NOT demonstrate
process restart, disk durability, DBOS execution, database isolation or RLS.

Contract and dependency gates: ../../contracts/run/README.md.
No SQL is needed for this first executable slice; no migrations applied.
