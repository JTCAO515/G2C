# CJ015 cancellation/interruption repair

Failing fixed parent: 6afa6742b13f5f5fafc9be1dcee89b26b2c3f04a.
Read original Testing CJ-015-transaction-repair/REPORT.md and run_pg.py lines52-67.
Original two shapes reproduced in test_transaction_interrupts.py: real COMMIT then
CancelledError; real COMMIT then ConnectionError plus close CancelledError. Both
now preserve CommitUnknown, original cause and commit_possible, with original v1
receipt available by ordinary query. No new action/resend was attempted.

Only product delta is cj_trip/postgres.py transaction/cleanup boundary:
- COMMIT BaseException becomes CommitUnknown chained from the original interruption.
- After COMMIT starts, propagated guard errors/cancellation carry commit_possible.
- Rollback/close/logging BaseException cannot replace an existing primary outcome.
- If successful commit/private-return is followed only by cleanup cancellation,
  propagate that cancellation with commit_possible=True. Do NOT return fake success
  or claim rollback. The known durable receipt remains in the original action table,
  available via an independently admitted query, not leaked through cancelled return.
- Ordinary cleanup Exception still logs safely and preserves a known Receipt;
  existing postcommit Denied identity/marker and precommit cancellation are retained.

Author actual new private PostgreSQL17.11 PASS: 30 tests = 11 prior transaction
controls + 19 interruption controls. Interruption matrix: CancelledError,
KeyboardInterrupt, SystemExit at commit, cleanup-after-unknown, precommit+rollback,
private return, cleanup-after-known-success, and cleanup-after-current-denial;
plus a logging-handler interruption while preserving original CommitUnknown.
Original14 evidence reused, not count-summed. Original three Review fault probes
and actual PostgreSQL stop/start original-v1/latest-v2 read also PASS.

Exact identity in pg-results.json; new empty UTF8 database, explicit Unix socket,
listen_addresses empty, clean env/explicit passfile, task bootstrap role only.
Final PID/socket absent, 0700 directories; data and logs retained. No old cluster
started, no permission/RLS/cloud/provider/wire/schema change. Synchronous injected
interruptions test Python BaseException handling, not a deployed async-driver claim;
uncatchable process termination remains original-action recovery territory.

Original 6afa positives and independent failures unchanged. New independent gates
PENDING, complete original chain required. No publish/push/PR/closure/deploy;
CJ005/CJ014/App/real-AUTH integration gates remain unchanged.
