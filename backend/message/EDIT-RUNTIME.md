# B343 runtime producer (CJ-MESSAGE-EDIT@1)

Implements the appended contract in contracts/message/EDIT-V1.md. Old frozen
schemas/profile1 and old refusals are unchanged. New local migration0027 follows
the current manifest; no cloud or production application is performed.

Trusted C host composition supplies EditConfiguration(memory=...,publisher=...)
to create_local_app and LocalDatabase. Both actual implementations must expose
the frozen ABIs. Existing CLI cannot load arbitrary module names or silently
ignore unsupported memory: a new-profile scope with no injected configuration
refuses dispatch. Use the formal programmatic run_once with the same database/
configuration; no unmetered model path is added.

Operator API scripts/message_edit_profile.activate(conninfo,subject,run_context,
configuration,namespace_selection) requires actual compatible configuration,
registered M2, resolved old work, and a current independent owned travel namespace.
It can activate over existing MEMORY; message_trip_profile's old refusal remains.
Namespace is then rechecked for each new input and every execution/publication.

EditAuthority.capture is factory-issued original source data; read_original alone
is not authority. hold_for_effect supplies a live memory_namespace lease. Model
source/memory checks release their source SQL locks before IO; the original RUN
first-advance fence still serializes the registered call against cancellation.
Text publication uses held current Trip SHARE. Modification publication instead
opens one canonical RUN transaction, preserves the worker's actual advisory-owner
checks, takes MESSAGE/TRAVEL locks on its same cursor, then enters C memory/NEEDS
leases. It never holds another Trip SHARE while C takes FOR UPDATE.

C's publish_in_transaction must lock_trip, apply its own scope/protect/FEAS checks,
call before_write with original source checks and original deadline last, and use
its sole _publish_in_tx on publication.cursor. B records the original RUN effect on
the same connection. Before_write is required; a discussion intent, cancelled/
UNKNOWN/failed RUN, changed binding/selection/source, or duplicate publication
cannot enter this path. phase=accept requires completed original modification RUN
with a recorded proposal effect; C still verifies exact confirmation/Proposal/act.
There is no new Trip acceptance/selection/version engine in B.

Commit ACK uncertainty reconciles original receipt/run/effect; it never creates a
new attempt or retries the provider. Whole-transaction rollback removes both C's
Proposal and RUN effect. C source leases outlive the common commit; their actual
objects remain live through exit, then expire. Temporary memory uses only the real
independent namespace, never the Trip ID or a made-up none/empty context.

Actual B acceptance: backend/cj_api/tests/edit_message_pg.py uses signed local API,
restricted PostgreSQL, formal run_once/worker and FakeProvider, existing C typed
memory current_context/require_current and manual collection/management, C scoped
preview and C sole writer. The small C adapter/publisher bridge in that test is
**test-only contract wiring**, not delivery of C344/C336. Those owners still ship
their production adapters and source/confirmation integration. No data fixture is
called a lease and no C file is edited by this B PR.

Default travel_message PG entry always executes send2, send3 and send4 acceptance
in separate fresh clusters, preserving every earlier failure. The supported old
send2 history path is /v2/message-history; /v1 refuses typed reference stripping.
New send4 recovery uses the appended contract endpoints. Real services/models,
fees, cloud/production, App/device and actual C consumer release remain UNRUN here.
