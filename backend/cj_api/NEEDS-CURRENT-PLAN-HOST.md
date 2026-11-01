# Explicit current Trip replanning host (#378)

After the source1 creation profile delivered by #354, a separate explicit profile
`needs-current-trip.1` composes C's existing cj_draft.needs_context.publisher. It
uses TRIP-source-input.2 and the unchanged C source/current-selection/protect_model,
publication, planning-context retention and original acceptance machinery.

```python
run_once(database, CurrentTripPlanFakeProvider(), auth_dir,
         draft_profile='needs-current-trip.1')
```

CLI: the existing run_worker.py arguments plus
`--travel-context message-travel.1 --draft-profile needs-current-trip.1 --once`.
The CLI selects the compatible offline Fake explicitly. No environment default,
arbitrary module loader or worker.drafts replacement is introduced. Default legacy
and needs-structured.1/source1 are preserved. Registered @2, actual owned travel,
original explicit NEEDS and C's actual accepted current Trip are required.

C's factory also supports a null planning context for its original creation use.
This B profile adds one capture-boundary guard requiring a non-null actual context;
it does not reinterpret null as source1 or implement another source/version engine.
The Fake preserves the actual current title/items, including manual observations,
source classifications and local fixed state. It invents no IDs or participants;
C still validates its proposed_fields mapping, protection, FEAS and currentness.

Source2 planning creates a new Trip candidate with expected_version0. Explicit
original TRIP-needs-action.1 acceptance selects that new Trip. It does not advance
or overwrite the old context Trip. Manual saves/scoped edits are the distinct
same-Trip version operations. Recover with original receipt IDs using C's existing
TRIP-needs-discovery.1, review the full actual candidate, then the unchanged
Signer/act/receipt; never infer a proposal ID from RUN output or a prefix.

Acceptance needs_replanning_pg uses real signed APIs, a fresh restricted PG,
unpatched run_once and actual CLI/Fake/Meter, original C discovery/confirmation/
acceptance/receipt. Its original source is created with needs-structured.1, then
manually edited and separately fixed through C's exact API before source2. It
checks new Trip adoption, unchanged original Trip, local fixed preservation,
missing context, actual Trip/NEEDS/selection changes during model, fixed violation,
wrong owner, queued/in-flight cancellation and original UNKNOWN without redispatch.
Original status/history/replay retain the exact accepted receipt and UTF8 bytes.
No SQL seeds a Trip or disables guards.
Real models/API/fees/cloud/production and App/device acceptance remain UNRUN.
