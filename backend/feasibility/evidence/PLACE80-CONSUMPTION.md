# CJ-035 separate fixed PLACE time-repair consumption

NEEDS firstfixed: a862a82504eae47ae5c44c13a45d34ae4edfeb03 (unchanged).
Route firstfixed: 95b65afbce6ea14367652d6a49199450da9fe55c (preserved).
Own binding fix: 2634ccd0b2e914271cbbb376cfdf074982512e4f (preserved).
This delta consumes PLACE 80ba4ae5527875ce375d22f3439f8e3256e2c4d6 only after that
local fix. The source's parent is ec2d0a6. Source directory is read-only; extracted
exact commit to a new temporary directory via git archive and never imported the
moving tree. Typed models.py is byte-identical to original dd4; gaode.py changes
only UTC instant normalization/elapsed/age/order handling. No upstream source,
shared files/locks/config or duplicated DTO/time wrapper changed here.

## New targeted evidence (author only)

Existing CPython 3.14.7; original PLACE types and parser; synthetic bytes only.
With PLACE_EXPORT pointing at the exact 80ba export, run from repository root:

```sh
PYTHONPATH="$PLACE_EXPORT/backend/place:backend/feasibility:backend/needs:backend/auth" /opt/homebrew/bin/python3.14 -m unittest discover -s backend/feasibility/tests -p test_place_repair.py -v
PYTHONPATH="$PLACE_EXPORT/backend/place:backend/feasibility:backend/needs:backend/auth" /opt/homebrew/bin/python3.14 -m unittest discover -s backend/feasibility/tests -p test_route_offsets.py -v
```

`place80-consumer-time.txt`: 6 PASS. Five actual parser→consumer time cases and
one exact pin check. Stale age, deadline elapsed and receipt chronology across
fold now cause parser STALE/UNKNOWN/INVALID_RESPONSE respectively; consumer
withholds arithmetic and never marks age/association PASS. Spring jump two-second
actual response remains OK despite ~one-hour wall-label change. Valid fold1
Source identity/offset remains original while own comparisons use UTC. There is
**no injected OK outcome** in these integration cases (`consumer_boundary=False`).

`place80-own-offsets.txt`: 4 PASS. Preserve independent local guard coverage
using explicitly injected actual typed synthetic results if upstream now rejects
first; helper marks reason synthetic_consumer_boundary_probe. Source remains
synthetic. This is a boundary fixture, never evidence that the repaired parser
accepted it. Original assertions still prove own 3602-second age, receipt-order,
wrong-fold source association rejection and fall/spring gap arithmetic. Separate
genuine-parser cases above prove upstream withholding. No old FAIL deleted.

Own production source delta is only PLACE_COMMIT; no algorithm change. Original
17 route-rule tests and NEEDS-only 29 source/tests/evidence are unchanged and
reused; no broad suite, upstream suite or service run. Staged whitespace PASS.
`place80-manifest.json` records this delta and fixed consumed files; historical
manifests/logs retain their original fixed attribution.

## Gates

Local author time-family consumption PASS. Upstream independent Review/Testing
and Main's HOLD resolution remain pending, not cleared by this report. All
Source.evidence still synthetic/unverified_bytes; real transport/date applicability,
confirmed item-endpoint mapping, provider/PG/root API/App/solver/Issue I gates
remain UNRUN or UNKNOWN. No real route/feasibility claim, no push/PR/merge/deploy,
no provider request, secret access or domain write.
