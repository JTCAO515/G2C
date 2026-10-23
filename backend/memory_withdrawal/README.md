# CJ021 internal withdrawal candidate

Independent branch `cj/021-memory-withdrawal`; base
`8ea1b35756726f60727f10deaf157c40b8df1072`.
Only this directory and `contracts/memory-withdrawal/` are written.

Standard-library candidate; imports existing pinned MEMORY/CLEANUP/AUTH modules.
Requires Python >=3.11; no dependency installation, global environment change or DB.
Example command using the verified installed interpreter:

```sh
PYTHONPATH=backend/memory_withdrawal:backend/memory:backend/cleanup:backend/auth /opt/homebrew/bin/python3.14 -m unittest discover -s backend/memory_withdrawal/tests -v
```

Read the [internal contract](../../contracts/memory-withdrawal/README.md),
[exact owner seams](../../contracts/memory-withdrawal/SEAM-REQUEST.md) and
[author evidence](evidence/REPORT.md). This is codec/observation code; persistent
withdrawal, physical cleanup and public activation remain blocked. No cleanup
algorithm or second official memory authority is implemented.
