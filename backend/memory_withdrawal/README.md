# CJ021 memory deletion

M3 adds [MEMORY-ERASURE@1 / original association and runtime fence](../../contracts/memory-withdrawal/ERASURE-V1.md).
M44 registers the original private manifest and minimum noncontent barriers with
account/item cleanup hooks in the same change. The explicit erasure app requires
B's complete memory-purpose message/run/usage hooks; missing composition does
not claim completion. The three registered PG groups exercise C physical hooks,
shared-candidate preservation and a signed API with genuine B UNKNOWN results.
They do not prove whole cross-domain/device/production erasure.

The following is the historical internal observation candidate; it is not the
M3 deletion API or an activation claim.

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
