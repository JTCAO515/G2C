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
