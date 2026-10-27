# CJ009 consumes CJ-AUTH-SERVER@0.1.0-rc.1

Current fixed source: CJ007 commit `79f88b6552da1bd3d4b27e22f64a158bddf2853b`,
`backend/auth/cj_auth/interfaces.py`, `admission.py`, `__init__.py`.
Only git-show blobs at that revision were read/executed; the moving JWT worktree was
not imported. The three temporary files are removed after testing; no second AUTH
specification/types or copied package is committed here. AUTH remains RC, not frozen.

Confirmed compatible: TrustedPrincipal is returned only via the real AdmissionChecker
allowed decision; VerificationResult invalid/unknown and denied/unknown access facts
remain distinct. CJ009 does not infer invitation/email membership from token/body.
`auth_boundary.py` directly imports the fixed interface types and version. A server
composition root supplies AdmissionChecker and a server-owned principal-to-repository
mapping. The client never supplies a scope/repository/principal. No mapping default,
route, JWT verifier, policy provider or token logging is implemented by CJ009.

Internal service wiring rechecks the same token/principal at transaction entry,
before transaction exit (commit), and after successful commit before returning private
results. A denied/unknown precommit check aborts the transaction. After-commit denial
or identity change has commit_possible=true: the original action may be committed,
so clients must preserve its ID/bytes and later query rather than resend under a new ID.
CommitUnknown from the repository is preserved. Actual provider dispatch is absent;
reading pending obligations is not a permanent authorization grant for RUN to execute.

## Concrete remaining gaps for Main / CJ007 / CJ005

- Runtime declarations read back: message root `pyproject.toml` at ba6051a requires
  `>=3.12`; fixed CJ007 `79f88b6552da1bd3d4b27e22f64a158bddf2853b` package
  requires `>=3.12,<3.15`. The integrated declaration remains `>=3.12,<3.15`.
  Python 3.10+ was only an inferred syntax floor, NOT a support declaration.
  Earlier core checks on 3.9.6 remain historical local evidence outside that range.
  Consumer and repair-delta checks used Python 3.14.7; Python 3.12/3.13 UNRUN.
  JWT implementation from AUTH parent 3f374214 was not imported or executed by
  these interface checks; real JWT/host integration remains UNRUN here.
- TrustedPrincipal has issuer/subject/audience and token times, but no session revision
  or authoritative revocation fence. Rechecking the gate detects changes reported by
  current providers, not an atomic DB-linked revocation guarantee. Fixed principal
  equality prevents identity replacement, not unreported revocation. CJ007 must define
  provider freshness/revocation semantics; CJ005 must reconcile commit-boundary policy
  consistency. The gap is not filled with invented fields or caller claims.
- `resolve_repository(principal)` is a required server composition callback, not a new
  AUTH contract. Provisioning, identity/environment-to-storage mapping, membership
  persistence and DB privilege/RLS policy still need CJ005/CJ007 confirmation. Tests use
  one explicit test partition; they do not establish real multi-user isolation.
- Authoritative policy reads presently happen while the scope transaction is open.
  They must be bounded by the host. Slow/outage handling is fail-closed, but performance,
  network timeouts and transaction/revocation races need actual integration tests.
- RC version check cannot alone prove source identity; integration must pin the exact
  accepted AUTH source/dependency. No third-party installation or frozen package exists.

Six targeted tests execute the actual fixed AdmissionChecker with synthetic verifier/
policy and injected transaction doubles: allowed repeated checks; unknown/invalid/
unverified/uninvited; commit-boundary withdrawal rollback; return-boundary withdrawal
with committed original recovery; identity replacement; client-owner rejection and
pending-read withdrawal. Real JWT cryptography, provider/database, concurrent revocation,
server/client API, deployment and device remain UNRUN. Independent Review/Testing pending.

Reproduce within the declared Python >=3.12,<3.15 range (tested 3.14.7 only),
pointing at the local CJ007 Git repository:

```sh
/opt/homebrew/bin/python3.14 -B backend/message/tests/run_auth_consumption.py <local>/Documents/Codex/2026-10-21/cj-007-auth
```

The runner pins the revision internally and reads git objects, never source working files.
Original 14 pure-domain/repository tests remain valid and were not rerun for this additive
boundary. No changes to domain.py/postgres.py/SQL or shared API/AUTH source in this delta.

## Fixed AUTH repair consumption

Current pin 79f88b6552da1bd3d4b27e22f64a158bddf2853b supersedes e49ea1a2 for
future reproduction. Exact diff of the three imported files shows only the
VerificationResult constructor tightening: non-VALID must carry None, VALID must
carry TrustedPrincipal. AdmissionChecker and package init are byte-unchanged.
CJ009 legal results already satisfy this rule; auth_boundary.py is unchanged.

Original six checks remain evidence against e49ea1a2, not a claim of six new runs.
Only two affected tests ran against 79f88b65: malformed non-VALID principal rejection
(including false/zero/empty/dict/object/TrustedPrincipal), legal VALID/None cases,
and original unknown/invalid/uninvited/unverified denial before repository resolution.
Both PASS; output evidence/auth-repair-delta.txt. The runner permits targeted unittest
names after the repository argument. No AUTH type copy, real DB, JWT crypto or provider
integration occurred. Independent double review remains pending; interface not frozen.
