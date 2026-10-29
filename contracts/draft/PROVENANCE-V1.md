# Source document `provenance.1` (#169)

JT approved the source-version direction and bounded TRIP/API/worker write scope
in [#169](https://github.com/JTCAO515/G2C/issues/169#issuecomment-6486082509).
This is independent of the historical structured-itinerary V2 proposal. It adds
no date/day/start/end/zone fields, time parser, NEEDS records or feasibility claim.
Structured itinerary time validation remains M2 #204.

## Content and ownership

`SourceDocumentV1` in the formal OpenAPI is a strict tagged document with
`content_version="provenance.1"`, `title`, `items`, `sources`, and `decisions`.
Original untagged `TripDocument` and all original `Trip*` component schemas retain
their exact definitions. New `Source*` response schemas carry the new union.

Each new item retains `id/text/verification/evidence` and adds `source_category`
and `source_refs`. All new items are `pending` with empty evidence. Classification
is separate from factual verification:

| Category | Allowed source and displayed text |
| --- | --- |
| user_provided | Exact original MESSAGE text, acquired for this same admitted run |
| queried | Exact PLACE adapter name field; never a model paraphrase attributed to a query |
| estimated | Original provider distance/duration raw number and unit; query-time estimate only |
| unknown | Model-generated text with no borrowed source reference |

Sources carry an internal document ID, original reference, displayed text,
canonical snapshot UTF8 bytes (base64), their SHA-256, and evidence level.
A MESSAGE snapshot retains the original command bytes and receipt. A PLACE
snapshot retains its original typed query, Source metadata and Place or Route
projection; decimal raw spellings and timestamp offset/fold/zone are retained.
This snapshot is **not** a claim to contain original provider response bytes.
Synthetic query evidence is labelled `synthetic` in both wire and UI. A query or
source association is not proof of factual accuracy or current future availability.

The model still supplies only the original `{title, items: [string, ...]}` shape.
It cannot supply source IDs, source categories, snapshots or verification states.
The host appends actual source displays and preserves model text as unknown.
Malformed model input still fails as an entire DraftRejected under #168.

`SourceObservationBatch` binds a host callback's parsed PLACE results to the
original RUN Binding. It is correlation data, **not an authorization token**.
The worker obtains the batch under its existing RUN step fence, then enters a
fresh publication step and reads the original MESSAGE again. A changed/missing
message, another run/scope's batch, cancelled run or explicitly supplied stale or
unusable query result cannot publish. No caller/model source-upload route exists.
The existing AUTH/RUN/TRIP authorities, original action semantics and transaction
boundaries remain; this feature does not claim atomic global auth revocation.

`decisions.travel_dates` is explicitly unknown or undecided, with the fixed
`decide_travel_dates` prompt. Free-form time descriptions remain pending text;
there is no inferred date, date validation or synthesized schedule.

## Wire compatibility and activation

For proposal, list, detail and confirmation preparation, the optional header
`X-CJ-Trip-Content: provenance.1` requests a source-aware response. Its envelope
has `representation="provenance.1"` and supports old and new documents. Missing
header preserves the original V1 response. Unknown or duplicate header values
are refused. Action submission/query byte formats and receipt schemas are unchanged.

The upgraded client explicitly requests the new representation, validates its
full original content bytes and sources, and still reads original V1 responses
and records. Old records show “Source not recorded”; their content is never
rewritten or filled with invented provenance. Old readers fail closed for new
records rather than silently dropping metadata. The protected V1 detail snapshot
export used by existing manual-preview/offline consumers remains V1-only; new
source records are not advertised as supported by those legacy consumers.

The server's local worker opts in explicitly with
`CJ_ENV=local CJ_DRAFT_CONTENT_VERSION=provenance.1`. Absence retains the legacy
publisher; invalid versions or non-local activation fail. Direct legacy `publish`
cannot silently emit a reduced record when source mode was requested. The host
may supply a `source_reader` and an explicit positive freshness budget; no reader
means no query, not fabricated query evidence. The default local launcher does
not acquire live PLACE data or credentials. The recorded transport in the tests
is offline and synthetic; do not register that fixture in production.

Legacy publisher compatibility remains until all intended readers explicitly
support the new format. Legacy record/action decoding remains while those records
exist. No migration, permission change, new source database, cloud or production
activation is part of this change. All new metadata is inside the same immutable
content bytes, candidate digest, confirmation and formal TRIP content.

## Evidence and limitations

L0 covers strict model/schema/source association, cross-scope/run and changed
message refusal, post-source cancellation, byte/Unicode fidelity, source hashes,
old/new client reads and original encrypted action recovery. L1 runs the actual
worker, signed local API and full migrations on a new private PG, with FakeProvider
and explicitly synthetic PLACE adapter transport. It checks mixed-record reads,
API reconstruction, original confirmation/action replay, foreign-user refusal and
unchanged source content in formal TRIP. Native iOS 17.5 checks exercise the actual
App in both languages and restart/original-action reconciliation.

These are local/fixture evidence levels, not live provider truth, cloud, real
accounts, device or release acceptance. Follow issue/PR evidence for actual runs.
