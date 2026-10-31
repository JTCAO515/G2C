# Explicit local NEEDS creation publisher (#354)

Default run_once/CLI still use the original legacy DraftPublisher. To opt into
C's existing cj_draft.needs_local.publisher, call:

```python
run_once(database, compatible_fake_model, auth_dir, draft_profile='needs-structured.1')
```

The database must be an explicitly registered CJ-LOCAL-RUN@2/travel creation host.
Use actual signed send.2 with creation_intent=consider_trip and an explicit owned
current NEEDS reference. Source capture/model prompt/protect, RevisionLease and
unique Trip publisher remain C-owned. No module-path loader, environment detection,
worker.drafts mutation or second model/accounting exit is introduced. New edit
profiles/tool profiles cannot be silently mixed with this creation composition.

CLI equivalent:

```sh
CJ_ENV=local uv run --locked python -B scripts/run_worker.py \
  --conninfo-json <private-local-config> --auth-dir <private-fixture-auth> \
  --run-context <explicit-registered-context> --travel-context message-travel.1 \
  --draft-profile needs-structured.1 --once
```

The CLI's opt-in NeedsPlanFakeProvider copies only explicitly supplied fixed_items
and observations into synthetic TRIP-model-plan.1 data; it does not invent sources,
UTC offsets, subjects, confirmations or real-world facts. Empty source items refuse
rather than create a fake default plan. C's unchanged builder/protection still
validates every output. Programmatic run_once may use a compatible FakeProvider
subclass. Real models/--real, services, fees/cloud/production remain unavailable.

Actual needs_creation_pg acceptance uses signed API, restricted PG, genuine @2
budgets/travel/NEEDS and unmodified run_once + CLI. Original C Signer/act accepts
the structured candidate, creates its current planning pointer, and structured
list/detail returns original version/hash/local observations and immutable NEEDS
basis. There is no business SQL seeding a Trip or disabling budget protection.
Currentness/source edits and UNKNOWN/no redispatch retain the same Meter/fences.

The old protected-legacy INITIALIZE 503 is a separate C policy: ManualOrigin._run
rejects existing cj_message_needs_binding/cj_local_run_protection rather than treating
an unbound legacy source as a current NEEDS lease. It remains unchanged and is
reproduced through actual original acceptance/initialization APIs in this test.
Structured creation now avoids that conversion path; any change to initialization
must be handled by C with the original source/confirmation rules, not by a B bypass.
