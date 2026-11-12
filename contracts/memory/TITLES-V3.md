# MEMORY title projection V3 — #803

Additive, read-only projection. `TYPED-V2`, all v2 paths, input/receipt models,
stored bytes and model-consumption payloads remain unchanged.

`GET /v3/memories?limit=...&after=...` and
`GET /v3/memory-items?item_id=...` keep the exact v2 query bounds and admission.
The response is `MEMORY-result.3`. Each item keeps every v2 field and adds
required `title: string | null`. Empty or null means unavailable; clients display
the original `command.text`, without generating a replacement themselves.

Titles belong to the returned item/source revision, not an independent record.
They are generated on each authorized read. No title is stored, cached, recalled
by a model or used as save/confirmation/source authority. Editing uses the new
item/source text; pause, withdrawal, expiry or deletion cannot retain an old
title. A missing item remains null, rather than a title-only item.

The read holds the existing MEMORY scope lock through source eligibility and JSON
encoding. Original AUTH/owner/request-lifetime checks remain. Precommit rechecks
the scope epoch, item version/bytes and source approval/expiry after fresh AUTH;
source or identity changes while encoding withhold the whole response. Initially
ineligible items have title null. Reads never activate/repair a source or change
an operation receipt.

## Title rules

- Preserve the original language: no translation. Chinese titles have at most10
  Unicode characters; Latin-script titles at most5 whitespace-separated words.
- No trailing sentence punctuation, line breaks, Markdown or internal identifiers.
- Generation removes only a supported first-person preference/reminder prefix or
  budget introduction, retaining negation. It never truncates a longer statement.
- Unsupported/mixed scripts, inference items, a phrase still over the bound, or
  unsafe text produce null. A travel-only qualifier may be omitted only in a
  canonical travel slot; negation and the original stored sentence are retained.
  This is the explicitly allowed generation-unavailable
  path, not a different saved fact. The original remains readable/authoritative.
  Broader summaries require a separately validated generator; this path remains
  until that generator supports the affected forms. There are no provider calls.

Formal shape source: `contracts/api/openapi.json` new MemoryItemV3 and list/detail
V3 response components. Semantic title checks: `cj_memory.title_projection`.
Old v2 clients retain their existing paths until explicitly migrated; removal is
outside this change and requires verified consumer retirement.

Validation includes Chinese/English labels, null/empty, overlength, wrong-script
and internal-text negatives; guarded PG reads, source expiry/withdrawal and edit
interleavings, cross-owner/identity rejection, v2 preservation and unchanged
original model text. These are synthetic local checks, not real-service quality
or deployment acceptance.
