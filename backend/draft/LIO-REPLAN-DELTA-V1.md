# TRIP-lio-replan-source.1 / TRIP-lio-replan-delta.1

Owner C (#744). Internal Lio model input and response formats for a planning
request with an adopted current Trip. Initial Lio planning and existing
NEEDS consumers retain their existing frozen input and output versions.

`TRIP-lio-replan-source.1` uses the `TRIP-source-input.2` fields with a distinct
version and a `response_version` of `TRIP-lio-replan-delta.1`. The current Trip
is read from the signed source selection and carries its existing version,
content and proposed fields. The response has exactly `version`, `title`,
`items` and `proposed_subjects`. Its item list contains new suggestions and
newly declared required NEEDS items absent from the current Trip. An empty
list and empty subject map are valid when the current items cover the request.

The publisher uses the current Trip's canonical items in their saved order
and appends the returned items. Reusing an existing item ID rejects the
candidate. A retained nonempty source list is refused because this planning
path has no corresponding source projection. The same structured.2 shape,
scope, source and feasibility checks run over the composed candidate. New
suggestions still require same-day ordered start and end times in the same
known timezone and follow the original unknown-source rules.

The original source lease, current Trip selection, final deadline, Meter,
signed action and single-version publication checks remain in force. The
model response cannot authorize a change or supply new approval evidence.
Replanning still makes its registered model call under the existing limits.
The frozen full-plan response remains available to its existing callers and
continues to reject missing or altered protected items.
