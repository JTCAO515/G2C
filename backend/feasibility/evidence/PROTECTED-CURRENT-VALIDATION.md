# CJ-035 fixed NEEDS4cc9 strict seam integration

Base af52cbdfadf06cc79d511b6c1b06f756a1896594. Same owner/tree/branch, only
backend/feasibility + contracts/feasibility writes. New runtime source
cj_feasibility/protected_current.py calls original ProtectedReader.read with the
fixed project_current; no project/history/evaluate changes, SQL/AUTH copy, private
fields, producer changes or registered root factory. Default unconfigured path
withholds before IO. The immutable facade accepts only token and needs_id.

## Fixed source and author checks

Original CJ013 NEEDS4cc9c815293a4e03225b26adfa228fdd0b50b2e7 and original AUTH
8b6abb236cf10c1865a9cc8c6155bd8ac732c07e exported by exact git archive into a NEW
temporary directory. Export bytes checked against git show at those exact heads;
input manifest captures source hashes. No moving peer tree import/source write.
Main supplied producer independent dual-PASS; no producer suite/review repeated.

Actual PG17.11, existing read-only CJ013 Python3.14.7/psycopg3.2.13 with -B and
PYTHONDONTWRITEBYTECODE=1. Each invocation clears inherited PG variables and
creates a new local empty schema from exact producer candidate.sql; explicit
Unix-only DSN/socket0700/passfile0600 and listen_addresses='' assertion. Seeding
and one explicit concurrent fixture correction are synthetic test setup only.
Evaluation itself changes no record/revision counts. No old DB or real account.

protected-current-first.txt: 11 targeted new methods PASS.
protected-current-final.txt: final 12 targeted new methods PASS:
- Full exact bytes, actual version2 + complete original history, same-decision
  bilingual checks, local CONFLICT/overall UNKNOWN and no evaluation domain writes.
- Original af52 ordinary-close-exception assertion now rejects on FIRST close,
  exactly one opened/closed connection; original FAIL file remains unchanged.
- Original close-scope-remapping assertion now rejects on FIRST close, also 1/1.
  Resolver uses explicit supplied config environment, no hidden environment switch.
- Explicit configuration environment replacement on first close withheld.
- Revision/aggregate input/projection output bounds; producer/outer full-byte caps.
- Missing original history and record advancing during history projection withheld.
- Missing and wrong owner share safe refusal; default/UNKNOWN configuration no IO.
- After full encoding, canonical final AUTH revocation withheld; configuration
  mutation from that final provider callback also withheld after context retired.

Tests reuse old fixture SETUP functions only, not inherited old test methods.
Old af52 12-method proof, NEEDS/route/solver20 evidence unchanged/reused. Full
producer/auth/old domain suites not rerun. Syntax/scoped whitespace PASS.
Both NEW clusters stopped by actual pg_ctl with postmaster.pid absent, STOPPED
markers and preserved data/socket/log locations. No TCP, sockets/host resources
from an older database, credentials or provider dispatch.

## Reproduce / gate boundaries

Use INPUT_EXPORT with exact fixed NEEDS4cc9 + AUTH8b, from repository root:

```sh
PYTHONPATH="$INPUT_EXPORT/backend/auth:$INPUT_EXPORT/backend/needs:backend/feasibility:backend/feasibility/tests" PYTHONDONTWRITEBYTECODE=1 <local>/Documents/Codex/2026-10-21/cj-013-needs/backend/needs/.venv/bin/python -B -m unittest test_protected_current.ProtectedCurrentTests -v
```

This is author local integration evidence for the complete internal read entry.
New consumer independent Review/Testing pending; no public root API/factory is
enabled. No assumption that a read result means real travel feasibility or write
permission. Real JWT/provider/production Auth/DB/RLS/App/UI/Issue18 I remain UNRUN.
No push/PR/merge/deployment, new authority or external message by this owner.
