# USAGE-STATUS-WIRE@0.1.0-rc.1

Readonly original-attempt API on prior348/c5. Runtime USAGE8cf6a85 final-binding repair (original6f/be473 evidence retained),
AUTH8b6abb protected read context; existing F3 init/interfaces/admission/JWT bytes
identical, only additive read_context required. One canonical AUTH package, no new
verifier/permission provider or MESSAGE dependency in standalone USAGE. Existing
c5 schema/operations retained. Neither USAGE@1.0 nor financial/product I is frozen.

GET /v1/usage-attempt-status?attempt_id=… (getUsageAttemptStatus) returns required
{request_id,attempt}. Request has only exact original attempt label (source200 chars
and explicit host UTF8 bound), no owner/environment/unit/budget/period/run selector.
Host UsageStatusConfiguration explicitly supplies authorized historical period bounds
and final response cap. Trusted resolver receives verified principal/environment/
period and returns canonical existing PostgresRepository; issuer/audience matched to
strict host JWT configuration. Mapping must authorize the period and stable
issuer/subject/audience/environment, never token timestamps or request data. Missing
config/resolver fails closed; no scope/ledger creation or current-budget fallback.

Per HTTP invocation root constructs the ORIGINAL ProtectedReadBoundary and
AttemptStatusReader, sharing the original checker and frozen host config/resolver.
This avoids one-instance active-callback reentry conflicts between legitimate requests;
no ctx is cached/shared. Same-instance reentry, cancellation/retirement/thread and
final outer check remain original AUTH behavior, not a new wrapper guard.

Only public reader.read(token,attempt_id,project=…) is called. Protected projection
validates the minimal source JSON and encodes the complete BASE envelope INSIDE
read_status/project. Source final size bound includes envelope; READ ONLY SELECT,
commit, cursor/connection close, storage/domain guard, then outer AUTH final check
all precede exact bytes leaving. HTTP sends bytes unchanged, no decode/rewrap later.
Source/cleanup/commit errors withhold result; unknown primary transaction outcome is
not overwritten by later denial. Reader-origin interruption becomes sanitized503;
outer HTTP cancellation still propagates. No reserve/claim/settle/cancel/Meter/provider.

Public fields: original attempt/operation/run/status, opaque unit, original reservation,
optional confirmed receipt count/output/ID, cancelled/exceeded and original bilingual
status text. No whole ledger/config, input_digest/prompt/budget ceiling/current balance.
reserved_units/confirmed_units/confirmed_output are EXACT unsigned base10 integer
strings in this new wire. Source integer type has no Int64 upper bound; strings
avoid Swift overflow without new dependency or invented budget cap. This is only
representation, never float/rounding/unit/currency conversion. Unknown confirmed
fields remain required null; original confirmed0 is "0", not unknown. Nonsettled
receipt fields must all be null, settled fields must all be supplied. Invalid numeric
forms/types fail, never default/coerce to zero. Historical receipt is not current
balance, monetary charge, execution/source permission or dispatch authorization.

Missing bearer401; malformed/extra query400; explicit ID cap413; public AUTH denied
401/403 and UNKNOWN503; read/config/period/row/corruption/encoding/cap/close/commit
uncertainty503 retry_safe_read. No synthetic/null status on failure. Public typed
ReadAdmissionFailure is used, no copied auth decision logic. Required status/confirmed
null fields are generated from sole OpenAPI. Swift null fallbacks must have actual
nil value; unknown != zero. BASE request-ID/header/no-store and safe errors unchanged.

Whole ledger is decoded internally by canonical storage but never emitted; response
limits do not bound that DB/codec work. Reads do not increment revision, reset missing
state, add quotas or change privileges. Registry only adds read consumer on existing
usage store; retention/restore/product RLS and shared AUTH-USAGE-RUN dispatch fence
remain unimplemented/unverified. Test SELECT-only roles/RLS apply only in a NEW
private synthetic fixture, not a production authority/policy or permission upgrade.

Checks: check-usage-status-wire.sh, check-generated-usage-status.sh,
build-usage-status-loopback-client.sh and generate.sh --check. Targeted tests separate
source/auth/scoped DB doubles from fresh private PG/numeric HTTP evidence and from
independent source/root gates. Original core/13 storage/11 PG suites are reused,
not rerun. Actual accounts/provider fees/dispatch/App/Issue9 I remain unverified.

Author combination9d0f4b4 passed7 groups on NEW SELECT-only/NOBYPASSRLS fixture PG
and numeric HTTP including official Swift GET; one wrong-period control is realDB+
ASGI and labeled. All revisions/ledgers unchanged and services stopped. Infrastructure
approval timeout before process creation retained, followed by one permitted retry.
See tests/evidence/usage-status/REPORT.md; no real account/fee/dispatch/product RLS
or full I follows from synthetic historical ledger receipts.

Final-binding repair consumption: original Review2 failures are retained. Runtime8cf
performs direct captured scope/connect/reader configuration comparisons AFTER the
original AUTH boundary final callback/retirement, without reactivating ctx or invoking
new checker/resolver/SQL/project. Root only updates the exact source pin; no outer
authority workaround or SDK change. Same original Review assertions pass against fixed
canonical imports, plus3 affected root close/outer/parallel lifetime checks. Independent
combination review is still required; prior7 PG results retain their original source.
