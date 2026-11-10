# TRIP-lio-replan-delta.2

Owner C (#744). The Lio publisher requests this response when the signed
`TRIP-source-input.2` contains an adopted current Trip. The response contains
exactly `version`, `items` and `proposed_subjects`. A response with a `title`
field is invalid. The publisher copies the title from the same signed Trip
whose items it retains. The composed Trip still passes the bounded title check.

The rules for new and retained items, source and feasibility validation,
leases, deadlines, Meter and signed publication are the same as in
[TRIP-lio-replan-delta.1](LIO-REPLAN-DELTA-V1.md). An empty delta still publishes
a new version with the saved content. The frozen `.1` response continues to
validate its own explicit title. Initial plans and other NEEDS consumers retain
`TRIP-model-plan.1`.
