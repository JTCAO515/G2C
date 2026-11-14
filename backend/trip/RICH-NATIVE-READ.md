# Native rich read components for WP8

This C-owned component implements the already frozen `TRIP-structured-read.3`
representation. It does not install a new planning producer, source authority,
undo handler, HTTP4 shell or Hong Kong deployment.

## Explicit consumer

The server composes `Boundary(..., structured=True, calendar=True, rich=True)`;
`Repository` has the same opt-in. The original AUTH principal/scope resolver,
operation lifetime, role/GUC binding, scope transaction lock, final admission and
serialized-return checks remain. Changing rich mode during an operation withholds
the private result. A client cannot enable this by adding a query/body field.

`Proposal` recognizes canonical structured.4 **data**. Old repositories still
reject that representation before publish, direct source ingress and detail.
The rich read factory supplies no confirmation/source write grant. A real WP8
publisher must separately compose the genuine current MESSAGE/PlanNow/policy,
profile/Memory/NEEDS/Trip source holders with the original sole commit path.

## Read routes

`cj_trip.local_rich_read.register_local_rich_read_routes` explicitly registers:

- `GET /v3/trip-structured-list?after=...&limit=...`
- `GET /v7/trip-structured?trip_id=...`

They return read.3, preserving the original accepted content and canonical hash
for structured.1–4. Only 3/4 have calendar/day_count; old content is not labeled
undated or upgraded. The existing detail query/size/owner/expired/revoked guards
remain, including withholding the whole page after a late revocation. Existing
read.1/read.2 routes keep their wire tags and reject rich details.

Old keyset lists filter the explicitly unsupported **canonical structured.4**
before LIMIT. The byte prefixes come from the existing canonical encoder; they
only exclude a representation and cannot validate or admit a payload. Full
grammar/canonical checks remain in the repository read boundary. No PostgreSQL
JSON cast is used: its stricter Unicode conversion would reject otherwise valid
old strings such as an escaped NUL. Old formats and original bytes remain intact.
This routing applies to frozen canonical .4; any future format requires its own
explicit consumer rather than changing old bytes or guessing a fallback.

## Evidence boundary

Private PG read controls use real signed local identities, limited runtime roles,
actual proposals/confirmations/sole accepts and native read routes. The rich
storage ingress is a controlled reader fixture, not a qualified WP8 Source4
producer. Native rich generation/edit/date conversion/undo, actual profile and
Memory final fences, source collection, model/tool calls and deployment remain
UNRUN. Frozen message/trip versions, migrations, grants and authorization files
are unchanged. The combined WP8 slice still requires its exact-head redline
review; these local controls do not authorize a real write.
