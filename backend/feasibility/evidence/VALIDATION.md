# CJ-035 local author evidence

Scope: NEEDS-first deterministic slice, not Issue 18 closure. All data synthetic.
Base: `8deb696f8149b4f5aa70c767be6c3a263b036227`.
Branch: `cj/035-feasibility`.
Owner tree: `<local>/Documents/Codex/2026-10-21/cj-035-feasibility`.
Only `backend/feasibility/**` and `contracts/feasibility/**` changed.

## Source and boundary checks

Source clone `cj-publish/Go2China` was clean at the exact base and its canonical
remote was `https://github.com/JTCAO515/Go2China.git`. Independent local
`clone --no-hardlinks` has a local origin pointing to that source; no push attempted.
First clone attempt with `--branch main` failed because that local clone had no
local main branch; Git left no target tree. The successful clone used the source
checkout and explicitly created `cj/035-feasibility` at the required base. No
existing directory or dirty work was replaced.

Read the sole Main HANDOFF, repository AGENTS/README/readiness/engineering/
contracts and Issue 18. GitHub connector returned null issue fields, so the issue
was read using official `gh issue view 18 --repo JTCAO515/Go2China --json ...`;
result canonical URL was `https://github.com/JTCAO515/G2C/issues/18`.
No issue/comment/PR changes, messages, resource calls or domain writes.
NEEDS `domain.py` is byte-identical to commit
`c821b34d607016c6dbc1020c203621841f1a60e8` (hash in public contract/manifest).

## Author verification: PASS

Runtime: existing Homebrew CPython 3.14.7, macOS aarch64, standard library only.
No dependencies installed, no root lock/configuration touched. Runtime specifics
and actual source hashes are in `source-manifest.json`.

Commands from the repository root:

```sh
PYTHONPATH=backend/feasibility:backend/needs:backend/auth /opt/homebrew/bin/python3.14 -m unittest discover -s backend/feasibility/tests -v
PYTHONPATH=backend/feasibility:backend/needs:backend/auth /opt/homebrew/bin/python3.14 backend/feasibility/demo.py
PYTHONPATH=backend/feasibility:backend/needs:backend/auth /opt/homebrew/bin/python3.14 -m compileall -q backend/feasibility
git diff --cached --check
```

- `unittest-first.txt`: initial 22 tests PASS; no original test failure hidden.
- `unittest-after.txt`: 27 tests PASS after decimal relation/date-bound probes.
- `unittest-candidate.txt`: 29 tests PASS with pre-write Candidate binding/provenance.
- `unittest-final.txt`: 29 tests PASS after per-item diagnostic details.
- `unittest-final-decimal.txt`: final 29 tests PASS, independent Decimal context.
- `demo-final.txt`: five synthetic public consumer examples PASS. Earlier demo
  output is retained; decimal-context change does not change those examples.
- Compileall PASS; staged whitespace check PASS.

The 29 tests cover four NEEDS states/absence, actual Command/validate_fields,
original field revision association, historical snapshot isolation, bad chains,
duplicate IDs, malformed versus unresolved input, cross-day and cross-zone order,
DST fall ambiguity/spring gap/non-hour Lord Howe gap, date-range overflow, shared
versus distinct applicability, party inclusion, cancelled/hotel/intent handling,
36 interval-pair property counterexamples (72 order-swapped evaluations), arrival
and departure, exact decimals under hostile precision/exponent contexts, missing
currency/basis/party/coverage, no paid deduction or FX, exact text protection,
locked/unselected edit/deletion/reorder, every nonknown lock, pre-write candidate
base binding, no fabricated candidate provenance, deterministic bilingual checks,
and nonmutation of supplied objects.

## Conclusions and outstanding gates

Local source/contract/synthetic behavior: PASS (author only).
Independent Review/Testing: UNRUN; fixed candidate goes to the original roles.
PLACE, real routes, rest/cost sources, OR-Tools/bounded solving: UNRUN here.
Root API, authorization response lifetime, PG, real provider, App/device, deployment:
UNRUN. No real-service or total-feasibility claim. Budget cost comparability and
paid semantics: UNKNOWN because fixed NEEDS has no typed cost ledger/coverage
identity; exact declared arithmetic is exposed without claiming contradictory caps.
CJ-014/017/018 integration confirmations PENDING. Issue 18 I gates remain open.
