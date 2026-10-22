# CJ008 local metering core

Self-contained, stdlib-only Python >=3.12,<3.15 candidate. Tested Python 3.14.7.
See [contract](../../contracts/usage/README.md) for all scope and trust boundaries.

Run from this directory:

```sh
uv run --offline --frozen python -m unittest discover -s tests -v
```

`cj_usage/core.py` supplies value types, mandatory configuration, repository
protocol and transitions. `local_exit.py` only permits injected synthetic execution
and defaults disabled. `tests/test_core.py` owns the nonpersistent transaction fake;
there is deliberately no production in-memory fallback. `sql/001_candidate.sql`
is an unapplied design candidate, not a registered migration or working repository.

Author verification: 18 tests PASS, covering absent/invalid configuration, disabled
exit, ID conflict/replay, concurrent budget and one-shot claims, pre-dispatch cancel,
timeout/unknown/late settlement, over-reservation actual receipt, aggregate output,
loop limits, deadline/clock regression, config reset refusal, receipt conflicts,
unknown commit ACK, immutable reads and shared background memory budget.

UNRUN: independent Review/Testing, PostgreSQL application/transactions/RLS/restart,
real AUTH/admission integration, trusted receipt pricing, provider caps/hard timeout,
real external calls, host/API integration, production rollover/cleanup, deployment
and device E2E. No Issue closure, push, PR, merge or release performed here.
