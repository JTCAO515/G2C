# Lio nationwide intake, version 1

JT 2026-11-11, #702. The public LIO-message.1/.2 and timeline contracts do not change.
The Hong Kong Demo assembly explicitly enables this profile for its existing Demo
identities. Unselected historical/local consumers retain their frozen Beijing
profile until they opt in and complete the same source/receipt tests. The selected
national profile never falls back to that old extractor or publisher.

## Extraction and authority

`LIO-planning-intake.1` is a model data envelope: version, intent
(consult/discuss/plan/save/cancel), reply, needs_tools, city, duration_days,
extraction, field_sources, current_request. Extraction retains the existing
NEEDS-extraction.1 fields. Unsupported interest keys are not added; original
traveler messages and their hashes remain in the draft input. Saved Memory uses
its existing owner, selection, recall and erasure fence; this envelope cannot
save Memory.

City is null or `{query,normalized_name,province,source_index,quote}`. Query equals
the original destination quote. Every known field has original indexed source
quotes; original per-message China question dates bind relative language. The
server validates NEEDS types, calendar dates, participant references and duration,
then derives the end date from the sourced start and duration. It supplies the
confirmed city and timezone itself. Missing start/end, party or fixed-item details
produce a question, without a Trip write. A changed city cannot inherit an earlier
city's date evidence. Refusal, conditional/draft-only/discussion/cancel language
wins over a model's proposed publication intent. A date-only answer can continue
an outstanding positive request, but cannot recreate authority after discussion
or a completed publication. All retained message refs join the existing Memory
history fence before model dispatch.

The model intake is registered as `model.lio_intake.1`. Its source record names the
profile, actual endpoint/model and prompt. It uses the already configured output
ceiling (Hong Kong 1536 tokens); it does not raise model, RUN or shared limits.

## Administrative and weather sources

`tool.lio_city.1` performs one original registered Amap district request for the
country tree (`keywords=100000,subdistrict=3,extensions=base,output=JSON`). It
validates the bounded original catalog and resolves names and pinyin across its
administrative records. Zero or multiple matches ask the traveler. A proposed
translation with no direct name/pinyin match needs explicit confirmation; a model
adcode is never accepted. A province is not silently treated as a city. The
provider currently excludes detailed Taiwan divisions; unavailable records stay
unresolved. See the [Amap district API](https://lbs.amap.com/api/webservice/guide/api/district).

`LIO-city-resolution.1` records actual candidate metadata, source parameters,
original catalog hash and observation time. Same-dialogue pending confirmation
can reuse that source; it is still bound to retained original messages. Amap
administrative lookup uses the original place allocation and unique fee journal.
Its unpriced receipt retains the full existing unit hold, rather than inventing
a lower settlement. Unknowns do not replay automatically.

Selected POI search is bound to the confirmed administrative code. Weather uses
the additive `LIO-weather-query.1`, checks the returned provider adcode, and marks
only actual returned dates observed. The old FACT-query.1 stays frozen. Timeline
sources include the provider name and actual retrieval time. Verified Weather
China reference pages are selected by the actual city; an unavailable public
reference contributes no invented URL. Such a reference is not a fetched forecast
receipt and has no claimed observation time. Historical pre-profile weather
records preserve their known Beijing reference.

## Publication and verification

Both planning and conversational edit explicitly select C's
`LioSourceWindowPublisher` / `LIO-source-window.1`. Candidate source dates,
timezones, known fixed commitments, original Trip head, locks, signature and
publication fences remain mandatory. Undo follows the original action target,
creates a new version, and keeps history. New city/period input cannot silently
remove an existing Trip's commitments.

`CJ_ENV=local python -B scripts/hk_lio_national_local_check.py` runs twelve signed
private PG chains (six cities, both languages), original registered provider/tool
receipts, automatic save, period/name edit, native undo and idempotent readback.
Only the external HTTP responses are fixtures. It proves no live vendor, Hong
Kong or physical-device acceptance; those results remain separate in #702/#32.
