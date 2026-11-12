# MESSAGE trip-schema.2 / LIO calendar contracts

#860 freezes new types in [trip-schema.2.json](trip-schema.2.json) and synthetic
[examples](trip-send-examples.2.json). Core MESSAGE send.1–4, trip-schema.1,
scoped-edit versions and applied migrations are unchanged. No send.5 is introduced.
Consumer agreement: #860/6819228034 (L), 6818480818/6819064617 (A), 6818540981 (B platform).

| New type | Purpose |
|---|---|
| TripSelection2 | id/expected_version/day/item_id. Undated day_index, optional genuinely known timezone; dated date+timezone. Mixed modes rejected. |
| LIO-trip-reference.1 | Protected original canonical MESSAGE identity/hash plus actual Trip ID/version/content hash and selection. Not authority. |
| LIO-message.3 / receipt.3 / lookup.3 | Same text/locale/MID/CID/new_conversation envelope, explicit new capability at /v3/lio/messages. |
| LIO-trip-card.2 | Actual trip_version/content_version/hash plus calendar/days/date_checks. Includes empty rest days. |
| LIO-timeline.3 / LIO-trip-history.3 | New card projection at /v3/lio/timeline and GET /v3/lio/trip, preserving cursor/undo_target. |
| LIO-trip-undo.3 / receipt.3 | Explicit new undo capability at /v3/lio/trip-undos and /v3/lio/trip-undo-receipts; original target/action query semantics retained. |
| TRIP-date-convert.1 / receipt.1 | Internal source-bound deterministic conversion; no new direct client write route. |
| LIO-fixed-day-bindings.1 | Protected NEEDS version/hash and original-message-backed start/end day indices. Not a new NEEDS field. |

The trip reference's input_sha256 is the original canonical MESSAGE digest. It is **not**
the digest of the outer LIO envelope. Source quotes must occur in the protected actual
original, with original generation/sequence/RUN; later replies cannot reanchor question_day.
The producer must check these through its real scoped reader, not client-provided claims.

Fixed bindings contain item_id/day_index/end_day_index/quote/source_reference. Both endpoint
indices are explicit (same for a same-day constraint); cross-day needs explicit original
evidence. The protected compiler and C must agree on the ordinal and complete original fixed
item coverage. Missing/ambiguous/foreign/stale mappings are unresolved/conflict, not day1,
not participant labels, and not permission to drop the fixed item.

The conversion receipt binds action_id/trip_id/original_version/original_hash. Converted
means committed=true, exactly basis+1 and the actual committed content hash/calendar/checks.
A hard fixed-date conflict has committed=false and no new-version/hash. Unknown has
committed=null and no asserted new state: reconcile the same action, never replay. A soft
date-dependent conflict may commit only with its actual check evidence also returned in
conflicts. Unknown check facts are never defaulted to clear. Provider/fee UNKNOWN continues
to follow the original registered-attempt/hold/stop rules; a check-state label cannot bypass them.

Legacy card content1/2 uses calendar/date_checks=null and its old date grouping; never
normalize it to structured.3. New .3 cards follow all explicit days and keep stable IDs,
times, fixed values and original content hashes. A card is a summary, not reconstruction of
the full authoritative content. Old .1/.2 endpoints reject unsupported new content instead
of a silent protocol fallback. The new undo receipt is an observation, not a retry grant.

`check_trip_v2.py` checks schema and explicitly synthetic protected-read correlations.
Its fixture receipts/compiler outputs are **not a production trust source**. Actual AUTH,
RLS, current-source checks, leases, canonical raw-byte reads, HEAD CAS, original signer,
sole commit, cancellation and budget fences remain mandatory in #861/#862. Read/schema
success is not factual or publishing PASS. Unknown outcomes and all prior negative records
remain. No real provider, resource, permission, key or migration change is part of #860.
