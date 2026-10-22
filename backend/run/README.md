# CJ010 RUN internal core

Core uses the Python standard library. Unit checks ran on Python 3.9.6;
PostgreSQL adapter checks ran on Python 3.14.7 / psycopg 3.3.4 / PG 16.15.
These are observed versions, not a general compatibility promise. Future USAGE
composition must honor its declared >=3.12,<3.15 range. No root lock changes. Execute from repository root:

```sh
PYTHONPATH=backend/run python3 -B -m unittest discover -s backend/run/tests -v
```

`core.py` contains immutable state transitions, pagination and repository protocol.
`fixture.py` is a synthetic process-local transactional adapter, never a production
repository. Reconstructed Service tests reuse memory; they do NOT demonstrate
process restart, disk durability, DBOS execution, database isolation or RLS.

Contract and dependency gates: ../../contracts/run/README.md.
PostgreSQL adapter and candidate SQL are now present; see evidence/REPORT.md.
SQL was applied only to the explicitly authorized task-private empty test cluster,
which is stopped. No existing database or formal migration was touched.

Synthetic RUN→USAGE first-step checks and explicit production blockers are in
[USAGE composition](../../contracts/run/USAGE-COMPOSITION.md). The retained
missing-durable-binding counterexample is FAIL; no real dispatcher is enabled.
