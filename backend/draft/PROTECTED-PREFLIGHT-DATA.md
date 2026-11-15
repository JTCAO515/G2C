# Protected data before any provider call (#931)

`calendar_plan.protected_base_data(fields, fixed_days, day_count, *,
start_date=None, retained=None)` is a pure data projection. It performs no I/O,
NEEDS registration, MESSAGE/Memory capture, source issuance, feasibility decision
or save. It does not create a new TRIP/MESSAGE contract or change frozen formats.

The host supplies source-span-checked projected fields and the complete original
day map. Fixed IDs must already be the final code IDs used after actual city
binding. The L projection and `fields_for` both derive them from the unchanged
quote/description hash; this function does not generate substitute IDs. An
unresolved day mapping must be clarified/refused before city/provider dispatch.
There is no default to day one or a guessed calendar, timezone or party size.

`retained` is the already read, validated structured.3 or structured.4 document,
or null. Legacy .1/.2 need their explicit bridge. All existing items, including
unlocked ones, remain in their original order. A fixed item with the same ID is
counted once and retains the exact current item; its day endpoints must agree.
Fixed IDs must themselves be distinct. New fixed items use the same merge as the
existing `compose` entry. No original observation is mutated.

The result contains only these data fields:

| Field | Meaning |
| --- | --- |
| `calendar`, `days` | Explicit supplied calendar; retained mode/start cannot silently change. Undated days have no dates. |
| `items` | Complete protected item copies. Retained .4 place/note/tip/reason metadata is not stripped. New fixed items have the existing base shape, with original time/timezone observations and unresolved offset. |
| `sources` | Complete unchanged retained legacy source records, including original snapshot bytes/digests. |
| `origins` | Per-ID bookkeeping labels `current_trip` and/or `fixed_fields`; these are not source refs, observations or capabilities. |

The result is neither a complete Trip document nor a source capture. It omits
weather/opening checks, publisher/source versions, NEEDS IDs and binding tokens.
It may contain more than 60 protected items so the host can explicitly reject
the complete graph; nothing is trimmed. The old `compose` limit/validation is
unchanged and still refuses oversized published content.

The host must add the entire model skeleton, two hotel anchors per day, arrival
and departure items, and all legs, then measure the complete candidate's item and
leg counts and canonical UTF-8 bytes **before any Gaode call, including city
resolution**. New fixed items must be fully decorated from the checked data;
do not count only the base shape or strip retained rich/source metadata. A byte
or count refusal reports failure and retains the original Trip; it is not G6.

Unknown observations stay unknown/missing here. This is not proof of the final
post-city/provider footprint: the host must account for pending field expansion
without inventing provider facts, and recheck the final candidate after actual
city/date/source binding. The final fields/date/fixed guards, real NEEDS/source/
calendar capture, `protected_records`, and sole-writer/final-holder checks must
run again. Preflight data may not replace them or be passed as a Snapshot/source.

`compose` still requires its original issued-source entry and rejects rich/legacy
input outside its old explicit .3 path. Only its original calendar/protected
merge was factored into shared internal functions; model fields, source window,
fixed invariants, subjects, date checks and canonical size validation remain.
