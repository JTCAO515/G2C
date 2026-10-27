# CJ-035 current-read consumer: partial delivery, strict entry BLOCKED

Base 512e272bece2e9ee5f768f08d01a3a43700ca9d7, original cj/035-feasibility tree.
Only backend/feasibility + contracts/feasibility changed. Old solver20/route/NEEDS
source/tests/evidence unchanged; no old full-suite rerun. No other owner writes.
Exact source bytes/input verification: current-read-input-manifest.json. NEEDS
c821b34d607016c6dbc1020c203621841f1a60e8 and AUTH
8b6abb236cf10c1865a9cc8c6155bd8ac732c07e match the accepted main snapshot in that
manifest. Exported exact commits into a new temporary tree; no moving-tree import.

## Code delivered

current_read.project_current requires actual canonical callback Operation and
ProtectedReadContext, explicit needs_id and trusted host-fixed positive limits.
It reads actual current Snapshot + full exact revisions through public operation
methods, calls existing evaluate, iteratively produces complete bounded immutable
bytes with both explanation languages, declarations, once-per-revision original
UTF8 sources/hash links, then rereads current Snapshot/checks metadata/principal
with fresh canonical context. No supplied snapshot/owner, SQL/history/AUTH copy,
private transaction access, new authority, factory or root endpoint.

## Actual private PG evidence

Runtime: existing CJ013 Python3.14.7/psycopg3.2.13, executed read-only with -B and
PYTHONDONTWRITEBYTECODE=1. No changes/install in that owner's environment. PG17.11
actual initdb creates each new cluster under this owner's ignored .local, empty
candidate schema from the fixed NEEDS source. Explicit Unix socket under /tmp,
private0700, explicit db/user/port/passfile/SSL/options/connect_timeout, no inherited
PG variables; listen_addresses='' asserted. Synthetic identity facts + original
manual fixture content, actual canonical AdmissionChecker/ProtectedReadBoundary/
NEEDS Boundary and transactions. No real JWT/account/provider/production RLS.

- current-read-first.txt: first consumer suite 12 PASS.
- current-read-final.txt: 12 PASS after original-source UTF8 projection was added
  and checked for exact SHA256 recovery; same affected slice only.
- current-read-seam-fail.txt: two explicit strict-entry requirements FAIL:
  ordinary close error swallowed and trusted environment mapping changed on close
  both still return bytes via the existing canonical composition. These are real
  negative findings, not xfail/skip or successful protected-entry proof.
- All three clusters stopped in class cleanup; actual pg_ctl stop succeeded,
  postmaster.pid absent, STOPPED marker written. Cluster roots preserved in logs.
  Socket dirs also left preserved; no TCP listener was enabled.
- Source syntax and staged diff whitespace checks PASS.

Consumer coverage: actual conflict/unknown output semantics and field revision
source association; wrong owner equals absent resource; expired/unknown/missing
configuration rejects before SQL; missing/tampered history rejected; revision/
aggregate input/output bounds; current version change after history withheld;
post-close revoke/principal change and post-full-encoding revoke withheld;
out-of-lifetime handles/forged objects rejected; record/revision counts unchanged
by evaluation. Fixture seeding/corruption is explicit test setup in these new
private databases, not runtime domain writing.

## Reproduce

Let INPUT_EXPORT point to exact fixed NEEDS + AUTH8b export; from repository root:

```sh
PYTHONPATH="$INPUT_EXPORT/backend/auth:$INPUT_EXPORT/backend/needs:backend/feasibility:backend/feasibility/tests" PYTHONDONTWRITEBYTECODE=1 <local>/Documents/Codex/2026-10-21/cj-013-needs/backend/needs/.venv/bin/python -B -m unittest test_current_read.PrivateReadTests -v
PYTHONPATH="$INPUT_EXPORT/backend/auth:$INPUT_EXPORT/backend/needs:backend/feasibility:backend/feasibility/tests" PYTHONDONTWRITEBYTECODE=1 CJ035_RUN_SEAM_PROBES=1 <local>/Documents/Codex/2026-10-21/cj-013-needs/backend/needs/.venv/bin/python -B -m unittest test_current_read.UpstreamSeamProbes.test_close_failure_must_not_release_bytes test_current_read.UpstreamSeamProbes.test_environment_rebind_on_close_must_not_release_bytes -v
```

Second command intentionally reproduces two FAIL, not a passing acceptance suite.
It explicitly selects only the two seam probes; no inherited suite repeated.

## Requested seam / remaining acceptance

contracts/feasibility/CURRENT-READ-SEAM.md requests the canonical owner guarantee:
strict read cleanup failures withhold output; after actual cleanup/full encoding,
revalidate the original host-controlled current environment binding under fresh
canonical identity, with no caller scope/new authority or second auth wrapper.
The consumer cannot observe those missing facts through existing public methods.
No bypass, connection wrapper or log interception was added to runtime code;
connection close hooks exist only in test fixture fault injection.

Projection consumer local proof PASS; complete protected entry BLOCKED/UNRUN
until that exact public seam is fixed and independently accepted. Main must route
request to original canonical owner; this owner sends no external messages.
Independent Review/Testing for this new partial candidate pending. Real provider,
production Auth/DB/RLS, root wire, UI and Issue18 I acceptance remain UNRUN. No
push/PR/merge/deploy, new credentials or domain/other-owner writes.
