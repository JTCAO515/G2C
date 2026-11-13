# TRIP structured.4 / protected-read.3 / rich source.1

WP7 #930, specification **#922** and merged WP6 #929/PR949. JT's coordinate
decision #922/6848017500 applies: **only original provider GCJ-02**, no conversion.
This slice defines data, conditional provenance checks and examples. It installs
no HTTP capability, writer, migration, account, resource, provider or authorization.

## Versions and compatibility

| New artifact | Meaning |
| --- | --- |
| [structured-schema.4.json](structured-schema.4.json) | Additive rich content over the explicit structured.3 calendar |
| [structured-read-schema.3.json](structured-read-schema.3.json) | New read data envelope accepting original structured.1–4 contents |
| [rich-source-schema.1.json](rich-source-schema.1.json) | Private `TRIP-rich-source.1` binding to protected host inputs, never model input or AUTH |
| [rich-undo-schema.1.json](rich-undo-schema.1.json) | New canonical `TRIP-lio-undo.3` input, including the exact current content version |
| [structured-examples.4.json](structured-examples.4.json) | Public synthetic positive/negative vectors and frozen legacy hashes |

Frozen structured.1–3 and old reads/undo inputs are unchanged. Old decoders reject
new versions; there is no automatic flattening, calendar inference or legacy
upgrade. The new read retains old content and original canonical hashes, including
legacy calendar/day_count=null. Only structured.3/4 have explicit calendars.
The new read/undo **runtime** requires an explicitly admitted new consumer and
source-aware handler in WP8/WP9/WP11; these schemas do not enable an old endpoint
or make an old handler accept .4. Existing saved content and histories are untouched.

## Content

The root retains title/calendar/days/items/sources/date_checks and adds legs and
lodging. Old source records retain their original grammar. Each day adds bounded
theme and area proposal text. Empty rest days remain explicit. Days, day_index,
date=start+index−1, time/zone/offset observations and the two date checks retain
structured.3 semantics. Undated checks are not_checked/date_not_set; dated missing
facts are unknown; clear/conflict requires original evidence. No date defaults to
today. The source checker also requires the exact code-produced check results.

Items retain every old field and add:

- kind: sight / meal / hotel / transport / free_time, a proposed category, not
  factual verification or permission to change a locked item;
- place: matched or unconfirmed, original amap_id, Chinese/English display names,
  coordinate, coordinate_role, address, source and separate name_en_source;
- nullable note, nullable tip{text,source}, and distinct reason_refs factor keys.

The place coordinate uses PLACE's lossless raw/longitude/latitude strings plus
crs=GCJ-02. Its role is poi_center/entrance/exit. All values must equal the captured
provider observation; no rounding, guessed entrance, WGS-84 value or conversion
tag is accepted. An unconfirmed place has null provider ID, coordinate/role,
address and place source; its names are visibly **unconfirmed suggestions**.
English display text without name_en_source is not an official translation claim.
An attested English name must match the captured provider/reviewed name pair;
Wikidata supplies names only, never geometry.

Within each day, item array order defines adjacency. The legs array must contain
all and only those consecutive pairs, in day/pair order, including hotel and
airport/station items when present. A route cannot be reassigned after reordering.
Estimated legs contain walking/transit/taxi, finite nonnegative seconds/metres,
source, provider_estimate_at_query_time and future_guaranteed=false. Unconfirmed
legs have null mode/quantities/source; no zero-fill or invented estimate.

Lodging is exactly area plus two or three recommendations. Each recommendation
contains place, nullable note and reason_refs. Price, rate, availability and
booking-status fields are forbidden. Area/theme are proposals, not independent
geographic facts: a placeholder or shape-valid example is not a G6 richness PASS.
Schema validity does not establish daily density, route coverage, opening hours,
semantic truth, actual availability, language quality or real feasibility.

## Actual originals, defaults and provenance

`cj_trip.rich_source.capture` is a separate **data-binding factory**. Its expected
original, plan-now decision, approved fixed policy, accepted profile states and
eligible observation projections must come from protected host readers/code,
not from Trip JSON, model output, a UI flag or advisory extraction. Equality and
a digest are not authentication. The resulting value cannot authorize a read,
write, collection, payment or release. Raw artifacts are bounded and duplicate
keys rejected; the frozen value has no model-writable aliases.

The original protocol is the actual stored **outer LIO-message.4 origin**; an inner
MESSAGE-send.4, endpoint name or client claim does not make a LIO-message.3 original
v4. New source parsing rejects old origins, including one relabeled by a caller.
As with the existing protected MESSAGE reference, input_sha256 binds the exact
canonical MESSAGE original, not the outer LIO lookup envelope hash. The host must
verify that original's association with the actual stored outer origin separately.
There is no widening of old data8/NEEDS/source guards and no canonical NEEDS change.
WP9's new source authority must independently retain the actual NEEDS/Trip/profile
values, locks, source revisions and final eligibility; this binding is not a
replacement for that authority or the old business constraints.

Code-default states require an actual protected plan-now decision with its original
MID/RUN/input hash/question_day and the **applied fixed policy ID/hash**. The host
supplies the independent decision and approved policy; the model cannot grant
either, invent a user quote or promote default/inferred/not_needed to known.
For later adjustments the original default-trigger MID/policy is retained, not
reanchored to the adjustment. A no-default adjustment may have plan_now=null only
when the protected host also has no such decision and no factor has state=default.
This does not admit an action or permit silent defaults.

Profile states use known/not_needed/inferred/default/memory, with explicit unknown
where unresolved. Only known/memory may be cited by reason_refs. Their values and
quote/Memory provenance were already checked by the protected profile producer;
public projection or merely advisory model fields cannot be used as that input.
Relative dates remain attached to the original date-bearing message, independently
of the current action's question_day used for observation freshness.

Eligible records hold a fixed projection digest and immutable native/reviewed
reference. The host must establish same-owner scope, exact query/endpoint binding,
current eligibility (or explicitly eligible exact cache), actual original records,
and original accounting **before** supplying this registry. New sources cannot be
established by declaring them inside the model document. The conditional checker
compares IDs, raw coordinates/roles, names, addresses, route endpoints/mode/amounts
and deterministic date checks against this separate registry. Newly generated text
keeps legacy source_category=unknown; provider association is in place/leg source,
not a fabricated legacy user statement. Protected fixed/retained base fields may
remain exact; model verification/evidence cannot be introduced as a new fact.

H tip references bind the whole entry digest, checked/expiry dates, exact subject,
explicit applicable item IDs and qualified provider IDs. General entries have no
venue identity. City/fuzzy-name matching and attaching a venue fact to an unresolved
or different place are refused. The initial capture checks validity at the current
original's question_day; the actual publisher must still enforce freshness at final
commit. Free-form wording is not semantically verified by the binding checker.

## Undo and publication obligations

`TRIP-lio-undo.3` has action_id/trip_id/expected_version/original_hash/content_version
and its explicit new tag. It preserves its exact canonical raw input. The old
scalar validator is reused on a private **validation-only** copy; that copy is
never submitted, stored or used to masquerade as old undo. Old input parsers reject
the new raw input and the new parser rejects old tags.

An admitted new handler must match the exact current version/content kind/hash,
read the actual preceding accepted revision and each genuine historical source,
preserve locked fields and source bytes, recheck current constraints, and append
one new version restoring those exact original bytes. No history is overwritten.
Legacy historical sources are checked as their real versions, never relabeled as
wire4; new originals are not falsely marked3 to pass an old guard. Restoring a
revision does not reapply defaults. Unsupported or conflicting history is withheld.
An uncertain commit/response is reconciled by the **same action and original input**,
without a new MID/action or provider replay. The original signer, AUTH/RLS,
RUN→MESSAGE/TRAVEL→Memory→NEEDS→Trip order, current-source/HEAD CAS, clock/Meter
and sole commit remain mandatory. No provider/model/network work belongs under
publication locks. The new codec itself performs no undo or receipt issuance.

## Evidence boundary

Run `uv run --locked python -B contracts/trip/check_structured_v4.py`. The executable
vectors cover new fields, source forgery, default/Memory reason restrictions,
code-produced checks, H applicability, hotel restrictions, adjacency, raw geometry,
strict input, new undo mutual exclusion, read1–4 and frozen legacy bytes/negatives.
They are L0 synthetic contract/binding evidence. They do not establish native wire4
admission, a deployed source authority, rich storage/read/undo execution, real model
completion, costs, Hong Kong timing, G6–G10 quality or JT's G12. Those remain UNRUN
until their owning runtime/evaluation slices provide the actual evidence.
