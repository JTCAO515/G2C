# TRIP structured.3 / structured-read.2

#860, parent #859. Additive calendar representation; runtime enablement belongs to
#861/#862/#863. Old content, protocols, signatures and stored histories are unchanged.
See [design](../../backend/trip/UNDATED-V3-DESIGN.md),
[content schema](structured-schema.3.json), [examples](structured-examples.3.json),
[read schema](structured-read-schema.2.json), [read examples](structured-read-examples.2.json).

`calendar.state=undated` has no start_date and every day has only a continuous positive
day_index. Dated has an explicit ISO start_date and each day's date equals start+index−1.
The content's items retain stable IDs and source/fixed observations; schedule endpoints
refer to day_index and explicit time/timezone/offset observations. Missing is never today.
Legacy unknown calendar observations are never reclassified as this new undated mode.

Date checks distinguish not_checked/unknown/clear/conflict. Undated weather and day_opening
are not_checked/date_not_set. A clear/conflict claim needs original evidence, and the
protected producer must attest provenance; a schema validator does not verify weather,
opening hours, booking, feasibility, identity or write authority.

GET `/v2/trip-structured-list` and `/v6/trip-structured` use TRIP-structured-read.2.
Summaries retain ID/version/content hash and add calendar/day_count: structured.3 has
explicit values, legacy1/2 have null, meaning **legacy**, not undated. Detail retains exact
original content and its canonical SHA. Old endpoints cannot silently convert or flatten
new content; they remain explicit old capabilities. The new read is owner-protected data,
never a commit token. Byte caps, pagination, fresh AUTH and protected encoding remain.

Conversion appends a new version; fixed items/source/time/order are retained. Hard fixed
date conflicts prevent a contradictory commit, while evidence-backed availability conflicts
are returned without automatically rearranging the plan. Undo appends a version restoring
the complete prior content, with current source/identity protection; old undo is not widened.

`check_structured_v3.py` is an **offline contract checker**. It tests shape plus ordinal,
calendar arithmetic, references and canonical detail digest; it reuses the unchanged old
field grammar on a private validation copy. It is not a new publisher or runtime adapter.
The old format hashes and old positive/negative behavior remain. No migration is needed.
