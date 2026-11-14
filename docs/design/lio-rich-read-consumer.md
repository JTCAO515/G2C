# WP11 rich data consumer preparation

This slice consumes the frozen WP7 #930 / PR954 formats. It does not register
HTTP4/read3, grant a protected source, accept a proposal, enable an old editor,
install a writer or change a normal App entry. Actual wiring requires WP8 and
an owner/lifetime-bound protected reader. Only the pure calendar data readers needed for .1–3 compatibility are included.
This slice does not depend on or include #863's activation, HTTP3, protected
snapshot, Library, host or UI changes; its separate native Home AX failure remains.

## Data and scope

`RichStructuredTripDocument` retains the actual structured.4 bytes and SHA256.
It reads kind/place/note/tip/reason references, themes/areas, all ordered adjacent
legs, and two or three lodging recommendations. Unknown fields, hotel price or
reservation fields, invented fields on unconfirmed values, wrong coordinate CRS,
invalid source pairs and nonadjacent legs are refused. GCJ-02 uses the existing
lossless coordinate reader without conversion.

A private calendar validation view reuses the frozen structured.3 rules. Its
retagged bytes do not escape as a document or accepted source. Public item/date
values can be displayed; their existence does not establish actual-original,
eligible-registry, owner or publication authority. Source-reference equality is
not authentication. WP8/WP9 retain those protected host obligations.

`RichStructuredTripReadV3` reads only the explicit read.3 envelope and checks
request ID, closed shapes, actual content kind and exact content hash. Legacy
contents stay .1/.2, explicit calendars stay .3, rich content stays .4. The old
read.1/.2 parsers still reject this envelope. A list preserves legacy nullable
calendar/day count and exact Int64 versions without date arithmetic on counts.
The envelope budget includes content overhead; each content reader retains its
own frozen byte/depth/node limits.

## Numeric boundary

structured.4 quantities allow JSON numbers beyond Foundation's numeric range.
The existing shared token reader gains an explicit numeric policy, default off.
Only the new rich data reader opts in. For that policy, a private grammar probe
replaces strictly valid number lexemes with zero for Foundation's syntax check.
Actual values, original bytes, ranges and hashes still use the original input.
No zero reaches the decoded model. Duplicate keys, strings, UTF-8, raw NUL,
structure, completeness and depth checks remain. Missing array values cannot
become empty numbers. Old consumers continue their original Foundation path.

Rich quantities retain their raw lexemes, including large integers. Floating
quantities must be finite and nonnegative. The display adapter must choose an
appropriate human representation; the decoder does not round, invent quantities
or authorize a route. Originals and canonical source hashes remain untouched.

## Evidence scope

The unchanged 400-digit positive and nonfinite/negative/boolean negatives are
retained. Six frozen contents use canonical bytes whose SHA256 values are checked
against C's Python canonical encoding, without Foundation numeric reserialization.
The content/read tests cover all four real content versions, old-parser exclusion,
hotel/calendar/adjacency negatives, mismatched hashes/trace/version, unknown keys
and exact Int64 overflow. Actual source-registry negatives remain a producer gate,
not a claim that this display codec knows private host evidence.

Local synthetic tests and independent code review are separate from exact-head CI,
native UI, Hong Kong, source eligibility, real model and JT G12 acceptance. No
new data or operational permission follows from this preparation.

