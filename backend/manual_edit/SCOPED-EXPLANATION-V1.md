# TRIP-scoped-explanation.1 — display-only scope explanation

`cj_manual_edit.scoped_explanation.explain(resolution, raw_edit=None)` is an
additive pure-core consumer of the original `scoped.resolve` result. Old Request,
Resolution, Preview and `preview` behavior/validation remain unchanged. It neither
calls a publisher nor opens an API or database connection.

The result is `ScopeExplanation(raw, status, can_publish=False)`, or `None` for an
edit that needs no expanded scope. It is not a ManualCandidate, has no candidate
hash or proposal ID, and grants no save/accept permission. Raw output is canonical
UTF-8, bounded to 1,000,000 bytes. Overflow refuses; it never truncates changes.

For a non-READY scope, status is CLARIFICATION_REQUIRED. The deterministic result
preserves original selection/resolved IDs, bilingual original resolver reasons,
and facts about unknown date observations, cross-day item IDs, unmatched explicit
dates and observed dates. `changes=[]` and `required_selection=null`: ambiguous
text/unknown dates do not authorize an inferred replacement selection. The model
need not run and model prose cannot supply these facts.

For READY scopes, the same manual grammar, exact original ID/version/bytes CAS,
document and protection validators validate the edit; their temporary candidate
is discarded. Fixed edits, unknown item IDs, stale edits, malformed values/orders,
locked changes and injected fields remain errors, not scope explanations.
The output contains exact before/after values for actual changed fields and
global title/order changes, not model-written explanations. Unselected values
and all UNKNOWN observations in the original Trip remain unchanged.

EXPANSION_REQUIRED records the original selection, outside item IDs, outside
explicit dates, reason codes and both Chinese/English reasons. Required item IDs
are the original-order union of selected and affected IDs. Reordering includes
every shifted position; title changes require the entire Trip. Required dates
are only explicit endpoint observations in the original/edited affected scope;
`incomplete=true` preserves unknowns. It never fills intermediate days, parses
free text or uses a device clock/timezone. Date selections additionally detect
schedule changes beyond their selected dates. An item selection continues to
select that item rather than silently acquiring a date constraint.

`required_selection.whole_trip=true` and `local_selection_sufficient=false` for
a title change explicitly identify a requirement that the existing local item/
date selector cannot authorize, even when all item IDs are selected. They are
display facts, not a new selection grammar or an automatic expanded send. Other
expansions still need a new user-selected send.4 against the current version,
then the original checks/Proposal/Signer/act. No current request is upgraded.

Chinese/English request language does not change machine-derived changes or
required scope. Both reason strings are retained together. Stage 1 does not
persist rejected model replies, change CJ-MESSAGE-EDIT-PUBLISHER@1, alter the old
TRIP-scoped-result.1 API, or complete #336 frames 2/4. Stage 2 must consume B's
new frozen result path and enforce current Memory/withdrawal and Trip lifetime
again before exposing a persisted result. Actual rejected-result API/PG/worker
recovery remains UNRUN until that integration is delivered.
