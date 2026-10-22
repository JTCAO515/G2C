# P2 context callback reentry repair

Exact parent: 930236d64697f2d78d67b8046f0881fafb0d167a.
Testing source read: cj-testing/CJ-010-run-core/REPORT.md and reentry_probe.py.
Original candidate remains FAIL/HOLD until independent fixed-delta review.

Before: five test groups executed; seven failing assertions show cancelled state
lost during started/text/effect/completed callbacks, committed effect overwritten,
and cancellation rolled back when the outer hook returns false or throws.
One read-only reentry group already passed. Evidence: p2-before.txt.

After: Service reads the run again after the external validity hook and rejects
superseded state. MemoryRepository now stages each transaction independently and
checks its repository revision before commit. Nested accepted writes survive an
outer exception or stale commit; rollback no longer replaces the shared map with
an old snapshot. Read-only reentry is permitted. No callback is disabled.

PASS: five groups (including all subcases) in p2-after.txt; existing 14 core tests
in p2-core-regression.txt. The stale outer operation raises Conflict; it does not
return success or a newly invented cancellation receipt. Query the original run
to see the accepted inner cancellation/event. Exceptions from the hook propagate
without undoing its already committed nested write.

This fixed delta includes core, fixture, regression tests and these evidence files
only. In-flight PostgreSQL repository/SQL/tests/docs are preserved uncommitted
for a separate subsequent delta. Existing PG normal cancellation/restart results
do not serve as proof of callback reentry. No PG restart/retest, network, provider
or worker execution was added for this repair. dispatch remains disabled.
