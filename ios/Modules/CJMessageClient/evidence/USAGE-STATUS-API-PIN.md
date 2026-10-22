# Shared CJAPI original USAGE status candidate

Exact parentf4c17b59213828543cef042d127c56d8467963d8 (readonly-preview capability is a
SEPARATE preceding commit; its source is unchanged here). Fixed official producer
9d0f4b4c1e89b28d01de18092b5bf695de5bcde7 from CJ005. No claim of merged/frozen business
or App integration. Existing branch and exclusive module export/Package/tests/evidence.

One versioned export:
`ios/Modules/CJMessageClient/.generated/9d0f4b4c1e89b28d01de18092b5bf695de5bcde7/CJFoundation`

Original sixteen official files exported unchanged, exact hashes in generated-pin.json.
Oldc5/c02/201156/d688/9dc/573 inventories rehashed unchanged; one actual standalone
CJFoundation graph location. No duplicate active package identity, hand-edited generated
source, alternate SDK or other consumer manifest changes. Previous c5 was not re-exported.

Fixed c5→9d0 comparison: all23 old paths and86 old component schemas exactly equal,
SDK manifest/lock/datehelper byte-identical. New GET /v1/usage-attempt-status, operation
getUsageAttemptStatus, UsageAttemptStatus/UsageAttemptStatusResponse only. Default real
write gates and narrow readonly preview factory remain unchanged. No App active pin change.

PASS: standalone compile and six targeted checks: three new USAGE compile/codec tests,
plus actual official preview-through-capability synthetic call, old receipt/null query,
and Memory configuration smoke test. Old broad business results reused, full suite not
rerun. New method is referenced without invoking it. Codec preserves arbitrarily large
reserved counts as decimal STRING, actual confirmed zero as STRING "0", and unknown
confirmed fields as actual null. Missing required attempt/confirmed fields and unsupported
status fail decoding. Non-null fallback remains non-null and cannot mean unknown.

The generated decoder is not a business-semantic validator: tests of four status enum
values do not certify each hypothetical field/status combination, integer pattern,
actor/scope, original attempt linkage, period eligibility or settlement receipt. A real
consumer must validate these through its fixed contract. Unit is opaque, not currency;
null never means zero balance, successful release/charge, permission to retry or dispatch.
No counts are parsed to Int/Double, rounded, summed or treated as current funds.

Exact SDK revisions match previous locks; no upgrade. Standalone auto-resolution output
was retained in ignored .build/usage-status-pin-evidence then source lock restored. Raw
log hash/state inventory in usage-status-api-pin-provenance.json, concise test output
usage-status-api-pin-tests.txt. No business request, real service/account/Keychain/PG,
root lock/API edit, signing, push or deployment. Full App same-pin integration remains
Main-coordinated/UNRUN; independent double review still required. Existing HOLD unaffected.
