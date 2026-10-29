# RUN-USAGE-STEP-BINDING@1

Immutable local association for the fixed answer/draft steps. This supplements, and
does not overwrite/backfill, the historical single UsageBinding on cj_run_record.

cj_run_step_usage key: (scope,run_id,step_key). step_key is exactly answer or draft.
The trusted server allocates attempt_id and operation_id once; command_bytes are
canonical Command fields (attempt_id,operation_id,run_id,kind,input_digest,reserve,
output_limit), input_bytes are the exact outbound input before credentials/headers.
SHA256(input_bytes) equals input_digest. run_id matches the original receipt/RUN;
kind=model, reserve=1 for the approved provider_call profile. IDs, bytes, ledger_scope,
unit and period are immutable; conflicting same-key data fails closed.

Persist Stage A under RUN serialization with a unique step key, then acknowledge
commit before any Meter call. Duplicate acceptance reads the original association,
never changes attempt or period. Legacy unbound running work remains query-only;
there is no speculative backfill or automatic replay after provider uncertainty.

Runtime has SELECT/INSERT only, forced RLS requiring both its message scope and
original ledger scope to match transaction-LOCAL authority. No association
UPDATE/DELETE. Empty/missing/malformed association or ledger is unavailable, not an
invitation to reset usage. Original-period reads install only server-derived
historical authority from that immutable association, never a caller ledger ID.

New-period provisioning is a separate explicit initialization operation. No real
credentials, header secrets or raw model output are stored in this association.
Only local FakeProvider input is enabled by this contract. Physical retention,
production billing and background/tool metering remain outside #170.
