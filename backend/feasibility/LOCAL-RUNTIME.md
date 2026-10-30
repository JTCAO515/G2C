# FEAS local runtime consumption

C #281 consumes frozen B `CJ-LOCAL-NEEDS@1` / manual-v1 through
`cj_api.local_needs.protected_reader`, not an owner-role fixture or preview DTO.
`cj_feasibility.local_runtime.current_reader(conninfo_path=..., auth_dir=...,
limits=<explicit FormalReadLimits>, run_context=<optional actual context>)`
constructs the canonical B database with `needs_context=True`, canonical checker
and fixed formal projection. Local-only; no root activation, writer, alternate
AUTH/owner resolver, dispatch or publication permission.

Only token and needs_id enter the fixed read. Snapshot/Revision formal encoding,
FEAS and complete bounded private encoding remain in B ProtectedReader lifetime;
source change before the final read and final admission change withhold output.
Original read-only ABI/strict close and original public FEAS protection remain.

`tests/runtime_pg.py` uses actual signed NEEDS HTTP create/correct/history and the
restricted runtime role, then this reader. It also executes B's real registered
MESSAGE/model/tool/model/Meter + LocalPlaceProducer, consumes its owned run-display
formal result in the canonical NEEDS read, and applies the original route checker.
No Trip or AI draft is necessary. Query-time synthetic duration, explicit buffer
and rest are conditional only, not verified transport/overall feasibility.

Currency/total/per-person/paid/coverage, explicit timezone/DST/reversed interval,
unknown/missing and duplicate-ID cases stay independent; no zero/FX/time defaults.
The model NEEDS-preview.1 remains unconfirmed and is never the input record.

Complete CJ014/CJ017/CJ018 source-bound publication/Trip consumer combinations are
backfilled with #204/#285. Current read bytes alone do not authorize publication:
original RevisionLease/MESSAGE needs_reference must span the final effect commit,
with no new NEEDS connection nested under that lease and no lease during model IO.
No new permission/migration or real provider/cloud/account/fee/device operation.
