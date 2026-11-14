# Rich itinerary presentation — WP11 #934

Consumer target: WP7 #930 / PR954, `structured.4` and `TRIP-structured-read.3`.
This preparation adds display values and native views only. It does not register
HTTP endpoints, decode untrusted JSON, authorize sources or change the current
Trip library. Normal Beta/Production still use their accepted readers. WP8's
protected rich runtime must be deployed before real integration.

## Mapping

| Validated value | Native presentation |
| --- | --- |
| title, calendar, days with continuous day_index/date | Title, date-not-set label, day selector; explicit rest days remain visible |
| day.theme / area | Day heading and neighbourhood subtitle |
| ordered items + kind | Numbered cards; camera, meal, bed, tram, leaf symbols with text labels |
| place.name_zh / name_en | Chinese name in both languages; English display name does not claim an official translation |
| place.state + original coordinate/role | Matched original GCJ-02 points only; no conversion, lookup, SDK or new provider request |
| place.address | Chinese driver card only when an actual matched address is available; otherwise disabled with a readable explanation |
| item.text / note / tip.text | Short reason, detail note, practical tip; no model-derived source permission |
| consecutive legs | Mode + approximate minutes/km from validated estimates; missing route has no invented mode, distance or duration |
| lodging.area / recommendations | Area and 2–3 recommendations; no price, availability or reservation fields |

`LioRichItinerary` is a module-internal view value. A future adapter must map only
an accepted protected read with the matching Trip ID, revision and content hash.
The data value and its matched flag cannot grant a read, write, undo or factual
source. Source/provenance checks belong at the existing HTTP/Trip boundary.
No new `AcceptedStructuredTripSnapshot` can be manufactured from this display.

## Interaction

Tap a numbered stop for notes/tips and the driver action. The driver card uses
large Chinese name/address text and supports text selection. A missing address
never becomes an actionable invented destination. Hotel recommendations remain
suggestions and do not display booking or price state.

Maps use the existing `LioRouteMap` snapshot renderer, moved without behavior
changes into its own file for reuse. Opening the map is explicit and explains
Apple's map-area disclosure. Missing points do not change the other stop numbers;
list positions 1 and 3 stay map numbers 1 and 3. Loading failure leaves the whole
schedule available. Day changes clear the displayed map and focus.

## Acceptance boundary

The simulator fixture uses demonstration names and coordinates. Map failure is
injected through the existing Debug-only delegate seam, with no tile/provider
request. It proves display/interaction and failure handling, not a loaded basemap,
provider correctness or live source eligibility. Ordinary message/Trip readers and all existing acceptance assertions are retained.
Legacy .1/.2 keep their existing path; explicit .3 integration belongs to #863.
Combined .1–3 compatibility, protected rich runtime integration and JT's G12
remain pending; this display-only preparation does not claim those passes.
