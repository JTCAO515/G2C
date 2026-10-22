# CJ-MANUAL-EDIT-INTERNAL@0.1.0 candidate

Owner CJ017; an in-process consumer of CJ015's existing DTOs, not a second wire,
OpenAPI schema or TRIP publication. Source base `8deb696f8149b4f5aa70c767be6c3a263b036227`;
CJ015 original source `5fd115fc97e542bc8776a445d8245fd272000e56`, unchanged domain blob.
Main routes consumer confirmation and independent Review/Testing; those remain pending.

## Read and edit

`cj_manual_edit.edit(original: Trip, *, expected_version, original_content,
selected_ids, title_selected=False, title=None, text_updates=(), order=None,
protected_ids=None) -> Draft` is pure, deterministic and immutable.

- `original` must be an existing Trip with a positive integer version and exact
  canonical UTF-8 bytes. `expected_version` and `original_content` must match it
  exactly. No parsing/re-encoding, trimming or Unicode normalization substitutes
  for the supplied original bytes. Because the Trip read DTO has no validator,
  draft construction checks its minimal current shape and `packed` canonical form;
  final export also runs the real CJ015 Proposal validator.
- `selected_ids` is a tuple of unique original item IDs, never an inferred scope.
  Empty is allowed for title-only editing or a no-op. Title editing requires
  `title_selected=True`. `text_updates` is a tuple of `(original_id, new_text)`
  pairs, each unique and selected. No replacement item dictionary is accepted.
- `order`, when supplied, is the full tuple of exactly the original ID set. Only
  selected, unprotected items can move among their original occupied positions;
  unselected/protected items retain their exact item bytes and absolute index.
  No creation, deletion, renumbering, duplicated ID or movement across collections.
- A changed text becomes `pending` with empty evidence. Another item's evidence
  cannot be copied. Exact unchanged text retains its own original state/evidence;
  adoption and verified truth remain separate dimensions.
- Trusted composition may pass an immutable `frozenset` of protected IDs from this
  read's context; it only restricts changes, and every ID must exist in this Trip.
  `Draft.protection_status` is `CONTEXT_ONLY` then, never a claim all real fixed
  matters were checked. Without that input it is `UNKNOWN`, not an empty-lock
  assertion. This module cannot identify whether the host supplied a complete or
  authentic set; it is not an authorization boundary or lock store.
- `Draft` validates these invariants on direct construction as well. All stored
  values are frozen DTOs, bytes, tuples or frozensets; no mutable JSON aliases.
  Original Trip remains unchanged, and is retained with the candidate content.

Canonical content supports only title/items and id/text/verification/evidence.
Day, time windows, place identity, persistent lock/unlock and cross-day editing
are unsupported. Extra fields/arguments fail explicitly. No automatic shape or
scope expansion. No long-term-memory writes or preference candidates are created.

## Exact change display and candidate export

`Draft.original.content` and `Draft.content` are exact before/after bytes.
`Draft.diff` is a tuple of `Change(path, before, after)` with canonical JSON bytes
for both values. Paths are local UI metadata: `('title',)`, `('items','order')`
for the ID sequence, and `('items', item_id)` for whole changed items (including
fact reset). This diff is not an apply-patch wire. No-op returns an empty tuple.
Decode values only to display them; preserve original bytes for candidate binding.

`Draft.to_proposal(*, proposal_id, basis_version, expires_at, expected_version)`
requires all four fields explicitly from the trusted host. Missing/invalid values
fail; expected_version must equal the original Trip version. It constructs the
actual CJ015 `Proposal` and reuses its canonical validator. IDs, basis or expiry
are never generated, guessed, copied from unrelated fields or defaulted. It does
not publish a proposal, attest freshness/feasibility, issue confirmation evidence,
create an Action or call a repository. Trusted composition must supply actual
context and revalidate original scope/version/expiry when integrating.

`Draft.save()` and `EditSession.save()` always raise `SaveUnavailable`;
`EditSession.can_save` is always false. Diff display or a mock click cannot produce
a confirmation issuer. Eventual user save as the single explicit confirmation,
original action receipt recovery and the only formal transaction belong to CJ015
and the future UI/API composition; CJ005 owns the formal wire.

## Read observation without losing edits

`EditSession(draft).observe(current: Trip | None)` returns another frozen session.
A same-ID observation with different version OR content yields `CONFLICT`, retaining
original draft/version verbatim. Missing/unknown observation (`None`) yields
`UNKNOWN`; subsequent reads cannot clear it or authorize a write. Conflict is
also sticky on a later matching read. Foreign Trip IDs are rejected. Latest
valid observation is retained for display, never adopted as a new base. An explicit
new edit after host reconciliation must be built from a newly chosen original;
there is no rebase/retry/new-action path in this module. This is local read state,
not proof of any attempted write or original receipt settlement.

## Unintegrated boundaries

CJ035 currently has no fixed public Trip feasibility interface for this consumer;
no solver/amount/time algorithms or fabricated feasibility verdict are included.
Protected read context is a structural limit, not a feasibility result. Persistent
fixed-state queries and downstream planning context, complete bilingual editor UI,
CJ015 trusted save/receipt transactions, real auth/DB/services and physical-device
Issue22 acceptance remain UNRUN. Local tests prove only this candidate's invariants.
