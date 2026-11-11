# Compact Lio draft responses

Lio selects a model response format from the same captured `TRIP-source-input.2`
used at publication.

| Captured Trip | Response version | Exact fields |
|---|---|---|
| Absent | `TRIP-lio-first-plan.1` | `version`, `title`, `items`, `proposed_subjects` |
| Present | `TRIP-lio-replan-delta.3` | `version`, `items`, `proposed_subjects` |

Each returned item is a new suggestion with exactly `id`, `text`, `date`,
`start_time`, `end_time` and `timezone`. A suggestion uses one local ISO date,
explicit local times, and an IANA timezone. `proposed_subjects` maps each new ID
to its explicit participant list. An empty suggestion list has an empty map.

The publisher adds fixed items from the captured NEEDS by original ID, text,
schedule and locked state. An adopted Trip retains its title and items in their
saved order. A new fixed item is appended only if its ID is absent from that
Trip. New suggestions carry pending verification, unknown UTC offset and
unknown source. The composed candidate uses the existing structured, source,
time, feasibility, lease and signed publication checks. Duplicate IDs and
unsupported fields are rejected. An empty delta may save the existing content
as one new version through the same publication path.

The frozen full-plan format and previous Lio delta formats remain accepted in
their original contexts. The model output limit and shared Meter are unchanged.
