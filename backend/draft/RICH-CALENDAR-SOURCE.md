# Native4 calendar and profile source component

This C component supplies one part of the WP8 source boundary. It is not a
publisher, a provider-observation seal, an HTTP route or deployment acceptance.
The L host composes the actual calendar reader and `RichProfileSource`; their
real signed PG composition must pass before a rich publisher uses this source.

## Additive representations

`cj_draft.rich_calendar_source.RichCalendarBasis(day_count, start_date,
fixed_bindings)` retains the existing day-ordinal and optional-start-date
semantics. Its canonical `LIO-fixed-day-bindings.2` sidecar has exactly:

- `version`, `needs_id`, `needs_version`, `needs_content_sha256`;
- `reference`: the current native4 original;
- `bindings`: the original fixed items, day/end-day ordinals, quote and original
  `source_reference`, with unchanged historical Lio versions 1–4.

Each reference has the existing exact conversation/generation/MID/RUN/sequence,
canonical MESSAGE input SHA, MESSAGE version and actual Lio protocol fields.
The root must be LIO-message.4. It is never relabeled as .3. The corresponding
metadata version is `TRIP-calendar-basis.2`.

The private source envelope is `TRIP-RICH-CALENDAR-SOURCE.1`: original retained
NEEDS data plus the new calendar basis and `planning_profile` provenance. The
latter records the actual plan-now original, applied policy, accepted states
and sourced profile from the L reader. These retained bytes are not authority.
No frozen calendar-v1 representation or decoder is changed; old decoders keep
refusing the new representation and native4 roots.

## Actual holders

`RichCalendarContextSource` uses the existing `LioContextSource` M/NEEDS capture,
then the new calendar reader and
`profile_reader.capture_for_plan(worker, binding, message,
expected_profile=accepted_profile)`. The L reader must verify the actual native4
original, committed context.2, independent code-only plan-now marker, installed
policy and actual Memory capture. A caller-supplied boolean or descriptor does
not replace those checks.

At publication, the existing MESSAGE frame is passed to the calendar holder and
`hold_for_plan(worker, binding, issued_profile, message)` before NEEDS and Trip
locks. The worker already holds its genuine Memory frame. Neither reader may
acquire another MESSAGE lock or dispatch a model/provider. Both holders and the
original NEEDS lease remain live through the final Trip check. Copied captures,
changed readers, foreign bindings, expired lifetimes, withdrawn Memory/profile,
changed fixed originals or inconsistent native question clocks are refused.

## Remaining integration

WP8 must additionally capture and hold actual eligible provider observations,
build and validate `TRIP-rich-source.1`, run the rich solver/date checks, retain
current Trip CAS, and use the existing signer and sole commit path. This source
component supplies none of those missing permissions. Native rich save, edit,
date conversion and undo remain separate integration requirements. A conditional
data-validator PASS is never a native source grant or complete task PASS.

## Registered provider composition

`RichProviderContextSource` adds a second, explicit stage. Initial `capture`
still captures only the original calendar/profile/NEEDS. After the registered
providers settle, call `seal_providers(binding, issued_calendar)` **outside
worker._step and all RUN/MESSAGE/Memory/NEEDS/Trip frames**. The actual L producer
checks original operation inputs and settled Meter receipts there; the C layer
does not take a records list or initiate a provider/retry.

The resulting opaque capture retains `TRIP-RICH-PROVIDER-SOURCE.1`, including
the unchanged calendar/profile source plus `provider_records`. It delegates the
original NEEDS records, calendar basis and profile. These retained bytes remain
data: copying or constructing a descriptor does not issue a publication lease.

Final publication reuses the original MESSAGE and worker Memory frames, enters
calendar/profile and provider holders before NEEDS/Trip, and keeps all checks
through the existing final callback. The producer's final check must use its
SELECT-only status reader, not reacquire RUN via `read_original`. Missing seals,
changed original/configuration/producer revision, unresolved receipts, expired
or copied captures and late source withdrawals withhold publication. A failed
seal is not retried by this component.

This join does not yet compile `TRIP-rich-source.1`, code-produced date checks,
fixed/retained/H records, a structured.4 candidate or a signed Trip action. The
new component still requires actual registered-producer signed PG composition,
source-bundle qualification and the full WP8 red-line review before activation.
