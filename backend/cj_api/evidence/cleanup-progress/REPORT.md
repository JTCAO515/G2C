# CJ-005 cleanup progress source delivery

Base: `0ecb94ae3815f80a2e38abeb72f70525d04f1b7a`.
Wire: `CLEANUP-PROGRESS-WIRE@0.1.0-rc.1`.
Producer runtime `514aba717dd0e0a7f7783b6d9072d347cdb0a623` /
evidence `6635bb9b301b567edeef91689c0097b25c576ba9`.
AUTH `8b6abb236cf10c1865a9cc8c6155bd8ac732c07e`.
Runtime file hashes are in `cleanup_progress_pins.json`; no source domain edit,
AUTH3 core delta, new dependency/lock, SQL migration, grant, provider or UI change.

Actual root checks:

- PASS scoped canonical checks: 9/9, `scoped-checks.txt`. Real strict synthetic-key
  verifier/admission, native protected read lifetime, actual cleanup journal replay,
  actual canonical PG Repository.query with controlled DB-API callbacks. No DB.
  Current deny/unknown never resolve; foreign scope/original operation withheld;
  SELECT-only/no FOR UPDATE/no recovery; original revisions/in-flight/unknown and
  finite complete preserved; missing hooks/gaps explicit; no private metadata;
  final commit/close failure and close revocation withhold bytes; same-principal
  final outer AUTH connect swap rejected; wrong resolver scope/guard denied;
  caps reject whole response; concurrent native lifetimes separate; composed
  native boundary receives the exact MESSAGE checker.
- PASS official Swift CJAPI build + generated GET consumer, fixture transport.
  Original ID encoding, status/step unknown and hook unavailable, mandatory
  nonnull progress, matching BASE request-id. Not an HTTP server or DB run.
- PASS OpenAPI/examples/compatibility/storage registry and foundation 4/4.
- PASS official generation reproducibility (`generate.sh --check`, exit 0).
- PASS exact all previous schema/operation definitions unchanged against both
  base `0ecb94a` and original association source `33cec5b`, using
  `scripts.check_contract.compatible`. These are definition compatibility checks,
  not a rerun of every old domain's runtime tests.
- PASS `git diff --check`.

Original failures are retained, followed by the final 9/9 run:

1. `initial-export-path-failure.txt`: command used nonexistent cj-003-auth path;
   located actual cj-007-auth, no source changes or dependency changes needed.
2. `initial-state-assertion-failure.txt`: fixture expected overall in_progress
   while first auth_revocation step was in_progress. Canonical status remains
   awaiting_revocation until revocation confirmed; corrected the expectation,
   retaining exact in_progress step and revision assertions.
3. `checker-observation-fixture-failure.txt`: instrumentation looked for public
   boundary.checker that native read boundary does not expose. Corrected to
   observe the constructor's checker argument; production code unchanged.

UNRUN root actual HTTP/PostgreSQL/account chain, logout/revocation backend,
physical data cleanup/hooks, offline devices/backups/external retention, UI/device,
provider, deploy/release and product acceptance. No new PG, old PG restart or
old cluster reuse. Producer 6635bb9 actual PG evidence is separate and does not
establish a root real chain. Cleanup metadata retention/restore/physical deletion
remain UNIMPLEMENTED/UNDECIDED in the registry. Complete means only original
frozen operation scope. Independent Review/Testing/Publish are Main-owned and
remain pending; Issue #5 stays open. No push/merge/deploy performed here.
