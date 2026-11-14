# Current original source in nationwide intake

#822 / #702. The distinct strict-profile continuation returned a structurally
valid response whose current_request copied the previous question. The original
parser correctly rejected it. That UNKNOWN and its receipt are retained.

New registration **model.lio_intake.3**, wire profile **LIO-planning-intake.3**
and response data **LIO-planning-intake.2** replace model-written current_request
with **current_source_index**. All other fields retain their established data
shapes, including NEEDS-extraction.1. The new field is an integer, not bool,
equal to the latest original traveler turn index. Stored Memory and Trip context
are not traveler turns. Earlier source quotes keep their own indices and days.

For original traveler turns ["去桂林玩两天", "继续"], the response field is
`"current_source_index": 1`. The server validates that coordinate and obtains
the current text from the same immutable original turn. It does not accept a
model-expanded request as publication authority or turn a continuation after
discussion/refusal into a new save grant. Wrong/prior/out-of-range coordinates,
bool values, extra current_request and wrong data versions fail closed.

Each invocation has its own schema whose current_source_index is constrained
to the frozen latest index. The exact response-format SHA and index are in the
original registered operation; the provider builds that same schema from the
same frozen index. It does not duplicate traveler text in the schema or raise
the 32768-byte request bound. Model, endpoint, nonthinking mode, token/output
limits, original Meter, shared journal, owner/Memory fences and source checks
remain unchanged.

The old data1 parser and registrations/profiles1/2 remain available unchanged.
The selected nationwide path explicitly requires data2 from reg3. It never
repairs a malformed old payload or falls back to an old model/format/attempt.
Evidence collection recognizes the actual reg3 only under the existing explicit
selected synthetic window/kinds; original artifacts are never relabeled.

The bilingual private signed-PG regression covers a missing-details question
and its same-conversation continuation with zero NEEDS/Trip/active Memory
writes, followed by the existing twelve complete city/language chains.
Fixtures are L0/L1; new-source real continuation, C nationwide and JT device
validation require separate original actions and remain UNRUN until observed.
