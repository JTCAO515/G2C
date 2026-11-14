# Canonical start and source-bound execution facts

#830 / #822 / #815. The original C r02 second response correctly recognized
tomorrow as its fixed hotel's date, but omitted arrival.date. The host therefore
repeated the start-date question. Both original RUNs completed, the trajectory
is FAIL, and no NEEDS/Trip/Memory was saved. Neither old response is repaired.

New registration **model.lio_intake.5**, wire profile **LIO-planning-intake.5**,
data **LIO-planning-intake.4**, and execution **LIO-execution-extraction.1**
separate model facts from the existing persisted NEEDS-extraction.1 format.

## Start date

Plan/save must return an explicit start_date observation. A known value requires
its own field_sources.start_date, exact original source index/quote and the same
ISO/relative-day checks used for event dates. Tomorrow remains anchored to that
original MESSAGE's question_day, including after a later person reply or midnight.
The host never infers this value from a hotel date or a previous arrival field.
Consult/discuss/cancel must return start_date=null and their existing null/empty
execution parameters.

Only the verified known canonical start is projected into the planning
arrival.date and its source refs. Existing city/date-ownership and derived-end
checks then apply. If a separately known arrival disagrees, the host asks which
date defines the itinerary range and writes no NEEDS/Trip. Missing, unknown or
uncertain canonical start remains a question even when another event has a date;
known arrival data is retained and may be used to phrase a confirmation question.

Execution returns the complete cumulative snapshot, including required party_size
and fixed_items, rather than only the latest delta. Model instructions require
missing people to stay missing, not default to one from a pronoun or saved Memory.
A later correction changes
only its stated facts; originals remain authoritative.

## Fixed sources

Each unconfirmed fixed item has a short literal label, one explicit primary
source_ref and item-specific detail_refs (possibly []). Each reference is an
exact quote of its indexed original traveler turn. The label must be a nonblank
contiguous span of the primary quote. The host compiles that exact primary quote
as canonical NEEDS description, never an entire turn, a normalized string, the
longest global citation or a guessed fixed_items.N match. A later detail must
match exactly one label that is unique across all original primary quotes;
two generic "meetup" labels do not authorize assigning the same supplement to
both. Ambiguous association is a question, not save authority.

This compilation is exclusive to the new execution version. Its source fields
are not presented to frozen NEEDS1 consumers; only validated compiled fields are.
The original raw model bytes remain independently inspectable. Existing adopted
item/head/lock/history guards remain; this path does not rewrite earlier IDs or
stored history. Canonical IDs for newly proposed items continue to use the
existing description hash rule.

Every original fixed marker must remain covered. Dates, clock intervals, subjects,
locks and booking claims still undergo the existing independent source checks;
a primary quote cannot contain multiple raw clock ranges, even identical ones
joined in one sentence. This deliberately does not deduplicate two same-time
commitments into one. A named reaffirmation can use a separate item detail ref.
Only missing local fixed timezones may use the confirmed destination's existing
host timezone policy. The administrative source identifies the city; this does
not claim that the supplier provided a timezone/UTC offset. Explicit known
conflicts or unknown/uncertain timezones produce a timezone question and zero
write. Explicit IANA/UTC/GMT/abbreviation markers in the original cannot be ignored
because a model returned missing. Explicit offsets/Zulu and unknown uppercase
zone markers next to a clock also require a question; AM/PM remain clock markers.
UTC offsets are never inferred or converted.

## Compatibility and evidence

Old data1/2/3, execution NEEDS1 inputs and reg/profile1–4 keep their previous
semantics. The selected path explicitly requires data4/new execution1; it never
repairs an old payload, retries a model, changes model/endpoint/limits, defaults
facts or bypasses original Meter, owner/Memory/cancel/source/signature fences.
Only the existing explicit synthetic evidence window may collect reg5 originals.

The private signed-PG regression consumes the unchanged public C Chinese/English
two-turn wording, a separate explicit party reply, then exactly one initial save,
name/time-targeted edit and native undo restoring the original content bytes.
Its supplier intentionally emits no arrival.date, a short fixed label and a
missing timezone. The host asks only for people after the start reply; before
that final reply there is no NEEDS/Trip/active Memory write. The original twelve
complete city/language chains and legacy negative controls remain.
These are L0/L1 HTTP fixtures. A new distinct real complete chain, new C full16
and JT L3 remain UNRUN until separately observed. Old ec UNKNOWN and r02 FAIL
denominators, IDs, original fees and unpriced holds are never reset or repurposed.
