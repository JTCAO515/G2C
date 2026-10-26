# Trip content V2 schema proposal — producer ABI fixed / formal wire not accepted

Owner CJ005, branch `cj/005-v2-schema-proposal`, isolated clone
`/Users/jtsm5p/Documents/Codex/2026-10-26/cj-005-v2-schema`.
Base is merged main `a10ad8998fbac4e2a648dd0137f1872eb12b8239` (PR135).
This lease adds only this note, the unregistered schema fragment, same-directory
fixtures/checker/result. Original5525/HOLD tree is not modified or executed.
Publish's existing dirty AGENTS.md is not copied or edited by local Git clone.

## Fixed field input and acceptance boundary

Original grammar field source is CJ015 syntax slice
`7e6a2e95021033cbe847465e18fe57977370057e`,
`contracts/trip/CONTENT-V2-CANDIDATE.md` and `backend/trip/cj_trip/domain.py`.
Its exact NEEDS input is4cc9c815293a4e03225b26adfa228fdd0b50b2e7 and PLACE input
5904e37f698ceb822c16e39ae36c87552235cabb. No mutable working-tree producer is
imported. Main subsequently supplied fixed public ABI
`7262c749fd0b81e3ff5e8ed9f3275169c49c1598`,
`contracts/trip/CANDIDATE-CONTENT-ABI.md`: `from cj_trip import CandidateContentV2,
CANDIDATE_CONTENT_ABI`; constructor is `CandidateContentV2(raw: bytes)`, and raw
is its only data attribute. This fragment describes the JSON INSIDE raw, not a
new dataclass JSON wrapper. Public marker is CJ-TRIP-CANDIDATE-CONTENT@0.1.0-rc.1;
the fixed commit/product SHA in schema metadata, not the marker alone, is identity.

Read-only fixed7e6→7262 comparison confirms all original content validators,
Proposal/Action and the candidate constructor validation body AST unchanged.
The public class is the former private class renamed/exported, with the old name
a direct alias; no second validator. Thus the field/bounds/refusal correspondence
in this proposal matches fixed7262. Producer ABI is fixed; CJ005/schema consumers
and FORMAL WIRE are still not accepted. Proposal V2 and PLACE present still reject.

`trip-content-v2-schema-proposal.json` is a standalone Draft2020-12 STRUCTURAL
fragment. Its $defs are local; no network resolution. It is not a formal OpenAPI
component, registered operation, API input type, replacement V1 model or factory
switch. Its x-cj metadata is annotation, not new content fields or authority.
Original Proposal still rejects V2 and present PLACE. No Proposal construction,
publish/act/confirm, persistence, source currentness or real feasibility follows
from schema validation. No source/AUTH/SQL/provider/permissions/App changes.

## Exact structural field correspondence

| Object | Fields and supported subset |
|---|---|
| Root | Required content_version=int2, title, needs_basis, days, items; strict keys. This schema version is separate from Trip CAS/NEEDS record version. |
| needs_basis | Explicit null or needs_id + positive persisted bigint version1..9223372036854775807; not the party-size100000 limit. |
| Day | id/date/timezone, original stable Trip identifier and original NEEDS observations. days may be empty when item references are null. Array order is preserved. |
| Item | Exactly id/text/verification/evidence/day_id/start/end/locked/needs_item_id/place; items nonempty. V1 fact-shape fields retained, not a new truth rule. |
| start/end | Full original four-field NEEDS Event: date/time/timezone/place. Event place is user-declared text, not provider identity. |
| Observations | missing/unknown: state only; uncertain: state+nonblank note; known: state+typed value. No default date, device zone, lock=false or collapsed null state. |
| Item PLACE | Exactly one state among missing/empty_array/empty_string/null/invalid/unknown. No value key even value:null, no present branch or present:any placeholder. |
| References | Nullable day_id and needs_item_id retain original identifier shapes. Nonnull needs_item_id structurally requires nonnull needs_basis. Membership/currentness remain later checks. |

Title/note/event place text bounds reuse confirmed NEEDS4096; item text/evidence
keep original V1 rules rather than inventing a tighter cap. Date format is checked
with FormatChecker in the local runner; local time accepts HH:MM[:SS] only, no
24:00/leap second/offset spelling. Known timezone strings retain original keys;
ZoneInfo database validity is delegated to the original producer.

A cross-midnight accepted example retains ONE item ID/start/end and one primary
Day, never clones an item into another Day or authorizes edit scope expansion.
verified+opaque evidence is only the existing grammar shape; source truth remains
unproven. Six PLACE absence examples stay distinct from actual JSON null or a
present provider object. No unconfirmed Source datetime/coordinate/Decimal/query/
outcome/max_age projection is introduced here.

## Three layers that must remain distinct

1. **Structural schema**: required/extra keys, tag value, typed observation shapes,
   identifier grammar, date/calendar with enabled format checking, local wall time,
   persisted-version range, no-value PLACE shapes and the basis conditional.
2. **Original producer pure gates**: raw immutable UTF8, canonical packed bytes,
   duplicate JSON keys,1,000,000 raw-byte cap, valid ZoneInfo key, unique Day/item
   IDs, valid day reference, and comparison of uniquely resolved instants only.
   Comparable end<=start, wrong selected destination-local Day and7e6 timezone
   overflow rejection belong here. DST overlap/gap remains unresolved; no UTC or
   inferred zone rewriting. JSON Schema uniqueItems compares WHOLE elements and
   is not an ID uniqueness assertion across differing objects.
3. **Trusted application gates**: NEEDS item/reference existence and currentness,
   exact field-level original revision/source association, current AUTH/principal,
   selected/fixed edit policy/old+new affected Days, accepted Proposal V2 and
   publication/confirmation boundary. None is performed by the fragment or7e6
   grammar. PLACE present remains rejected pending exact producer serialization
   and separate adoption/currentness/cache rights.

Standard JSON Schema integer uses mathematical value semantics:2.0 satisfies
integer/const2, and1.0 satisfies integer revision. The fixed producer explicitly
rejects float tokens. This limitation is demonstrated, not hidden by a custom
validator dialect. Exact JSON token type/canonical raw checks must remain in the
original producer at any eventual ingress. The fragment therefore cannot replace
that validator or become an enabled wire merely by passing these tests.

## Local examples and observed validation

`trip-content-v2-schema-examples.json` keeps one base document and small test-only
replacements/deletions, not a proposed patch API. Six checker methods PASS:

-16 structural accepted examples: all six absence states, all observation shapes,
  original Unicode, empty Days/null reference, cross-night identity,100001/max
  persisted versions and fact/lock shapes.
-35 structural rejected examples: extra/missing fields, unsupported/bool versions,
  bad lexical/calendar/time values, wrong observation shapes, present/any value
  escape, missing basis, invalid bool/bigint and verified-without-evidence.
-8 schema-accepted ORIGINAL PRODUCER gate examples, explicitly not producer tests:
  integral float tokens, invalid zone database key, duplicate IDs with differing
  values, orphan Day, reversed unique window and selected-Day overflow.
-2 schema-accepted application examples, explicitly not authorization/currentness
  evidence: unresolved NEEDS references and unknown lock.

Initial result: `trip-content-v2-schema-validation.txt`, Python3.12.14/jsonschema4.26.0,
Draft2020-12 with date FormatChecker. That retained log correctly records the
then-PUBLIC_ABI_PENDING status and initial schema SHA. After fixed7262 arrived,
only provenance/status annotations changed; validation keywords and fixture bytes
are identical. `trip-content-v2-schema-abi-check.txt` records old/current/structural
SHA, unchanged producer ASTs, and ONE rerun of the changed metadata/metaschema
method. The original six-method structural evidence is reused, not broadly rerun. No CJ producer/module,5525 runtime, DB,
network/provider/real AUTH, generator or old HOLD probe executed. Existing
third-party validator toolchain is used read-only with -B; no dependency install,
lock or environment change, and no CJ002 runner/config/key is accessed.

Reproduce with any already available Python>=3.12/jsonschema4.26.0 environment:

    PYTHONDONTWRITEBYTECODE=1 python -B contracts/api/check_trip_content_v2_schema_proposal.py

The actual local interpreter was the existing CJ002 venv's Python binary, used
ONLY for stdlib/unittest/jsonschema. -B prevents bytecode writes; no runtime source
is imported and no human-operation script is invoked. Validation is structural
proposal evidence, not re-performance of CJ01557/overflow or independent review.

## Evidence that this fragment is not registered

Checker reads immutable a10 Git blobs and confirms byte-identical formal
`contracts/api/openapi.json`, `scripts/generate.sh`, TRIP/preview dependency pins.
Original V1 accepts its old shape and rejects V2/explicit content_version1; V2
fragment rejects untagged V1. Original schemas/operations remain untouched.

The unchanged generation script explicitly reads ONLY contracts/api/openapi.json
for Python and Swift; it never scans proposal JSON files. Formal OpenAPI has no
reference to the fragment. No generated file, handler, factory, migration or pin
is written. The fragment's presence cannot enable V2 in a producer or service.

The producer ABI field-match step against fixed7262 is now complete. Next gate is
independent schema-candidate/consumer confirmation, followed only under a separately
approved lease by formal versioned wire work. Formal wire requires versioned schemas/operations,
V1 mixed-record compatibility, original Proposal/read/confirmation contracts and
CJ014/CJ017/CJTripClient confirmation. Current note does not authorize that step.
All runtime/source/currentness/Proposal/provider/App/C2/DB/production checks are
UNRUN; no resource, deployment, push/merge or Issue closure.5525 HOLD stays intact.
