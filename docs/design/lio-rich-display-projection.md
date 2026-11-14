# Rich itinerary display projection

Refs #934 / #922. The frozen structured.4 data decoder now feeds the existing
rich itinerary view model. This projection consumes validated document fields;
it creates no protected read, source eligibility, accepted editor or write action.
Normal App wiring still needs WP8's protected reader and deployment. Old reading
paths and their source checks remain intact.

Type, item order, day/empty-day order, theme/area, adjacency legs, lodging and
actual place state are retained. Unknown quantities do not become zero. An
integer outside the native formatter's finite numeric range is explicitly
unavailable at display time; the decoder retains its original token. Missing or
unmatched coordinates yield no map marker. Unconfirmed addresses do not enable
the driver card. No prices, reservation state, invented address or coordinates
are added. Caller/source qualification remains an integration gate before real
protected data is displayed; frozen fixtures do not prove a provider source.

Explicit cross-day endings use the actual calendar date or ordinal day, preserving
an overnight end even when dates are unset. The shared stop formatter replaces
identical legacy formatting at both existing display sites; old records have no
new day marker and retain their existing date/time output. A known fixed stop
keeps its lock label in rich summary and detail. Rich detail also displays its
actual time interval. Existing model initializers keep their optional fixed state.

Public display checks cover supplied titles, day areas/themes, names, addresses,
notes and tips. Only existing SwiftUI/SF Symbols/D5/MapKit components are used;
no new UI framework, map SDK, endpoint or permission is introduced. UI/native
checks and protected-service/JT acceptance remain separately reported.
