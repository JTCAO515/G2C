# RUN-BACKGROUND@1 local activation record

The frozen BACKGROUND-V1.md interface is unchanged. The production code path now
uses append-only **0040_background_jobs**, following Device V3 M39, and the actual
C filtered DATA/EXTRACT/PUBLICATION@2 accepted in PR #444. There is no runtime
schema probing, missing-table fallback, legacy Data1 fallback or unregistered SQL.
The former standalone private SQL fixture is moved to this registered migration;
its executable checks remain and now run against the complete chain.

## Storage, permissions and recovery

`cj_run_background_job` belongs to B `checkpoints/run`. Exact filtered model input
and original source/Travel references are content until user/account deletion.
Command/config, immutable IDs and unknown accounting are reconciliation evidence,
not diagnostic logs; a 90-day timer must not discard them. Model output is passed
to C and only its hash is stored by B. No second canonical Memory store is added.

The runtime role has own-account SELECT, original-only INSERT and UPDATE of only
state/output/receipt hashes, under FORCE RLS and active account/Run scope. It has
no DELETE/TRUNCATE or cleanup-role membership. The dedicated local cleanup role
can SELECT for original task preflight and DELETE only under an original account
plan, hashed owner fence and in-progress checkpoints/run intent. No new role,
SECURITY DEFINER or BYPASSRLS is added. Future memory-item payload redaction is a
separate C-authorized selection interface, not silently enabled by this schema.

Original physical worker leases are included in account stop preflight. Busy or
unsettled unknown work prevents erasure. The actual B account hook deletes this
table before old RUN state. Down refuses any background row and leaves all
original bytes intact; an empty chain supports full up/down/up. No main-applied
migration bytes are changed.

## Acceptance entry points

- `scripts/test.py`: existing non-PG suites plus background data/role validation.
- `scripts/pg_suites.py`: four appended background groups, using independent fresh
  PG, actual signed API, original run_once, restricted roles, C V2 and FakeProvider.
- `backend/run/tests/probe_background.py`: the same four checks against one fresh
  registered chain, with verified server shutdown; no fixture SQL injection.

Original-ACK reconciliation, source withdrawal, current Travel fencing, quota,
output/time limits, NoEligibleSource and account retirement remain real local
component results. Native devices, real models/accounts, cloud and backup evidence
are not supplied by these tests (#29/#32/#30).
