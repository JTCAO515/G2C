# CJ013 protected-read author evidence — 2026-10-23

Base c821b34d607016c6dbc1020c203621841f1a60e8, original owner/branch, only
backend/needs/** + contracts/needs/**. Candidate is the commit containing this
report. Independent Review/Testing and full CJ035 entry gates pending.

Actual author run: **33 PASS** in protected-read-after.txt: 16 parametrized new
read-seam cases and 17 original PostgreSQL write/read/CAS/UNKNOWN regressions.
Original unaffected 23 grammar/domain checks and prior source evidence reused.
No root/API/schema/lock/old stored bytes modified.

- Original consumer failures were read from the read-only CJ035
  `backend/feasibility/evidence/current-read-seam-fail.txt` and `tests/test_current_read.py`.
  Those moving files were **not imported, executed or accepted as a dependency**.
  Two local tests replay the same concrete close fault and host scope-on-close
  remapping against the new public ProtectedReader; both withhold bytes.
- `protected-read-first.txt`: 32 PASS, 1 FAIL. Scope remapping was refused, but only
  on a later reader (two connections instead of the required immediate post-close
  gate). Added strict-reader guard directly after successful close; final 33 PASS.
  The original failed timing assertion and evidence remain unchanged.
- Complete bilingual original source bytes/history returned in a bounded full
  projection; original Operation/Snapshot/Revision and canonical AUTH context used.
- Close ordinary failure/cancel, post-close revocation/identity change, projection
  configuration mutation, final canonical AUTH configuration/repository mutation,
  non-bytes/lazy output, output cap, expired handles, caught write denial, callback
  cancellation/reentry all refuse publication. No consumer SQL/AUTH/evaluator copied.
- Only new strict-read repository uses strict close + post-close guard. Existing
  write and unknown commit/query tests pass with previous semantics.
- Fixed canonical AUTH8b package exported from Git object
  8b6abb236cf10c1865a9cc8c6155bd8ac732c07e into ignored .local/auth8b;
  hashes in auth8b-manifest.json. Existing root AUTH tracked tree untouched.
- Two NEW private PG17 clusters: .local/px4xjgm04 (first) and .local/p3nnnqdxf
  (after), both stopped and preserved with STOPPED markers, no postmaster.pid.
  New synthetic role cj013_synthetic, explicit Unix socket/port56413, empty
  password/0600 empty passfile, inherited PG* removed in test process,
  listen_addresses='', no TCP. No old DB, real credentials/provider/cloud accessed.

Precise new host signature and supported configuration/resolver constraints:
contracts/needs/PROTECTED-READ.md. Legacy Boundary remains the write/receipt entry;
full current-read consumers must use the new protected seam after independent gates.
Production resolver/grants/RLS/cleanup, full CJ035/root/API, real account/App/model,
Issue I acceptance, deployment/CI: **UNRUN**. No external messages/push/PR/merge/close.
