# CJ-PLACE-GAODE@0.1.0-rc.1

CJ-012 / Issue 13 local candidate; source base
`8deb696f8149b4f5aa70c767be6c3a263b036227`. Independent Review/Testing pending.
This is an **internal Python consumption contract**, not published PLACE@1.0,
not an HTTP schema and not a second API. Root `contracts/api/openapi.json` remains
owned by CJ005. Consumers pin the candidate commit, not only this version string.

## Public surface

Import `cj_place` with `backend/place` on `PYTHONPATH`. The single definitions are
[models.py](../../backend/place/cj_place/models.py) and
[gaode.py](../../backend/place/cj_place/gaode.py); no copied DTOs are required.

- `Search(keyword, city, page, page_size)` explicitly scopes one search. Page size
  1–25 and the selected page end <=200 are this adapter's conservative bounds.
  Search requests use `citylimit=true`, `children=0`, Chinese response language.
  Result order and different provider IDs are retained; no name-based merging.
- `Detail(provider_id)` selects one exact POI identity; a returned different ID
  fails correlation. Parent/navigation IDs are retained separately, never used
  as replacements for the original POI identity.
- `Place` retains original `name_zh`, `address_zh`, center/entrance/exit coordinates,
  parent/navigation IDs and typecode. `Observed[T]` has `state` plus optional
  `value`: present/missing/empty_array/empty_string/null/invalid/unknown. Only
  present has a value. Required invalid ID/name invalidates the response;
  optional absent or invalid values remain explicit, with no fabricated data.
- `Coordinate` keeps exact provider text plus Decimal longitude/latitude and
  fixed `GCJ-02`. Numeric bounds/format do not prove a location is in China or a
  building exists. Actual `"0,0"` stays present; missing data never becomes zero.
  There is no conversion/rounding implementation. Route inputs require <=6
  decimal places; higher precision is refused, not silently rounded.
- `endpoint_from_place(place, role)` selects exactly poi_center/entrance/exit,
  preserving provider ID, role and exact coordinates. Missing/invalid selected
  coordinates fail. Two entrance POIs with separate IDs remain separate Places;
  an `entr_location` coordinate is NOT invented into an independent provider ID.
- `RouteQuery(origin, destination, mode, departure)` supports walking/driving.
  `Departure("at_query_time", None)` is explicit. A timezone-aware
  `Departure("specified_time", at)` is representable but preparation refuses it,
  past or future. No unsupported date is dropped or converted into "now".
- `Route` retains the entire original query and `Observed[Quantity]` distance and
  duration. Quantity preserves raw text, Decimal value, and m/s units. String
  `"0"` is present; numeric 0, missing, negative or malformed values do not become
  a usable measurement. Time semantics are provider_estimate_at_query_time;
  future_guaranteed is false. Driving strategy is fixed 10 in request binding.
- `Result` includes outcome, original query, fixed safe reason code, optional
  Source, immutable place/route tuples, provider code/count and contract version.
  `Source` includes provider/API version, credential-free endpoint, original
  request ref/digest, query start and receive times, evidence category. No
  provider update timestamp exists here; it stays None. **Carry Result.source
  alongside extracted Places/Routes**; values alone have no provenance/freshness.

Official English fields are unknown. Original Chinese is never translated or
normalized. English field/status names explain the parser result; they are not
provider-authored English place names or addresses.

## Preparation, parsing, and outcome meaning

`prepare(config, query, request_ref, started_at) -> PreparedRequest` is pure and
credential-free. `Config(origin, max_request_bytes, max_response_bytes,
timeout_seconds, max_age_seconds)` has no production defaults. Origin must be
exactly `https://restapi.amap.com`; only the four fixed v3 paths can be prepared.
The SHA256 binds complete query, IDs/roles/coordinates, mode/departure, parameters,
limits, request ref and start time. It is **correlation, not authentication**, not
a USAGE input digest and not an idempotency/dispatch permission. Do not replace
canonical RUN outbound bytes/digests with this digest.

`parse_response(config, request, response, *, now, evidence="unverified_bytes")`
recomputes the descriptor, checks exact envelope association, time/byte bounds,
HTTP/provider status, strict UTF-8 JSON, duplicate keys at every depth, JSON depth,
list/count structure, detail ID and route echoed coordinates. Numeric coordinate
formatting differences with identical Decimal values compare equal; original
request text is retained. Provider POI search does not echo the keyword/city;
route responses do not echo POI IDs/mode. Their binding comes from the **trusted
transport's association with the exact request**, not proof in provider JSON.
An arbitrary supplied body plus matching metadata is still unverified_bytes.

Elapsed time, query age and receipt/observation ordering compare actual UTC
instants after aware-time validation. Original timezone offsets/fold and datetime
objects remain unchanged in Source and request binding. DST clock transitions do
not extend deadlines or expire a fresh response. An instant outside Python's
representable UTC datetime range is invalid_response/response_time.

| Outcome | Consumer behavior |
|---|---|
| ok | Provider success with parsed entries; inspect every needed Observed field and source before use. It is not a complete-feasibility or truth claim. |
| no_results | Successful empty page/paths. A search page can be empty while provider_count >0; this does not assert the whole city has no matches. |
| rate_limited | Explicit documented quota/QPS error or HTTP 429; no retry here. |
| provider_error | Provider status 0 or non-200 HTTP including redirects; not no_results. Unknown error codes stay provider_error with original numeric code. |
| unknown | Transport exception/timeout or late response; no retry/zero-charge/never-dispatched inference. |
| invalid_response / binding_mismatch | Malformed/inconsistent payload or original-request correlation failure; no places/routes accepted. |
| stale | Query age exceeds explicit host maximum; no usable entries returned. Not proof of provider's own data freshness. |
| unsupported | Synthetic preparation rejects unsupported explicit departure. Pure prepare raises PreparationError. |
| unavailable | No configuration/fixture transport, or production dispatch remains closed. |

This deliberately narrow v3 profile accepts string status/count/numeric fields;
other types are invalid, not coerced. Optional fields retain unsupported/null
states. Missing `pois`, `route`, `paths`, required route coordinates, contradictory
success flags, duplicate identities or invalid counts are not empty success.
No parser failure returns provider prose, body, URL query or exception detail.

## Real execution boundary and minimal missing integration

`execute(query, *, config=None) -> Result` always returns unavailable. It takes
no token, caller owner, allow flag, fake budget or credentials. There is no HTTP
client, socket, environment lookup, retry, cache, persistent storage or Trip write.
Pure parsing never claims user authentication or usage settlement.

Read-only references at the fixed base: `AdmissionChecker.check(token)`, canonical
`Meter.reserve/claim/settle`, `UsageBinding(command_bytes, input_bytes)`, and
RUN's bound synthetic first-step composition. Current RUN documentation explicitly
keeps real dispatch closed pending shared claim/cancel/current AUTH fencing and
trusted exit/receipt provenance. PLACE does not copy or weaken those boundaries.

Minimal host seam still needed: CJ005/original domain owners must route one
**accepted canonical dispatch context + exact original bound input/attempt** to
an approved credential-injecting bounded HTTP transport. It must associate the
prepared request and response, enforce final URL bytes and response streaming
limits, timeout/TLS/host/no redirects, recheck current AUTH/cancellation under the
accepted fence, and reconcile unknown usage through the original attempt/receipt.
Those public dispatch-context/exit signatures are **not available at this base**;
this module does not invent a new Protocol/guard/token or infer them from IDs.
CJ005 may wire the pure functions after that seam is fixed; root API remains its
sole source. Real key/signature injection belongs only to that trusted host,
never App, request objects, results, logs or this candidate's stored input.

`cj_place.synthetic.run_synthetic(...)` provides one credential-free injected
**offline fixture** call with cooperative timeout/cancellation, no retries, and
synthetic evidence labeling. Arbitrary Python callbacks are not a sandbox; this
helper cannot stop blocking code or prove external non-dispatch. Do not register
it in a production host. It does not reserve/settle real USAGE.

## Samples, privacy and limits

Run [examples.py](examples.py) for fixed positive/negative consumers of the real
classes. [test_gaode.py](../../backend/place/tests/test_gaode.py) contains the
expanded deterministic fixtures. All names/coordinates/IDs are synthetic;
examples are not approved city/provider results. No account or credential used.

Private query/place data stays in memory. No provider cache/library or storage
license is assumed; real retention/cache/license approval is UNRUN. Real Gaode
permissions (including detail/multilingual access), city fit, network, costs,
AUTH/USAGE/RUN composition, CJ016/CJ035 consumer acceptance, UI, and all Issue 13
I/real-service acceptance remain UNRUN. Source/author tests do not close Issue 13.
