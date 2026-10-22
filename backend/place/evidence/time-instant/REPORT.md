# CJ-012 P2 actual-instant time repair

Parent: `ec2d0a60e28ada64ac261185452070a3593cd6dc`.
Original source: `dd4c375a731bbaef1d436bc3e88466040ac02294`.
Status: author repair checks PASS; independent Review/Testing recheck PENDING.
Original candidate remains HOLD until the existing roles accept the new fixed head.

## Fix and scope

Only `gaode.py` runtime changes: after aware validation, use
`astimezone(timezone.utc)` copies for start/receipt/observation, then calculate
elapsed/age and chronology on that common instant timeline. Direct same-ZoneInfo
wall-time arithmetic caused the demonstrated fold/spring failures. Original
request timestamps, binding digest input and Source datetime objects/offsets/fold
are retained. No relabeling via `replace(tzinfo=UTC)`, provider date parameter or
public type/signature/version change. Unrepresentable UTC instants fail closed
as invalid_response/response_time instead of leaking OverflowError.

Runtime diff is confined to import, time normalization and the three affected
calculations/comparison. Contract adds only the explicit instant semantics.
All writes remain inside `backend/place/**` and `contracts/place/**`.
No root, AUTH, USAGE, RUN, provider transport, shared wrapper or authority change.

## Exact repro and verification

Python 3.14.7, synthetic bytes, no network or credentials. Files were copied
byte-for-byte into owner tests and checked with `cmp` against both originals:

- `cj-testing/CJ-012-place/independent_time_checks.py` ->
  `backend/place/tests/test_time_testing.py`.
- `cj-review/CJ012-dd4c375/IndependentTimeTests.py` ->
  `backend/place/tests/test_time_review.py`.

Both original reports/logs remain untouched. Before changing runtime:

- [testing-before.log](testing-before.log): exact Testing 3 tests, 3 FAIL.
- [review-before.log](review-before.log): exact Review 5 methods (7 expanded
  cases), 3 FAIL / 4 passing cases.

The already-minimal fixed probes and UTC controls isolate the same-tzinfo
arithmetic cause; no extra instrumentation, speculative hypotheses or broader
provider/environment investigation was needed.

After repair:

- [after.log](after.log): **13 methods PASS**: both exact original suites (8
  methods) and 5 affected controls. Controls assert inclusive 3s/60s thresholds
  across spring DST plus one-microsecond exceedances; receipt actually before
  start across fold; mixed timezone representations; original Source object
  identity, offsets/fold and binding digest; UTC conversion overflow rejection.
- [affected-legacy.log](affected-legacy.log): **4 existing methods PASS**:
  stale/timeout/invalid time, full original request binding, cooperative timeout
  and caller cancellation propagation.

No changes to original 32 tests or 6 consumer examples. Their valid unchanged
scope evidence is reused; neither complete set was rerun. The prior extreme
JSON exponent ERROR and its regression PASS logs remain unchanged. Earlier
`source-manifest.json` continues to describe the historical dd4c source only.

Commands from repository root (installed compatible interpreter):

```sh
# Each exact pre-fix suite was run with its own before log.
PYTHONPATH=backend/place python3.14 -B -m unittest discover -s backend/place/tests -p test_time_testing.py -v
PYTHONPATH=backend/place python3.14 -B -m unittest discover -s backend/place/tests -p test_time_review.py -v
# Fixed affected time suites, no provider or old-domain checks:
PYTHONPATH=backend/place python3.14 -B -m unittest discover -s backend/place/tests -p 'test_time_*.py' -v
PYTHONPATH=backend/place:backend/place/tests python3.14 -B -m unittest -v test_gaode.FailureTests.test_stale_timeout_and_invalid_time test_gaode.RequestAndRouteTests.test_binding_covers_query_role_mode_ids_limits_and_time test_gaode.SyntheticTests.test_timeout_cancels_cooperative_fixture_without_retry test_gaode.SyntheticTests.test_caller_cancellation_propagates
```

## Delivery boundary

Public PLACE types/provenance precision unchanged; CJ035 can consume the same
shapes while pinning the repaired source. Real execution remains unconditionally
unavailable. Canonical shared claim/cancel/current AUTH fence and trusted
scope/exit/receipt provenance are still missing, not patched by this parser fix.
Real provider, permissions, city quality, root integration, CI/device/deployment
and Issue13 acceptance remain UNRUN. Next is the original independent roles'
fixed-head recheck, not author self-approval or automatic release.
