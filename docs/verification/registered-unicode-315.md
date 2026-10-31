# #315 registered_exit Unicode CLI investigation

Status: **historical FAIL retained; root cause UNKNOWN, not a confirmed fix**.
Only local Unix-socket PostgreSQL and FakeProvider are involved. No real provider,
cloud, account, fee or credential is used.

## Observed and reproduced conditions

The original failure was the complete default PG run at C head
`1ee3eb7b80b98408828e223f8a5e1b5445dc6ef8`, with B sources unchanged from
`14065019`. It reached `registered_exit_pg.py:340`: the worker CLI returned 0,
but stdout did not contain `local_provider_calls=1`. The original assertion did
not retain stdout, so the actual count, three RUN states and accounting boundary
at that failure remain UNKNOWN. The same head's fresh standalone registered_exit
and exact remote CI passed. This does not establish either a Unicode bug or a
budget bypass. The historical FAIL is not relabelled PASS.

At baseline `a5993e3` (after C #325), a complete fresh registered_exit run passed.
Read-only diagnostics observed CLI counts `[2]` for the earlier normal/draft test,
then `[1]` for the Unicode test: high/low surrogate RUNs UNKNOWN, valid Unicode RUN
COMPLETED, exactly one Unicode metered operation. Repeating the Unicode combination
100 times with distinct owner scopes and fresh budgets produced 100/100 counts `[1]`,
with the same three statuses each time. This ran while other local suites were active;
it does not reproduce the historical failure or prove its cause absent.
Environment: CPython 3.14.7, Homebrew PostgreSQL 17.11, UTF-8 private cluster,
LANG/LC_ALL=C, actual signed local API and actual `scripts/run_worker.py --once`.
The probe retained the original high/low surrogate and valid Chinese/emoji inputs,
per-owner budget=1, max_steps=4, max_tools=1, model output=1000 and max_seconds=600.
No timestamp, assertion, provider or accounting behavior was relaxed.

## Next recurrence

The original failing assertion is unchanged; its failure message now extracts
only bounded numeric CLI counts, fixed high/low/valid case labels, RUN status,
acknowledgement, operation count, attempt-state enums and exposure. It never prints
stdout/stderr, tokens, internal owner scopes, IDs, private sentinels or input/output.
Unavailable DB evidence remains explicit; diagnostics cannot turn failure into success.
The later original assertions still require surrogate UNKNOWN/zero exposure,
valid completion, original-action replay with zero calls and unchanged exposure.

Run from a checkout with its own locked environment, not another worktree's editable
installation. `CJ_PG_BINDIR` points to approved local PostgreSQL binaries:

```sh
CJ_ENV=local uv run --locked python -B scripts/pg_suites.py registered_exit
CJ_ENV=local uv run --locked python -B scripts/pg_suites.py
```

On recurrence retain the safe assertion summary and exact head/environment. Zero
versus extra calls, pre-operation versus claimed exposure, and pending versus terminal
work are different cases; no cause is inferred until those facts are available.

The diagnostic failure path was also exercised with a controlled mutation of the
captured CLI count (actual completed run, report changed from 1 to 0). The unchanged
assertion failed and showed actual_calls=[0], surrogate UNKNOWN/0 exposure and valid
COMPLETED/settled/1 exposure, without private input or credentials. This verifies
failure reporting only; it is not a reproduction of the historical product symptom.
The affected complete registered_exit suite and non-PG checks (58/58) passed with
the diagnostic change. The historical head's default-suite replay also reached the
Unicode CLI with count 1 and the expected three statuses. That replay's RUN group
has a separate environment FAIL because PG16 was not supplied; it is not used as
an all-green replay or evidence about Unicode. No historical failure is erased.
