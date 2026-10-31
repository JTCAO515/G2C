# TRIP-scoped-request.1 — C owner freeze / local preview only

#25 child #335 owns this independent L0 seam. B #330 remains the owner of the
actual MESSAGE formal-selection version and current runtime binding; #336 must
consume that frozen version before any real source/dispatch/publication/save.
App #337 belongs to A. This is no new authorization, NL model, or Trip writer.

`cj_manual_edit.scoped.Request.parse(raw)` accepts bounded canonical UTF-8 JSON
(65536 bytes, exact keys/no duplicates), with:

- version=`TRIP-scoped-request.1`; original request_id, trip_id, positive
  expected_version, original_hash (original canonical content SHA256).
- language=`zh-Hans` or `en`; original nonempty text (at most2000 characters).
- selection exactly `{kind:"dates",dates:[explicit ISO dates]}` or
  `{kind:"items",item_ids:[original item IDs]}`; nonempty, unique, at most60.

`resolve(actual_original_trip, request)` checks that exact original ID/version/
bytes with the original structured.1/2 grammar. These are *source observations*,
not a current-read lease. Item selection must exist. Date selection compares only
explicit schedule start/end date observations; unknown date partitions or any
cross-day item require clarification in this local date mode. Select explicit
item IDs instead; actual runtime day membership belongs to the B#330 version,
not a second calendar-range algorithm here. No text-derived date, device
clock/time zone, most recent Trip or travel-context substitution.

A finite ordinal consistency check recognizes 第一天…第十天 / 第N天 (N1–99),
`day N`, and `first/second/third day`, against sorted explicit observed Trip dates.
Unsupported/contradictory ordinals or today/tomorrow/yesterday references require
clarification; no free-text calendar parser. Other text is retained as instruction
for a future model within the explicit selection, not interpreted as permission.

Resolution has original request/Trip, original-order selected_ids, READY or
CLARIFICATION_REQUIRED, bilingual reasons, and immutable can_publish=False.
Switching language retains original Trip/IDs; it does not generate a record or ID.

`preview(resolution, original_manual_edit_bytes)` consumes the existing additive
manual-edit.1 or .2 for that content version. Original request ID, version/content
CAS are retained. It reuses the original manual candidate/fixed validator and
same-package exact unselected-content/position guard (extracted unchanged from
legacy Draft). No second protection or version engine. Global title, unselected
item changes or moves return EXPANSION_REQUIRED with no candidate. The user must
see the reason and explicitly select a new scope; rejecting leaves original bytes
unchanged. Model changes to fixed intent are refused; explicit lock/unlock remains
in the manual editor. Retained fixed/unknown items cannot be edited incidentally.

Model-authored replacement text stays pending/empty evidence/unknown source; the
manual validator does not make it a user statement. Valid local edits return PROVISIONAL, original ManualCandidate and its exact
before/after diff, bilingual required-source explanation and the original
FEASIBILITY-TRIP@1.0/2.0 time report. Reversed explicit time conflicts reject;
missing route/budget/NEEDS occupancy evidence stays UNKNOWN. There is no claimed
fresh traffic result, NEEDS/current memory fence, dispatch permit or confirmation.
No export-to-Proposal/save adapter exists here, and can_publish is always False.

Optional `source` plus `previous_fields` consume an actual canonical source capture
and exact accepted Trip candidate association for structured.2. This delegates
unchanged to C285 `needs_edit_store.checked` (same FEASIBILITY-PROPOSED/protect),
not a new mapper/checker or fabricated Snapshot/Revision. It exposes its original
constraint_report; the source owner still supplies currentness/lease separately.
Absent source, only the declared time report is returned. Neither case grants
publish/save permission.

#336 must add actual B#330 selection/message/source identity, current memory/
withdrawal and canonical NEEDS/FEAS checks, protected current re-read, final
publication fence and the original sole Proposal/ConfirmationSigner/act. A DTO,
READY, equal hash/version or local diff must never supply those permissions.
Cross-day traffic effects need actual sourced evidence and a newly confirmed
larger selection; no automatic expansion, unlock, memory edit or old Trip rewrite.

This slice adds no schema, grant, role, API route, actual provider call, retry,
real service, cloud/production access or physical delete. Legacy core API/frozen
contracts and all original tests remain unchanged in semantics. Pure tests prove
scope/retention only; #25 full L1 remains open until #336/#337 are delivered.
