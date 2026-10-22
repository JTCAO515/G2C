# CJ015 de4e three-family repair

Failing base: de4e53da323c8df77f250d0b39f4ff86926bccb8.
Independent inputs read without alteration:
- cj-review/CJ015-de4e53d/review-summary.json and pg-runner.py/pg-results.json
- cj-testing/CJ-015-trip-core/REPORT.md
Original source/14 PASS/restart and independent failure evidence remain preserved.

Code delta: only cj_trip/postgres.py. Reject non-fresh/autocommit/unknown connection
metadata before cursor creation or SQL; final expiry check after commit guard;
cleanup warnings cannot mask receipt/CommitUnknown/post-commit denial. No scope,
AUTH decision, confirmation, SQL schema or wire change.

Author real PostgreSQL verification PASS:
- 25 tests = original 14 + 11 regression controls (fixed-suite.log).
- Autocommit/active/unknown metadata: no cursor or rollback call, no Trip/receipt,
  candidate pending. Actual BEFORE INSERT receipt trigger faults: autocommit denied
  before SQL; ordinary transaction raises trigger error and rolls back all writes.
- Slow canonical AUTH ALLOWED check crosses expiry: accept and reject both Conflict;
  Trip/receipt absent and proposal pending after rollback.
- Actual commit then close failure returns original Receipt. Lost ACK plus close
  failure retains CommitUnknown and original ConnectionError cause. Post-commit
  AUTH denial retains commit_possible. Precommit denial still rolls back.
  Generic cleanup warning observed; injected sensitive error text absent.
- Adapted original Review probes all PASS in pg-results.json (same fault shapes).
- Actual private database stop/start and separate-process original-v1/latest-v2 read
  PASS. Final PID and socket absent; data/logs retained, 0700 private directories.

Fresh target identities are recorded in pg-results.json. No old database started.
Runner clears environment, uses explicit socket/role/database/port/passfile, TCP
listen_addresses empty. SQL only applied to the new empty UTF8 task database.
Two fresh test clusters were used: first collection accidentally imported original
14 tests twice (39 PASS, not 39 distinct tests). Explicit imports corrected that
harness issue; final fresh run has 25 distinct tests. First logs/results retained
and accurately labelled. Both clusters stopped; no deletion or reuse.

Source hashes accompany these results. Independent Review/Testing of the new head
PENDING; no Publish/PR/push/merge/Issue closure/deployment. Original App/CJ014/API and
real AUTH integration gates unchanged. This fixes ordering against slow admission,
not a new cross-system atomic revocation or wall-clock scheduling guarantee.
