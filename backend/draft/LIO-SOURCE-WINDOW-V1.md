# LIO-source-window.1

Owner C, #815. This is an additive, host-selected publication policy for a
single-destination itinerary. It does not change a frozen model response,
NEEDS field, Trip document, confirmation, Meter, or HTTP version.

The host selects `cj_draft.lio_plan.LioSourceWindowPublisher` explicitly.
Its constructor and public publication methods are inherited unchanged:

```python
publisher = LioSourceWindowPublisher(
    context_publisher, confirmation, original_needs, check_lio_original,
    draft_guidance=draft_guidance,
)
```

The nationwide lane must not fall back to `LioPlanPublisher` after a rejection.
The original publisher and all its frozen formats remain available to existing
explicit consumers. Returning an older accepted model format cannot bypass the
new policy once the host has selected the new publisher.

## Required source and publication checks

Consume the same protected, immutable `TRIP-source-input.2` capture. The existing
NEEDS fields must contain known `arrival.date`, `departure.date`, and
`destination_timezone`. Both bound events must use that same known timezone.
Arrival must not follow departure. A bound's clock may remain unknown; no
midnight, reservation time, observed UTC offset, or city-derived field is filled
by C.

Immediately before the inherited save path, for every candidate activity:

- A known local date must lie within the inclusive source date window.
- A known timezone must equal the source's canonical destination timezone.
- If existing explicit-time resolution determines an arrival/departure instant
  and the activity instant, the activity must also fit those time bounds.
- Unknown original fixed fields stay unknown. They are not promoted to known
  values. Existing source/fixed-item, selected-scope and new-suggestion interval
  validation remains in force.

This single save-boundary check covers planning and the existing text-replacement
publication route. A contradiction refuses publication with the original
`DraftRejected` semantics and field/rule diagnostic. It does not repair, move,
remove, or normalize a locked or adopted item. The inherited leases, original
action reconciliation, signature, financial deadline and sole Trip transaction
still perform the commit. No database write occurs in the new check.

If an existing source or adopted Trip contradicts a new destination window, the
host must clarify or select the correct new planning context. The delta format
still retains saved items and title; it is not a cross-city reset operation.
Overseas travel facts remain their original source fields; this policy is not a
claim to support a mixed-timezone itinerary as a single destination. The original
undo path retains its source-version, fixed-item and historical-content gates.

## City and place boundary

C has no Beijing whitelist or city resolver. The host must first resolve the
user's intended city and ambiguity against its administrative source, and bind
the result to the original user messages. `arrival.place` may retain the
confirmed canonical name. B's versioned `city_ref` evidence must not be inserted
as an unsupported key into frozen NEEDS fields.

Real PLACE choices continue to require the exact offered choice ID, provider
name, original query and source snapshot. A same-name place or an English alias
does not confer source authority. Compact Lio suggestions still have pending
verification and unknown source; this policy does not certify a POI, booking,
opening hour, price, transport route or overall feasibility.

## Evidence scope

Synthetic six-city/source/window regressions validate this policy and keep old
negative cases. Existing signed private-PG publication/undo suites validate the
inherited path. B must separately exercise its explicit nationwide integration,
deploy the same source, and provide a real test window. Local results are not
public planning acceptance. The public bilingual scenario set is
[`eval/lio_national_cases.v1.json`](../../eval/lio_national_cases.v1.json).
