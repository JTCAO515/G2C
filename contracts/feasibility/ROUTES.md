# PLACE query-time estimate consumer candidate

`CJ-FEASIBILITY-ROUTE-ESTIMATE@0.1.0-candidate.1`, CJ-035 / Issue 18.
This is the next local slice after NEEDS-only firstfixed
`a862a82504eae47ae5c44c13a45d34ae4edfeb03`. It does not modify NEEDS or PLACE.
Consumer source: `backend/feasibility/cj_feasibility/routes.py`.

## Exact dependency, not a copied schema

Pins PLACE commit `dd4c375a731bbaef1d436bc3e88466040ac02294` and imports
`cj_place.Result/Route/Observed/Source` and the existing request/config/query
classes directly. No vendored/copy DTO, provider request or alternate route
schema. The author's PLACE checkout had already moved to ec2d0a6 (evidence-only
diff); testing instead used `git archive` of the exact dd4c375 commit in a fresh
temporary directory. `routes-manifest.json` records consumed file hashes.

**This fixed Source only allows `synthetic` and `unverified_bytes`.** There is no
verified transport category or supported specified-time query. This slice can
therefore return an exact **conditional numeric relation**, but cannot prove a
real route duration, real conflict or real feasibility. No boolean/caller-provided
trust label can promote it. Invented evidence categories are INVALID.

## Public function and explicit constraint selection

```python
from cj_feasibility.routes import Window, assess_route

window = Window(
    origin_item_id, destination_item_id, selected_place_route_query,
    explicit_buffer_observed_quantity, explicit_rest_observed_quantity,
)
assessment = assess_route(
    before_snapshot, original_revisions, proposed_candidate, window, original_result,
    route_index=explicit_index, request=original_prepared_request,
    config=original_place_config, as_of=explicit_aware_datetime,
    selected_fields=explicit_frozenset, selected_item_ids=explicit_frozenset,
)
```

`Window` is a selected pair of candidate NEEDS fixed-item IDs, the actual PLACE
`RouteQuery` and explicit buffer/rest. It does not recreate a PLACE endpoint:
IDs, GCJ-02 coordinates, coordinate roles, mode and departure remain in the
original typed query. The time window is exactly origin item's end to destination
item's start. Both items must exist, differ and have a shared explicit applicable
subject and known noncancelled booking declarations. Missing/ambiguous event
instants are UNKNOWN, never a device-zone/default date. A cancelled item does not
impose travel. Hotel/intent occupancy is not inferred here; the caller explicitly
selects this end-to-start leg.

The item-to-PLACE endpoint mapping is an **explicit input declaration**, not a
fact inferred from NEEDS free-text `place` and not independent verification.
`ROUTE_ENDPOINT_MAPPING_DECLARED/UNKNOWN` keeps the missing confirmation visible.
No endpoint search, name matching, coordinate conversion or implicit entrance
fallback is performed. Future trusted mapping integration remains a separate gate.

Buffer and rest reuse actual `Observed[Quantity]` with seconds unit `s`. They
explicitly reserve **separate additive amounts of this gap**, as selected by the
caller, not inferred from `pace` or condition text. Unknown/missing/null/invalid
observations are not zero. Even zero must be `present/Quantity('0', Decimal('0'),
's')`. Numeric raw text must exactly represent the nonnegative Decimal under the
pinned quantity bounds; unit mismatches and malformed values are unusable.

## Original evidence and policy preserved

`RouteAssessment` is frozen and holds the exact original `Result` (including
Source), Window/RouteQuery, PreparedRequest, Config, proposed Candidate, route
index and explicit `as_of`; it does not strip a duration into an anonymous number.
Its `protection` is the existing pre-write NEEDS invariant result. The same
unselected/locked/unknown-lock protections run first; a withheld protection stops
route arithmetic. No candidate or domain object is modified.

The function recomputes PLACE `prepare(config, window.query, original_ref,
original_started_at)` and compares the complete prepared descriptor, original
Result query and version. It checks the source endpoint/provider/API/ref/digest/
start against that original request. It does not mistake this correlation for
transport authenticity. Selected route must retain the same complete query,
`provider_estimate_at_query_time` and `future_guaranteed is False`. An explicit
index is required; no first-route fallback and no averaging route alternatives.

Freshness policy is the explicit original `Config.max_age_seconds`, already part
of the PLACE request digest; there is no default freshness/TTL. Query start <=
receipt <= as_of must hold. Age is exact `as_of - query_started_at`, using integer
seconds/microseconds and Decimal, never a float-derived trip duration. The
inclusive max-age comparison does **not** establish provider data freshness:
provider_updated_at remains None. Age and policy, original ref/digest and evidence
category remain in the checks as well as the retained original objects.

Only a candidate departure **exactly at the original query instant** is presently
time-comparable for conditional arithmetic. A different past or future departure
is UNKNOWN, even if the source is young. Specified-time departure is unsupported;
it is never silently changed to now. This intentionally narrow condition has no
invented speed, departure tolerance, buffer or future-guarantee assumption.

## Result semantics and codes

`RouteAssessment.status` is INVALID before CONFLICT before UNKNOWN. Any CONFLICT
here comes from the independent NEEDS protection guard, not synthetic route data.
This slice never returns overall PASS/feasible or route-proven real impossibility.
`conditional_relation` is None, `required_exceeds_gap` or `required_within_gap`.
It compares only the supplied estimate under the recorded assumptions:

`required_seconds = estimated_duration + explicit_buffer + explicit_rest`

`gap_seconds = candidate_destination_start - candidate_origin_end`

All arithmetic has its own Decimal context, exact across allowed quantity/date
bounds regardless of ambient precision/exponent settings. A 3600-second estimate
exceeds a 900-second gap; a 900.000001-second requirement also exceeds that gap.
This is a mathematical counterexample **conditional on the inputs**, not proof
that synthetic travel took an hour. Equal amounts fit the arithmetic boundary;
the route's actual future applicability remains unproven.

| Code | Conclusion |
|---|---|
| ROUTE_PROTECTION_WITHHELD | Original candidate protection did not pass; no route arithmetic |
| ROUTE_ENDPOINT_MAPPING_DECLARED | Explicit mapping supplied; independently confirmed mapping missing |
| ROUTE_WINDOW_TIME_UNKNOWN | Candidate event date/time/zone/DST instant unresolved |
| ROUTE_SUBJECT_UNPROVEN / ROUTE_ITEM_ACTIVITY_UNKNOWN | No proven shared subject or active item declaration |
| ROUTE_DEPARTURE_UNSUPPORTED | Fixed PLACE cannot query the specified departure |
| ROUTE_QUERY_BINDING_UNKNOWN / ROUTE_SOURCE_BINDING_UNKNOWN | Query/descriptor/version/source not bound to the exact selected input |
| ROUTE_RESULT_UNAVAILABLE / ROUTE_SOURCE_MISSING / ROUTE_SELECTION_UNKNOWN | No usable original result/source/explicit route selection |
| ROUTE_SOURCE_TIME_UNKNOWN / ROUTE_SOURCE_STALE | Timestamp order or explicit query-age policy not met |
| ROUTE_QUERY_AGE_CHECKED | Local age comparison passed; no authenticity or provider-update claim |
| ROUTE_EVIDENCE_UNVERIFIED / ROUTE_EVIDENCE_CATEGORY_INVALID | Synthetic/unverified only; invented trust label invalid |
| ROUTE_FUTURE_APPLICABILITY_UNKNOWN | Candidate departure differs from query instant; no extrapolation |
| ROUTE_VALUE_BINDING_UNKNOWN | Selected Route has wrong query/time semantics/future claim |
| ROUTE_REQUIRED_SECONDS_UNKNOWN | Duration/buffer/rest lacks an explicit usable seconds quantity |
| ROUTE_CONDITIONAL_WINDOW | Exact conditional relation and component amounts, still UNKNOWN |
| ROUTE_INPUT_INVALID | Malformed explicit objects/times; stable safe diagnostic |

Every Check carries the same bilingual decision structure as the NEEDS slice.
Raw input/Source/query remains private; don't publish the dataclass or log it as
public telemetry. No persistence/cache/retention promise is added.

## Reproduction and acceptance boundary

Use an isolated checkout/export of the exact PLACE commit, keeping it outside
this repository. Let `PLACE_EXPORT` point to its export root; then from this repo:

```sh
PYTHONPATH="$PLACE_EXPORT/backend/place:backend/feasibility:backend/needs:backend/auth" python3.14 -m unittest discover -s backend/feasibility/tests -p test_routes.py -v
PYTHONPATH="$PLACE_EXPORT/backend/place:backend/feasibility:backend/needs:backend/auth" python3.14 backend/feasibility/route_demo.py
```

The demo calls the actual PLACE `prepare/parse_response` on synthetic bytes,
constructs actual NEEDS objects, supplies explicit zero buffer/rest and reports
3600 > 900 with overall UNKNOWN. Tests exercise actual PLACE classes and original
query/Source retention, every nonpresent duration state, wrong IDs/roles/GCJ02/
mode/digests, stale/timestamp/departure anomalies, buffers/rest/decimal precision,
protected edits and failed trust promotion. No actual provider call.

NEEDS-only 29-test evidence is reused unchanged; new route tests are separate.
Independent Review/Testing, trusted exit provenance, confirmed candidate endpoint
mapping, true route evidence at candidate departure, provider/PG/root API/App,
full rest/cost integration, OR-Tools/bounded solving and Issue 18 I gates remain
UNRUN. No empty solver adapter is added: the fixed evidence cannot support a
real-world solution or its independent invariants yet. Owner confirms only this
fixed PLACE consumer interface and its synthetic/conditional behavior.

## Offset audit follow-up: upstream dependency remains HOLD

Main reported the fixed dd4/ec2d PLACE elapsed-time/freshness P2 HOLD. This
consumer remains pinned to dd4; upstream repair has **not** been consumed or
accepted. A later fixed upstream repair must receive separate consumer attribution.

Own NEEDS `_instant` maps unique wall date/time/zone values to UTC, and keeps
ambiguous/nonexistent wall times UNKNOWN. Own route window/age/receipt order
already normalize to UTC before subtraction/comparison. Calendar date declarations
remain unmodified: a date label is not an instant or elapsed duration. Across US
fall/spring DST, unique 00:30→02:30 / 00:30→03:30 windows yield 10800 / 7200 seconds.
No fold is guessed to make an ambiguous NEEDS event usable.

The audit found and fixed one separate consumer correlation defect: source
`query_started_at` equality against the original request directly compared aware
datetimes and could treat different folds of the same ZoneInfo as equal. That
check now reuses existing `_aware()` and compares **UTC instants**. Before the
fix, substituted fold start could incorrectly produce QUERY_AGE_CHECKED; aggregate
still remained UNKNOWN and no real evidence was promoted. Original FAIL logs are
preserved; new targeted offset tests plus affected route tests pass. This local
fix does not repair PLACE or release its freshness/chronology dependency HOLD.
