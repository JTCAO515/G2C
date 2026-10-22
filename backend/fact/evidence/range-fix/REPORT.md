# CJ-034 UTC range P2 repair — author evidence

Failing parent: `05d8683339d0ee6e7bd28eb03d01602a95e6b01d`.
Original base: `8deb696f8149b4f5aa70c767be6c3a263b036227`.
Branch: `cj/034-fact`; only `backend/fact/**`, `contracts/fact/**`.
This report's containing commit fixes the candidate; source hashes are in this
folder's `source-sha256.json`. Both old401d fold and05 conversion failures remain
preserved with their original evidence.

## Actual correction

At05, `astimezone(UTC)` on an allowed aware datetime whose UTC instant lies outside
Python's year1..9999 range raised an uncaught OverflowError. The exact independent
probe was copied byte-for-byte to `tests/independent_overflow_checks.py`, verified
against the original Testing file. `independent-before.txt` reproduces both
published_at/expires_at subcase failures. The exact raw output is preserved in
`independent-before.txt.gz` (SHA256 of decompressed original:
`523c33a74a721cefc4c75e4f043f6382837db78452e9aa021c7b054dd5fa67c2`). Its readable `.txt` copy only removes
trailing whitespace emitted by unittest, so the scoped diff whitespace check can
pass without discarding original bytes. `parent-control.txt` preserves Testing's
original401d control PASS; it was copied from the existing log, not rerun.

Only runtime change: `model.py`. `_instant` converts a range OverflowError to safe
ValueError `instant_out_of_range`, and the existing `aware` validator now verifies
representability for every Document/Query/Evidence timestamp. This covers optional
source fields even without the other validity endpoint. Existing structured
extraction catches that ValueError and returns its existing safe FactFailure
`invalid_structured_evidence`. Comparison calls remain defensive as well.
No catch-and-continue, fabricated validity, conversion to a different local time,
clamping or replacement source metadata. The existing UTC fold comparison fix and
source-local inclusive DateRange semantics are unchanged.

## Executed checks, existing offline CPython 3.14.7

- `independent-before.txt`: exact1 independent method, both subcases FAIL at05.
- `independent-after.txt`: exact same1 method/two subcases PASS after repair.
- `affected-final.txt`: **22 methods PASS**: prior17 affected instant/fold controls
  plus5 new range controls. No double-counting the original fold methods.
- New controls cover direct Document/Query construction, each manual optional
  Evidence timestamp alone, structured fields with no companion, lower/upper
  unrepresentable ISO offsets, and nearest representable UTC extrema through
  actual evaluate calls. Valid extrema preserve original offset/object metadata
  and return supported before expiry / expired exactly at expiry.
- No unrelated acquisition/network suite or original45/9 full rerun. Valid
  unaffected evidence is reused. Acquisition/policy/extractor, prior test/fixture
  bytes, original fold probes and logs remain unchanged.

Reproduction from repository root:

```sh
PYTHONPATH=backend/fact:backend/fact/tests /opt/homebrew/bin/python3.14 -B backend/fact/tests/independent_overflow_checks.py
PYTHONPATH=backend/fact:backend/fact/tests /opt/homebrew/bin/python3.14 -B -m unittest test_instant_ranges independent_time_checks test_time_instants test_fact.ApplicabilityTests.test_expiry_at_exact_boundary test_fact.ApplicabilityTests.test_future_observation_or_publication test_fact.ApplicabilityTests.test_same_values_and_stale_source test_fact.ApplicabilityTests.test_missing_publication_is_preserved_not_inferred test_structured.StructuredTests.test_explicit_fields_bind_to_exact_json_substrings test_structured.StructuredTests.test_invalid_typed_declarations_fail_explicitly -v
```

Author-local repair PASS; original independent Review/Testing pending.05 and401d
remain historical HOLD candidates. Production entry still closed; real provider,
AUTH/USAGE/RUN, root wire/UI, source approval, account/DB/device/CI/deployment remain
UNRUN/UNKNOWN. No global configuration, permission, external resource or shared
module was changed.
