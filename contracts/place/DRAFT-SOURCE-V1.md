# CJ-PLACE-DRAFT@1 — actual PLACE observations for structured producers

B #388, parent #21; C owns the new producer/builder/source parser and sole Trip
writer. This appended ABI does not change PLACE@1.0, PLACE-TOOL-HOST@1,
provenance.1, old tools/NEEDS profiles or any frozen Trip semantics.

The interface source is backend/place/cj_place/draft_source.py. New explicit
PlaceDraftConfiguration(publisher=<actual C adapter>), ABI CJ-PLACE-DRAFT@1,
requires publisher.abi=CJ-PLACE-DRAFT-PUBLISHER@1 and actual LocalPlaceDraftTools
(version CJ-LOCAL-PLACE-DRAFT-TOOLS@1). Both are trusted host dependencies, never
HTTP/model fields, module names or environment-discovered fallbacks.

C adapter bind(database,checker,message_context,token_supplier,scope,
place_sources=...) returns a new structured.1 or structured.2 producer with the
existing sources_for/model_messages/system/hold_for_publication/publish_for_message
interface. B explicitly enables the pre-model capture/system-prompt/producer
publication-fence path for either format. Old structured/tool incompatibility
remains; mixing place_draft_configuration with old draft_profile or edit profiles
refuses. No dynamic module loader or new model/PLACE exit is added. Use the formal
run_once(...,tools_configuration=LocalPlaceDraftTools(),
place_draft_configuration=PlaceDraftConfiguration(CAdapter(...))). CLI cannot load
arbitrary C code; a C-owned explicit factory may compose this programmatic host.

## Data capture and exact original association

The registered tool loop supplies SourceToolInput from its original Binding and
logical operation_key. PLACE-tool-input.2 retains original_query_base64,
request_ref, operation_key, message_id, run_id in original metered input bytes.
Actual LocalDraftPlaceProducer invokes the original adapter/parser once and
retains its original typed Result directly, then encodes the same PLACE-result.1
bytes before display JSONL is built. No typed source is reconstructed from a
wire dictionary or display JSONL; answer text is never parsed as source.

Each PlaceObservation is exactly operation_key,request_ref,original_query,
result_utf8,result,config,started_at. config is the original code-owned immutable
cj_place.gaode.Config, including max_age_seconds. Result retains exact provider ID,
coordinate raw/longitude/latitude/CRS strings, source/query/status and unknowns;
no float conversion, same-name merging, invented coordinates or verified upgrade.
started_at is a trusted host preparation observation; successful Result's original
source.query_started_at remains the freshness origin. No client/model max-age or
snapshot upload is accepted.

place_sources.capture(original Binding) returns PlaceSourceBatch(binding,
observations tuple) only from the same actual host/run after the complete answer/
tool loop and all registered settlements. Partial/UNKNOWN or cancellation-interrupted outbound work
cannot be exported as completed. Already completed observations remain data only;
publication after cancellation/terminal state is still refused by the original fence. Empty tuple means no observed PLACE call, never a
fake queried source; C decides whether its new producer can publish unknown-only
content. Failed/no-result outcomes stay typed failures, not successful empty pages.
The batch is data, not admission or a publication lease. Another Binding/owner,
reconstructed batch or old config cannot acquire publication authority.

## Publication and lifetime

C captures before its draft model, includes only bounded actual observation
choices/references in its model contract, and never lets model JSON supply source
snapshots or permissions. C's new message/source path handles send.1/send.2 as
appropriate; provenance.1's old parse_stored rejection is not relaxed.

During actual publish_for_message, place_sources.check(binding,original_batch)
requires the original active B publication fence. It runs the original current
owner/MESSAGE/selection/Memory/NEEDS/source checks and deadline. Outside that
factory-issued active fence it refuses; equality/ABI alone never qualifies a write.
B also mandatorily runs captured-data/config/freshness checks in its own final
publication callback before the original deadline. C must keep before_publish last
in its sole writer/transaction, and its own constraints/protection/FEAS/confirmation
rules. No second engine, writer, model call or unmetered query.

Only the issued complete capture can be checked. Source age must remain within the
original Config.max_age_seconds with a non-regressing aware host clock; unknown
clock/config/old capture refuses rather than dropping sources. Original RUN,
identity, namespace/NEEDS, cancellation and currentness fences stay in force. Source
checks do not open another RUN/MESSAGE transaction inside the active publication.
UNKNOWN/restart reconciles original run/message/operation bytes and exposure; no
automatic model/tool redispatch or new IDs. Once a Trip is accepted, C's frozen
snapshot/source_refs and its manual/scoped semantics govern historical retention;
this data handle cannot refresh a source or grant an edit/accept operation.

Runtime and new C producer delivery require actual signed API/private restricted
PG/formal run_once/Fake/Meter evidence, including two provider IDs with one display
name, raw GCJ-02 and optional-coordinate UNKNOWN, owner/run isolation, stale/config/
cancel/UNKNOWN refusal and preserved old profiles. Real model/API/fees/cloud/
production remain forbidden. This appended interface is not C or App acceptance.

## Positive/negative examples (synthetic contract cases, not production evidence)

| Input/ordering | Observation/publication meaning |
|---|---|
| New explicit producer structured.1 or .2, one successful Search | One settled registered PLACE call; two same-name places remain distinct SYNTH_EAST/WEST, original GCJ-02 strings; three model calls, one tool call, no extra query by capture/check |
| Provider location=[] | Preserve FieldState.EMPTY_ARRAY and value=None; C map projection is UNKNOWN, never longitude/latitude zero |
| Actual no_results | Preserve Outcome.NO_RESULTS with no places; never manufacture queried/verified source; C decides whether unknown-only proposal is allowed |
| Old LocalTools@1 plus new config, old tools+NEEDS profile, wrong ABI | CompositionUnavailable before model/tool dispatch; no silent upgrade |
| Wrong owner/run or copied/reconstructed batch | Capture/check refuses; no additional query or publication grant |
| Only partial/UNKNOWN/unsettled turn, C skipped capture | No usable capture/publication; original exposure retained, no retry |
| Expired source or replaced Config/max_age | Refuse publication; cannot substitute a caller larger freshness budget |
| Host clock regresses before/after capture | Unknown source clock, no new proposal; parser/turn/capture/publication samples share the original monotonic lower bound |
| Cancellation/NEEDS/namespace/identity invalid before final write | Original guard refuses; no late proposal or automatic new attempt |
| check outside original active publication fence | Reject even with an equal DTO/hash; data is not a permit |

A C producer may not call check during hold_for_publication initialization, before
B installs its actual effect fence. It calls check only inside publish_for_message;
B's mandatory captured-data check is also run before the final original deadline.
