# CJ-035 own fold/offset audit; PLACE dependency HOLD retained

Original NEEDS firstfixed: a862a82504eae47ae5c44c13a45d34ae4edfeb03.
Original route fixed: 95b65afbce6ea14367652d6a49199450da9fe55c.
Both remain intact in history; NEEDS source/tests unchanged. PLACE pin remains
exactly dd4c375a731bbaef1d436bc3e88466040ac02294, using the original isolated
export; no moving-source import, copied wrapper or upstream edit. Main's report
that dd4/ec2d has a chronology/freshness P2 HOLD is not cleared by these checks.

## Actual consumer finding and fix

Existing NEEDS unique instants and route window/age/order calculations use UTC.
Targeted tests confirm true 3602-second query age despite 2 wall-label seconds,
receipt-before-query despite increasing wall labels, and true elapsed 10800/
7200-second fall/spring windows with individually unique local endpoints.

One actual local defect: routes.py compared original request.started_at and
Source.query_started_at directly. Same ZoneInfo and wall labels but fold0/fold1
could compare equal despite being different instants. A Source with substituted
fold start incorrectly reached QUERY_AGE_CHECKED (using the substituted instant),
though later applicability/evidence gates kept overall UNKNOWN. Fix reuses the
existing `_aware()` UTC conversion for **that equality only**. No new wrapper,
NEEDS change or datetime/calendar normalization elsewhere.

## Exact retained evidence

- route-offsets-before.txt: 4 probes, 2 PASS/2 FAIL. One FAIL was the actual binding
  defect; the other was a test-fixture issue: PLACE's original 3-second timeout
  correctly withheld a 60-wall-second receipt before own chronology code ran.
- route-offsets-before-fixture-corrected.txt: explicit synthetic timeout set to
  4000 seconds so the original dd4 parser yields a result; 3 PASS/1 FAIL isolates
  the actual source-start fold equality defect before code fix.
- route-offsets-after.txt: final 21 PASS = four new offset test methods (five DST/
  chronology/binding scenarios) plus the affected 17 route tests. Original test
  names/assertions were not weakened; only the explicit synthetic fixture timeout
  changed to reach the intended gate. Prior FAIL files retained unchanged.
- NEEDS-only 29-test evidence reused; that source/test code is byte-unchanged.
- Staged whitespace check PASS. No broad tests or upstream suite rerun.

With PLACE_EXPORT at the original exact dd4 export root:

```sh
PYTHONPATH="$PLACE_EXPORT/backend/place:backend/feasibility:backend/needs:backend/auth" /opt/homebrew/bin/python3.14 -m unittest discover -s backend/feasibility/tests -p 'test_route*.py' -v
```

This is author-only local synthetic evidence. Independent Review/Testing remains
pending. New upstream repair consumption UNRUN; PLACE freshness dependency HOLD;
real-provider/root API/PG/App/bounded solving/Issue I gates remain UNRUN. All source
and evidence changes are within backend/feasibility and contracts/feasibility;
no push/PR/merge/deploy, key access or domain writes.
