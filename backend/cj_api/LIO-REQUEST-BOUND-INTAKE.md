# First direct trip request routing

#835 records one C03 original POST: `去成都玩三天` returned consult plus
needs_tools=true, while its own raw reply asked for dates and party size. The
host discarded that clarification and invoked the tool-answer route, which
assumed tomorrow. No NEEDS/Trip was written. C03 remains FAIL1/UNRUN15; its
fourteen received outflows, empty Memory extraction, fees and original IDs stay.

B08 and C03 had identical registered input and actual supplier request hashes,
but different intent/tool flags. A single positive pilot does not prove stable
routing; this does not establish the supplier's internal reason.

New registration/profile8 retains data6 and one original metered model call.
On a first, unqualified direct trip command only, a code-owned request control
binds the generated intent to plan and disables the separate tool-answer flag.
Both constraints and their exact schema SHA are recorded in the original input
and transmitted schema. A violating response is rejected before city/tools;
the host never upgrades an old consult response or repairs its payload.

The request control recognizes command syntax, not city/date/day/count values.
There is no Beijing list or parameter extraction/fallback. All those values
still come from the general model, keep their exact original sources, and go
through the existing administrative, date/party/fixed-item, authority, signature,
Trip-head and Memory checks. Missing planning facts are asked, not assumed.

Other wording still uses general model extraction; a non-matching command does
not fail or select a legacy city implementation. Ordinary questions, conditional
or refused saving, quoted/meta inquiries, existing discussion/history and isolated
date/party replies are not forced into planning. The publication gate is unchanged;
the request control itself grants no write permission.

Old registrations/profiles1–7 retain their original wire behavior. No model,
region, parameters/limits/hold, credentials, schema migration or financial ledger
changes, second extraction or automatic retry are introduced. Worker history reads
the same trusted tuple prefix for the new five-field input; original arity/provider
binding checks remain at RealTools preparation.

Fixtures, schema/wire and signed private-PG controls are L0/L1. A new-source real
diagnostic and a fresh complete C16 stage with new IDs are required; the old stage
and its unused IDs cannot be resumed or supplemented. New #32 follows all16 PASS.
