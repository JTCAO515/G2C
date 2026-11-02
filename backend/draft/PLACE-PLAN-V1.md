# TRIP-place-plan.1 — appended C producer for #21

This C adapter consumes B's CJ-PLACE-DRAFT@1. During preparation it is tested
against the explicit B candidate recorded in #21/#388; formal delivery requires
the merged B runtime and exact-head evidence. Old provenance.1, source1/source2
profiles, old model plans, structured.1/2 grammars and existing reads stay exact.

## Explicit composition

```python
PlaceDraftConfiguration(publisher=PlaceDraftAdapter(content_version='structured.2'))
run_once(database, compatible_fake, auth_dir,
         tools_configuration=LocalPlaceDraftTools(),
         place_draft_configuration=configuration)
```

`cj_draft.place_local.PlaceDraftAdapter` has ABI
CJ-PLACE-DRAFT-PUBLISHER@1. The content version must be structured.1 or
structured.2. Its bind signature is the exact B interface, not an HTTP input or
dynamic module loader. The original C NEEDS source factory/revision lease,
builder/protect/evaluate, original Proposal and unique Signer/act are reused.
No new query, model exit, place store, permission or version engine is introduced.

Before the draft model, sources_for captures original NEEDS and B's complete
issued PlaceSourceBatch. Each offered choice is derived from operation_key,
request_ref, place index, provider and provider_id; equal names never merge.
The original typed result creates a code-owned source record using the existing
snapshot serializer, retaining raw/Decimal strings, CRS, source/query and optional
states. No answer JSONL is parsed. No-result may offer zero choices/UNKNOWN;
other failed observations withhold the whole plan rather than silently dropping
part of a place set. B retains and rechecks original trusted Config/freshness.

Input appended to model messages is TRIP-place-source-input.1 with
content_version, needs_id, revision, original fields and place_choices. Each choice
is exactly choice_id, place, query, source. This is quoted data, never permission.
The output object is exactly version=TRIP-place-plan.1, title, items,
proposed_subjects, place_refs. Items and subjects use original TRIP-model-plan.1
rules: pending verification, empty evidence/source_refs, no model-authored source
records/queried labels. place_refs is a bounded item_id -> offered choice_id map.
Only items displaying that exact provider name can be annotated. Unknown/foreign
choice, changed name, source upload or verified claims reject the whole candidate.

C validates the original projection through the existing NEEDS builder, then
attaches only selected code-owned place snapshots and source_refs. The resulting
document uses the existing frozen structured.1/2 grammar, at most 40 sources and
1,000,000 bytes. structured.1 requires actual HH:MM:SS declarations; minute values
are not padded with seconds. Missing dates/zones/coordinates remain missing or
UNKNOWN; no free-text inference, coordinate conversion or default zero is added.
The original Trip time checker rejects explicit reversal.

The actual place_sources.check runs only inside publish_for_message/build_plan,
not holder initialization. B's mandatory final callback again checks actual source
identity/config/freshness and its original deadline. The original before_publish
callback remains last in C's sole publication transaction. Data/ABI/hash equality
does not grant a write; cancel, UNKNOWN, expired capture and owner changes refuse.

## Read and edit compatibility

GET /v5/trip-structured remains TRIP-structured-read.1. Resolve
trip.content.items[i].source_refs to trip.content.sources by id, require kind=place,
verify/decode snapshot_utf8_base64 and its SHA256, then read:

- record.place.provider / provider_id;
- record.place.coordinate.state and .value.raw/longitude/latitude/crs;
- the separate entrance_coordinate / exit_coordinate observations;
- record.source and record.query, plus source evidence_level/reference.

These are the old structured snapshot fields, not a relabelled PLACE-result.1
envelope. Query Search retains keyword/city/page/page_size; Detail retains its
provider_id. Record source retains its original evidence/request_ref/binding/time
fields. It does not turn a synthetic/query association into verified facts or
fresh provider data at view time. No observed center means map UNKNOWN; an
entrance/exit must not silently become a center.

Original manual/scoped rules preserve exact sources for title/time/unselected
changes. Intentionally changing queried item text clears that item's old refs;
the old point must not be attributed to new words. Other items and original
historical bytes remain. Source-bound structured.1 editing uses the appended
TRIP-needs-edit/save.2 host in backend/trip/NEEDS-EDIT-V2.md; old .1 keeps its
structured.2-only contract. No source snapshot upload or direct accept shortcut.

L0 tests are data/transform evidence only. Signed API/restricted PG/original
run_once/Meter/Fake PLACE -> original confirmation -> v5 reads, manual/scoped
retention, source/freshness/owner/UNKNOWN negatives are required before reporting
the requested L1 chain PASS. App MapKit and real services have separate owners.
