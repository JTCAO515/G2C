# TRIP-structured-read.1 — C owner freeze

Additive discovery/read contract for #21/#286. Existing /v1/trips,
/v3/trip-structured and /v4/trip-structured remain exact, single-ID endpoints.
They do not provide this discovery contract. No old content is converted.

Explicit CJ_ENV=local composition:
`cj_trip.local_structured_read.create_local_structured_read_app(conninfo_path=...,
auth_dir=...,run_context=<original CJ-LOCAL-RUN@2>)`. Canonical AUTH checker,
owner→original Trip scope and original protected OperationContext/Repository
provide RLS and fresh admission through encoding/return. Scope provisioning only
uses the original host pattern; no Proposal, receipt or formal Trip is created.
No new role, schema, permission, writer, or model/provider call is added.

GET `/v1/trip-structured-list`: optional `after` (original Trip ID, empty first
page) and `limit` (ASCII 1–100, default20), no other or duplicate query fields.
Result keys exactly `version,request_id,trips,next_after`. Version is
`TRIP-structured-read.1`; each summary has `trip_id,version` (positive committed
Trip version), `content_version` (structured.1/structured.2), `title`,
`content_sha256` (original canonical content SHA256).

Only actual formal cj_trip_record rows are scanned, in original bytewise ID
order, after exclusive cursor. Pending/rejected Proposals are never discovered.
Legacy/provenance records are skipped rather than relabelled structured. The
cursor advances over *all scanned records*: an empty structured page may still
have next_after. Continue until next_after=null; an exact-size final page can
require one final empty page. No transaction-spanning snapshot is promised;
concurrent new/changed data requires an explicit refresh and current detail.

GET `/v5/trip-structured?trip_id=...`: exactly this one query field. Result keys
`version,request_id,trip`. Trip=null when missing, foreign or non-structured;
otherwise `trip_id,version,content_sha256,content`, preserving full canonical
structured.1/2 observations and stable item IDs. No text/date/timezone inference.
The returned hash/version is an observation, not a publish/save authorization.

Missing/malformed token follows the original401 ACCESS_DENIED; malformed query
400 INVALID_INPUT; denied/unknown/expired/revoked/dependency/encode/size failure
503 TRIP_UNAVAILABLE with retry_safe_read. Private bytes are fully encoded within
the original protected lifetime, default response cap1000000 bytes. No partial
page or stale bytes are returned on failure. Local host rebuild reads the same
formal table, without injected Trip or a second read store.

For B #330 the authoritative backend source remains `cj_trip_record` under the
canonical owner-derived Trip scope: exact Trip ID/version/content hash, item IDs,
explicit `schedule.start/end.date/time/timezone/utc_offset` and fixed observations.
A response DTO is not authority: producer validation must use its own current
protected read, original identity and final currentness/publish seam. Travel
context identity is a different namespace and cannot substitute for formal Trip.
App and B MESSAGE fields/new versions are owned by their respective lines.
