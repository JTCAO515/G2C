# CJ-034 instant-comparison P2 repair — author evidence

Parent/fixed failing candidate: `401d082bd2f0a47893f3049bf8e953229a68bb67`.
Original project base remains `8deb696f8149b4f5aa70c767be6c3a263b036227`.
Branch `cj/034-fact`; owned paths only `backend/fact/**`, `contracts/fact/**`.
This repair is fixed by its containing commit and `source-sha256.json` in this
folder. Original 401d evidence/source manifest are retained, not overwritten.

## Defect and minimal correction

Direct comparisons of aware datetimes with the same ZoneInfo compare wall times
and can ignore the repeated-hour fold. In the original independent synthetic
New York 2026-11-01 examples, an expiry at 05:45 UTC was incorrectly supported at
06:15 UTC, and a retrieval at 06:30 UTC was incorrectly supported at 05:45 UTC.
The original two probes were copied byte-for-byte from:
`<local>/Documents/Codex/2026-10-21/cj-testing/CJ-034-fact/independent_time_checks.py`.
Their exact source is retained in `backend/fact/tests/independent_time_checks.py`;
its hash is recorded in this folder's source manifest. Independent originals were
read-only throughout.

The only production-code delta is `cj_fact/model.py`: one UTC comparison-view
helper shared by future retrieval/publication checks, expiry and publication/
expiry validity ordering. UTC is never assigned back to the evidence. Original
datetime objects, offsets, fold, raw document bytes and exact excerpts remain
unchanged. Inclusive DateRange continues to compare source calendar dates.
No public shapes or version change. No acquisition, provider, authority or root
wire modifications.

## Actual results, existing CPython 3.14.7

- `independent-before.txt`: exact two independent probes **FAIL** on original401d,
  both wrongly supported. Preserved without changing assertions.
- `independent-after.txt`: same byte-identical two probes **PASS** after repair.
- `adjacent-controls.txt`: first 8 adjacent controls PASS.
- `affected-time-final.txt`: final **15 methods PASS**: 9 adjacent instant/metadata/
  calendar/JSON controls plus 6 original affected UTC/structured/validity methods.

New controls include both fold ordering directions for retrieval/publication/
expiry, valid and invalid publication-expiry ordering, equality across UTC and
fixed offsets, standard JSON extraction with ZoneInfo retrieval/query, preserved
source metadata, and a +14 calendar day differing from its UTC date. A true
source-local calendar date still matches; the UTC date is out of range.

Original independent45-method/9-consumer-case PASS evidence from401d is reused
for unchanged behavior. The acquisition module, original tests and public fixture
bytes remain identical to401d. No broad acquisition suite or consumer sample
rerun was performed for this timestamp-only correction.

Reproduction from repository root, offline:

```sh
PYTHONPATH=backend/fact:backend/fact/tests /opt/homebrew/bin/python3.14 -B backend/fact/tests/independent_time_checks.py
PYTHONPATH=backend/fact:backend/fact/tests /opt/homebrew/bin/python3.14 -B -m unittest test_time_instants test_fact.ApplicabilityTests.test_expiry_at_exact_boundary test_fact.ApplicabilityTests.test_future_observation_or_publication test_fact.ApplicabilityTests.test_same_values_and_stale_source test_fact.ApplicabilityTests.test_missing_publication_is_preserved_not_inferred test_structured.StructuredTests.test_explicit_fields_bind_to_exact_json_substrings test_structured.StructuredTests.test_invalid_typed_declarations_fail_explicitly -v
```

Author-local repair PASS; independent Review/Testing **pending**. Original401d
stays HOLD until the new fixed candidate is independently accepted. Real network,
provider approval, AUTH/USAGE/RUN dispatch, official wire/UI, account, database,
device, CI and release remain UNRUN/UNKNOWN exactly as in the baseline. No source
text, secret, authority, production configuration or calendar scope was invented.
