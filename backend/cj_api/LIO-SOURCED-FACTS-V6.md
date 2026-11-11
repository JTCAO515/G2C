# Sourced single-call facts

#830 / #822. B07's actual second response had valid participants/start dates but
inserted arbitrary empty field_sources map values. The original parser correctly
rejected it; no NEEDS/Trip/Memory write occurred. Its UNKNOWN and original costs
remain frozen, with the unsubmitted later steps unused.

New registration `model.lio_intake.7`, wire `LIO-planning-intake.7`, data
`LIO-planning-intake.6` keep the same single registered model call and exits.
Field sources are now entries `{field, source_index, quote}` with a fixed domain
field enum and nonempty exact original quotes. No arbitrary map keys or empty
map values are accepted. The host groups validated entries into the original
domain source representation; it does not drop unknown fields, invent sources,
repair an old response or retry extraction.

Fixed arrangements replace scalar booking_status with nullable booking_evidence:
`{status, source_index, quote}`. Null explicitly means no known reservation
status (existing unknown/uncertain metadata still applies). A supplied status
requires an explicit reservation/ticket/intention/cancellation statement in
that same item's primary/detail source, then all original source binding and
booking checks. Fixed, locked, confirmed, or a hotel meetup is not reservation
evidence. A fabricated booked string or unrelated proof is rejected, never
changed into a missing observation so execution can continue.

The new boundary reads the full original atomic clause around the proof, not
only its model-selected substring. Evidence must uniquely and affirmatively
name this item next to its reservation predicate (the quoted span may locate
the item, but the full original clause must contain the assertion); negative/conditional Chinese
or English clauses, a different target, repeated ambiguous quotes, and a label
that borrows another arrangement's clock are rejected. Clipping “已预约” out of
“并非已预约” cannot hide the negation. Independent review found these two P1
cases in the first candidate; their original failures and regression cases are
retained. No received supplier response is rewritten by this rule.

The affirmative check keeps the complete original declaration tail through its
sentence terminator, including comma/semicolon/conjunction clauses. Question
tags or a later false/conditional clause cannot disappear when either supplied
ref is clipped. Date/clock spans are masked only for sentence detection so an
`a.m.` clock cannot masquerade as the statement ending; original bytes stay exact.

Structurally valid facts with unclear reservation semantics return a typed
clarification carrying only already checked control metadata. Duration, start,
sources and execution facts are absent from that control value. The host keeps
its original authority/city checks and asks for named fixed details before any
NEEDS/publication. It does not repair or save the rejected booking facts. DTO,
original source/date and other malformed results still use the original error
path. Cancellation/discussion/consultation do not consume booking requirements.

Support remains conservative: indirect wording, ambiguous clauses, or a later
confirmation not supported by the existing final fixed-source checker can still
require clarification. This version does not claim expanded booking capability;
the old writer guard remains in place and no primary quote is fabricated to
make a later confirmation pass.

The DTO validates data6 once; the code-owned normalized facts enter the existing
flat compiler and original data4/execution1 domain path. All start/date/source,
scope/intent, fixed-item participants/unique details/clocks/timezones/bookings,
current Trip head/signature/undo, Memory, cancellation, Meter and original user
authority checks remain. Consultation/discussion/cancellation still does not
consume optional execution facts or require execution booking proofs.

Old registrations/profiles1–6 and data1–5 remain available with their original
behavior. No fallback, second model, alternate endpoint/model, financial ledger,
limit/hold reset, credentials or migrations are introduced. Actual schema SHA
and selected raw response capture use the same registered input and protected
evidence mechanisms. Existing stopped stages never resume or change denominator.

Local fixtures and CI are L0/L1 only. New-source real full planning/save/edit/
native undo, C's fresh complete16, new #32, and JT's device result require their
own original evidence and are UNRUN until actually observed.
