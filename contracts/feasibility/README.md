# FEASIBILITY NEEDS-only candidate 0.1.0

`CJ-FEASIBILITY-NEEDS@0.1.0-candidate.1` is a **local internal candidate**, not
FEASIBILITY@1.0, HTTP API, solver release or Issue 18 acceptance. Owner: CJ-035.
Source: `backend/feasibility/cj_feasibility/validator.py`.

## Fixed consumption and trust

Consumes the **public NEEDS Snapshot / Revision / Command / validate_fields** at
`c821b34d607016c6dbc1020c203621841f1a60e8`, present unchanged in base
`8deb696f8149b4f5aa70c767be6c3a263b036227`. NEEDS version remains
`CJ-NEEDS-INTERNAL@0.1.0-candidate.1`; this does not declare NEEDS@1.0 frozen.
`domain.py` SHA-256: `19d9bf84a86e5a7918aefc641ba7f8e50c67066d43b3b944ea27f49e59883de9`.

The caller supplies an **explicit authorized** snapshot and its complete original
revision chain 1..snapshot.version, obtained through the existing NEEDS AUTH
boundary. These pure functions perform no reads, writes, auth checks, model calls
or network requests. Matching sources is structural consistency, **not** proof
of account ownership, authenticity, currency validity or supplier verification.
Do not expose a client-supplied snapshot as an authorized server read.

Every revision must match the record, positive sequence, original action ID,
expected_version and original manual patch. Replaying patches must match each
revision content. Final snapshot bytes must equal that explicit revision's bytes.
No latest lookup, revision substitution or partial history fallback is performed.
Each top-level field retains its last explicit patch revision and **original
input bytes**; retained fields are not attributed to the latest source text.
Absent fields have no invented source. Nested NEEDS fields are whole replacements.

## Small public Python interface

```python
from cj_feasibility import Candidate, evaluate, protect

report = evaluate(snapshot, tuple(revisions))
protection = protect(
    before, tuple(before_revisions),
    Candidate(before.needs_id, before.version, proposed_resultant_fields_utf8),
    selected_fields=frozenset({'fixed_items'}),
    selected_item_ids=frozenset({'appointment-1'}),
)
```

`Candidate(needs_id, base_version, content: bytes)` is an uncommitted in-memory
wrapper around **the existing resultant NEEDS fields**, not a new collection or
Trip/draft schema. `base_version` and record must match the explicit `before`.
`content` is strictly decoded and checked by the same NEEDS `validate_fields`.
No command, revision, persistence or domain write is needed to check a proposal.
The original `before` still requires its complete authorized revision chain.
Candidate evidence has no committed revision/action/source and never borrows old
provenance. A candidate is not an authorized read or a user-confirmed statement.
An unchanged candidate is allowed; different record/base version is INVALID.
CJ-014/017/018 must bind their real fixed types separately. No arbitrary dict,
`String()` conversion or parallel lock algorithm is provided here.

All outputs are frozen dataclasses:

- `Report(status, checks, needs_id, revision, content_sha256, version)`.
  Aggregate status is INVALID before CONFLICT before UNKNOWN. **Never feasible**.
  For protection, `revision` is the explicit before/base version and content hash
  identifies the proposed bytes; it does not identify a committed new revision.
- `Check(code, status, evidence, missing, zh, en, details)` contains both languages
  from the same decision. Status: PASS, CONFLICT, UNKNOWN, INVALID, NOT_APPLICABLE.
  `details` is immutable key/value text for calculated relations, never floats.
- `Evidence(path, declaration, revision, action_id, original_input)` preserves
  declared JSON bytes and exact source bytes; `null` with no source means absent.
  Invalid input diagnostics may contain raw malformed snapshot bytes with no
  claimed valid revision. Paths use zero-based list indexes. Protection evidence
  uses `before.`/`candidate.` prefixes; proposed declarations have no committed
  revision or original source. `content_sha256` identifies the actual
  input snapshot; a hash is not authority. Read-only checks never modify inputs.

Output can contain private user source text. It belongs to the same authorized
read lifetime as its inputs; consumers must withhold it after admission changes,
not log it as public telemetry, and register retention/cleanup if later persisted.
No persistence or retention promises are introduced by this in-memory module.

## Checks and limits of conclusions

| Stable code | Meaning |
|---|---|
| INPUT_INVALID | Bad NEEDS grammar, snapshot, revision history, original source or selection |
| NEEDS_DUPLICATE_ITEM_ID | Invalid duplicate item IDs, with actual input evidence |
| FIELD_ABSENT / FIELD_DECLARED | Absent field versus actual source-associated declaration |
| OBSERVATION_KNOWN / MISSING / UNKNOWN / UNCERTAIN | The actual four NEEDS states, never zero/default date |
| ITEM_TIME_ORDER / ITEM_TIME_REVERSED | Unique start/end instants agree / end precedes start |
| ITEM_TIME_UNKNOWN | Missing date/time/zone, DST ambiguous/nonexistent or unrepresentable instant |
| DECLARED_OCCUPANCY_OVERLAP | Positive-length appointment/transport declarations for a shared subject overlap |
| OVERLAP_CANCELLED / OVERLAP_MEANING_UNKNOWN | Cancelled excluded / overlapping hotel, intent or unknown booking does not prove exclusive occupancy |
| ARRIVAL_DEPARTURE_ORDER | Order of explicit unique instants; missing evidence stays UNKNOWN |
| BUDGET_DECLARED_ARITHMETIC | Exact total-versus-per-person-times-party relation, scope equivalence still UNKNOWN |
| BUDGET_SCOPE_UNPROVEN | Coverage/paid semantics and sourced costs insufficient for a budget verdict |
| UNSELECTED_FIELD_CHANGED / UNSELECTED_ITEM_CHANGED | Explicitly unselected content changed or disappeared |
| LOCKED_ITEM_CHANGED / LOCK_UNKNOWN_CHANGED | Selected locked item changed / lock unresolved and changed |
| ITEM_ORDER_CHANGED | Retained item order changed, needs review even within selected collection |
| PROTECTED_SCOPE_UNCHANGED | Local protection check passed; never overall feasibility or write permission |
| OVERALL_EVIDENCE_INCOMPLETE | Route, rest and cost evidence still required |

Intervals are half-open `[start,end)`; touching intervals and zero-duration items
do not overlap. A reversed declaration is a conflict; malformed grammar is INVALID.
Shared subjects use exact `self`/`companion:id` membership; `party` includes every
subject in that record. Different companions are not silently treated as one.
`booked` and `intended` are user declarations. CONFLICT here identifies declared
time-order/overlap counterexamples, not verified real-world impossibility. Hotels
may overlap appointments. Cancelled or uncertain bookings never establish a
certain occupancy conflict. No travel time, inferred transport speed or buffer.

Date, time and IANA zone must all be explicit on the event itself. The validator
checks both folds using UTC round trips; it chooses neither when ambiguous and
rejects neither declared wall time as malformed merely for a DST gap. Missing
instants stay UNKNOWN; destination/device zones are never substituted. Results
use the runtime's available IANA rules; rerun affected dates if rules change.

Budget declarations retain exact decimal strings. Arithmetic requires known
currency, basis, explicit includes text, party_size, total and per_person. It does
not need budget_paid, infer party size from companions, apply FX, interpret text
as a cost set or subtract paid amounts. Details contain `relation` (less/equal/
greater) and exact `per_person_times_party`. Global Decimal precision cannot round
the product. **Different total/per-person caps are not inherently contradictory**:
the fixed NEEDS contract does not assert they are equivalent limits or that paid
is part of total. Thus all budget verdicts remain UNKNOWN, even when numeric
relations are known. Zero is used only when explicitly declared.

Protection uses field/object equality after fixed NEEDS validation; money text,
Unicode, whitespace and time strings are not normalized. Top-level unselected
fields cannot change. Selecting `fixed_items` also requires explicit item IDs.
Existing items with `locked=true` stay unchanged even when selected; unknown,
missing or uncertain locks require review and produce no positive protection
verdict. New selected items and selected explicitly unlocked edits may pass the
local protection check. Retained list reordering needs review. A selected edit
may still violate an unselected companion reference: NEEDS validates that first.
Only a sole `PROTECTED_SCOPE_UNCHANGED/PASS` constitutes local protection success;
any CONFLICT, UNKNOWN or INVALID means withhold automatic acceptance. Expanding
selection is a new explicit review, never authorization to unlock or write.

## Reproduce and consumer confirmation

From repository root, using existing Python 3.12–3.14 (no new dependencies):

```sh
PYTHONPATH=backend/feasibility:backend/needs:backend/auth python3.14 -m unittest discover -s backend/feasibility/tests -p test_validator.py -v
PYTHONPATH=backend/feasibility:backend/needs:backend/auth python3.14 backend/feasibility/demo.py
```

`examples.json` contains **synthetic-only** patches. `demo.py` creates actual
NEEDS Command / Snapshot / Revision objects and prints both explanations from the
same check. This is a reproducible read-only consumer, not a server or UI adapter.

CJ-035 confirms consumption of the fixed NEEDS public candidate for this slice.
CJ-014/017/018 consumer confirmation: PENDING. Real PLACE route integration, bounded solver,
rest/cost-source integration, root API wiring, auth response-lifetime integration,
real provider, PG, App/device, Review/Testing and Issue I gates: **UNRUN**. Nothing
in this candidate closes Issue 18 or permits domain writes.

Fixed PLACE estimate consumption is documented in [ROUTES](ROUTES.md); its
optional dependency and tests are separate from NEEDS-only.
