# CJ014 local structured-result review — candidate.1

Internal Python consumer only, based on Git `8ea1b35756726f60727f10deaf157c40b8df1072`.
This is a bounded C-stage slice of Issue 19, not a public contract, architecture
freeze, authentic generation, persisted draft or completion of the Issue.

`cj_draft.review.request(original, snapshot, revisions, memory, *, subject,
context_id)` binds an already-generated canonical `cj_trip.domain.Proposal` to
the complete canonical NEEDS `Snapshot` and tuple of `Revision` records, plus
the canonical MEMORY `Context` model. `review(request, snapshot, revisions,
memory, *, subject, context_id, links, cancelled, as_of)` compares the supplied
observation against that exact original binding and composes the existing FEAS
`evaluate` report. `as_of` and `cancelled` are explicit local observations, not a
trusted clock, RUN state or cancellation authority. There is no model/tool input
or dispatch API. Arbitrary generated dictionaries must first satisfy the original
TRIP `Proposal` validator. No second Trip, NEEDS or solver DTO is introduced.

All source inputs are historical observations in this slice. A detached MEMORY
`Context`, a matching epoch/version/hash, or a `Binding` is **never** proof of
current authorization or permission to publish. The full manifest includes exact
NEEDS original command/content bytes and source metadata, MEMORY raw original
commands/item versions/status/timestamps, epoch, subject and context. Missing or
invalid dependencies raise; no default memory, synthetic substitute, automatic
rebase, retry or silent success is supplied.

`SourceLink(item_id, evidence_ref, source)` links an exact original Proposal item
and its opaque evidence string to an actual original canonical NEEDS `Revision`
or MEMORY `Item` in the bound inputs. It records association, not textual support
or supplier truth. Missing evidence and unresolved opaque refs remain explicit
`Review.missing`; duplicate links, cross-item links, absent originals, conflicting
ref sources and duplicate refs are rejected. Original records and bytes are
retained, including the source_id/source_version in MEMORY commands and the
original manual source in NEEDS revisions. No provider source schema is invented.
Source membership and reference conflicts compare explicit original record
representations, not dataclass/datetime equality. MEMORY recorded_at retains
microsecond wall time, original numeric offset, fold and timezone identity
(naive, stdlib fixed-offset name, or ZoneInfo key). It is never converted to UTC.
Different DST instants and same-instant different offset/zone representations are
distinct; unsupported timezone implementations are refused. The same exact
representation is included in the request input binding. Command UTF8 bytes are
compared without reconstructing or normalizing their JSON spelling.
Provider-only, estimated or otherwise unresolved information stays `pending` and
UNKNOWN; this slice cannot classify it into a verified provenance category.
`verified` output is refused because truth authority is not supplied by either
source association or canonical structure validity.

Cancellation, expiry and changed bound input bytes discard the candidate from
the result. This is a local check, not a persistent sticky RUN cancellation
ledger. Otherwise status is UNKNOWN or the original FEAS CONFLICT, with the
canonical report's full source/unknown/conflict evidence preserved. Report checks
cover the bound NEEDS declarations, **not** a speculative mapping of free-form
Proposal text to times, places, routes or costs. The original TRIP shape has only
title/items/id/text/verification/evidence. It has no date/day/place fields, so
these cannot be guessed or added. Bilingual text can share the one original
candidate; there is no separate translated candidate or validated translation.

`Review.candidate` is the same immutable original `Proposal`; its content bytes
are never normalized or rewritten. `content_sha256` hashes only those bytes;
it is **not** TRIP's scope-bound `Proposal.digest(scope)` or a confirmation hash.
`can_publish` is always false. `production_factory()` raises `Unavailable`.
There is no accept/reject/save, repository, database, HTTP registration, model,
provider or budget execution. Accept/reject remain exclusively CJ015/TRIP.

## Minimum seams still required

- Trusted host must bind canonical AUTH/NEEDS protected-read and MEMORY
  `consume_current` for the same principal/environment/subject/context. Current
  source APIs cannot be replaced by caller-supplied `Context` or version equality.
  Full encoding must occur within both lifetimes; nothing retained here is a permit.
- RUN/USAGE must define authentic dispatch, cancellation and budget ownership.
  This module neither creates nor accepts a fabricated dispatch token.
- TRIP candidate publication needs an accepted source/basis binding and a defined
  atomic relationship with current NEEDS/MEMORY and RUN cancellation. Existing
  TRIP Repository candidate storage is not duplicated or invoked until that seam
  is fixed. A preflight recheck cannot bridge an independent publication race.
- Mapping structured itinerary dates/places to TRIP and genuine PLACE/FACT
  evidence requires the owning contracts. FEAS's existing constraints/solver and
  provider validators remain their owners; no parallel engine is added here.

These gaps close production generation/publication only; the pure local review
and exact original-version/source-binding checks are executable independently.
