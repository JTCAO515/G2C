# CJ015 with_operation serialization boundary

Parent0e2c3241825d81b89cc7bdb2f2c6daa967038068. New operation.py + narrow
AUTH binding refactor; no repository transaction change, policy, SQL, wire or root lock.
Public contract: contracts/trip/OPERATION.md. Actual first write paths operation.py
and auth_boundary.py. Original fixed chains and failure evidence remain preserved.

20 new actual PG checks PASS: all five context methods + principal/scope metadata;
post-serialization AUTH denial with/without DB work; transaction/commit/private-return
denial or cancellation caught by callback remains sticky (six cases); projection
ValueError/CancelledError/KeyboardInterrupt after durable act preserve original ID;
expired/cross-thread/nested-request context refusal; coroutine/iterator/object return
refusal; actual scope/connect/confirm/checker/resolver drift refusal; actual COMMIT
then cancellation with callback swallow remains original-action-only recovery.

Affected suite 76 PASS total = 14 original + 11 transaction + 19 interruption + 12
proposal-read + 20 new projection. Fresh suite justified by AUTH binding refactor and
new full request lifetime. Review's original fault probes and actual PG stop/start
original-v1/latest-v2 separate-process read PASS as recorded. No independent Review
or Testing PASS inferred from this author run.

Fresh empty task PostgreSQL17.11, UTF8, explicit role cj015_private/DB cj015_test,
Unix socket/port55435/passfile, clean environment, TCP disabled. Exact identity in
pg-results.json. Final PID/socket absent; 0700 private paths and all data/logs retained.
No old/private-other cluster restarted, no account/provider/fees/cloud/RLS action.
Syntax/diff checks PASS. CJ005 consumer confirmation and formal route integration
PENDING; no actual UI evidence or CJ014 proof added, confirm remains default absent.
No push/PR/merge/Issue closure/deployment.
