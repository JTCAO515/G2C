# Flat single-call travel facts

#830 / #822. The actual B05 supplier response violated the transmitted schema
(plan, null start, omitted nested version/core fields). The same-source provider
request was reconstructed without network; its SHA exactly matched the original
shared journal. This proves a response/schema mismatch, not the supplier's
internal reason. strict=true is generation assistance, never host validation.

New registration **model.lio_intake.6**, wire **LIO-planning-intake.6**, data
**LIO-planning-intake.5** use one model call with simple nullable core values,
flat source-bound fixed values and whitelisted optional extras. The vendor
schema inlines definitions and nullable types; it has no references, observation
unions, conditional branches or nested version wrappers. Current source index
remains the frozen latest traveler coordinate and the actual schema SHA remains
in the original registered input/provider request.

Every root key and fixed-item key is required. Host DTO parsing is strict:
missing keys, extra keys, bool-as-int, numeric/date string conversions and old
versions are rejected. A malformed older response is not a flat DTO and cannot
be upgraded or repaired.

The B06 real second response used `applies_to: ["day-1"]`. Original NEEDS
participant validation rejected it, leaving that original RUN UNKNOWN with no
write. The published flat schema now expresses the same existing participant
grammar: `self`, `party`, or `companion:<existing local id>`, for fixed items and
temporary conditions. No day index is a participant; the host does not translate
an invalid value. Booking/clarification/same-day range descriptions explain the
existing source guards without changing them. A fixed hotel meetup is not a
reservation, redundant primary-quote details do not need later detail refs, and
a single dated clock range has the same start and end date. The B06 original,
its fee and the two unsent steps remain separate from any later new-source run.

## Nullable values

Core start_date/party_size and each fixed date/time/place/zone/lock/booking value
are simple values or null. Non-null means known. For null values only,
unknown_fields explicitly records unknown; uncertain_fields records an original
uncertainty note. Otherwise null means missing. Unknown and uncertain tags are
bounded, disjoint, cannot accompany a known value, and cannot name an unsupported
or absent extra path. Fixed timezone distinctions survive compilation: missing
alone can use the confirmed destination policy; unknown/uncertain/conflicting
values still require a question. No UTC offset is inferred.

extra_fields permits only pace/budget/overseas timezone, the existing three event
types, companions and temporary conditions. Event parts are simple nullable
values with their explicit unknown/uncertain paths. Canonical start, party,
fixed arrangements, source, scope and authority cannot be patched there.
Illegal keys/types do not get dropped to continue saving. All known extras still
need their original domain-path source refs and existing NEEDS validation.

## Host compilation

Only an explicitly valid data5 is compiled into the existing data4 and
LIO-execution-extraction.1 validation path. The host creates its own version tags
and observation objects as this new contract's declared representation, not as
recovery for omitted model data. Source-bound fixed labels/primary/detail refs,
date source/day/arrival conflict/city ownership, people, clocks, marker coverage,
three fixed-source P1 repairs, timezone, locks, current Trip head, signatures,
Memory fences and original Meter remain authoritative. Known fixed place text
must be a span in that item's actual primary/detail source.

consult/discuss/cancel consumes the validated control envelope and city/reply;
optional planning facts do not become execution prerequisites or writer authority.
No NEEDS/Trip is registered. Existing consultation Memory-candidate and explicit
Remember handling stays in place. Plan/save validates all consumed facts before
the original publisher. A model's intent never replaces original user authority.

Old data1–4 and reg/profile1–5 keep their semantics. No fallback, automatic retry,
second extraction, extra model, endpoint/region/limits change or financial ledger
is added. Raw model output and compiled domain facts stay separately inspectable.
The B05 UNKNOWN/fee, C r02 FAIL1/UNRUN15 and old ec UNKNOWN1/UNRUN15 remain frozen.

Local strict DTO/negative, original model wire, private signed-PG full planning
and legacy controls are L0/L1. New-source full real missing→date/fixed→party→
save/edit/undo and C's new complete16 require separately registered original IDs
and remain UNRUN until actual evidence is observed.
