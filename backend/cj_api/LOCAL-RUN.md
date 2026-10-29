# Local NEEDS and registered provider-call quota

This opt-in host composition implements #170 under JT approval6488161293. It is
only for `CJ_ENV=local`, a new private Unix-socket PostgreSQL database and
`FakeProvider`. A `provider_call` is one complete local answer or draft invocation;
it is not a token price, paid-model budget or production authorization.

Apply the repository migration manifest through 0017 using the local initializer,
and initialize invited development subjects with `scripts/dev_auth.py`. The API
and worker still connect as `cj_m1_runtime`; the initializer is used only by the
operator CLI below. Never use cloud connection information here.

Provide an explicit JSON file through `CJ_LOCAL_RUN_CONTEXT` (API and worker) or
worker `--run-context`. Replace the period bounds with explicit UTC epoch seconds
whose interval contains the current time; no bounds or budget are generated:

```json
{
  "version": "CJ-LOCAL-RUN@1",
  "current": {
    "meter": {
      "unit": "provider_call",
      "budget": 2,
      "period_start": 0,
      "period_end": 1,
      "max_steps": 4,
      "max_tools": 1,
      "max_output": 10000,
      "max_seconds": 600
    },
    "output_limits": {"answer": 1000, "draft": 1000}
  },
  "history": []
}
```

The example interval is intentionally expired. Output limits count characters.
The total time limit spans the original run, including time between steps.
Missing/invalid explicit configuration, missing accounts and mismatched existing
account configuration fail closed. `--real` with this configuration is rejected
before provider credentials are read. No account is initialized by the runtime.

For each invited subject, run the operator command (paths below are placeholders):

```sh
CJ_ENV=local uv run --locked python -B scripts/local_run_context.py \
  --conninfo-json conn.json --auth-dir auth --run-context context.json \
  --subject alice init-budget
```

First initialization records immutable scope protection in the same transaction as
its explicit quota account, under the original MESSAGE scope lock. Unacknowledged
legacy work (including inactive conversations) refuses first activation. Finish that
original work first or use a new local subject; do not reset or delete it. All later
messages in this activated scope require this mode, including ordinary messages.
Their immutable requirement is committed with the receipt, NEEDS binding and outbox.

Repeating identical initialization preserves activation and the ledger; a changed budget for the
same account/period is rejected. To test answer refusal use budget1 and send two
ordinary messages. To test draft refusal use budget1 and send one `consider_trip`
message with the NEEDS registration below. Budget2 permits its answer and draft.

Create the conversation through the authenticated `PUT /v1/conversations` first.
Supply the real NEEDS command bytes in a separate file, for example:

```json
{"action_id":"manual-1","needs_id":"needs-1","expected_version":0,"source":{"kind":"manual","text":"Local operator supplied party size"},"changes":{"party_size":{"state":"known","value":1}}}
```

Then use the same operator flags with `put-needs --input-json needs.json` and
`bind-needs --conversation-id <original-id> --needs-id needs-1`. Registration is
immutable for that conversation generation. It is M1 local scaffolding, not App
selection semantics. A later edit must use a new action ID and the original current
version. The server captures the revision in the message receipt transaction;
replaying original MESSAGE-send.1 bytes never captures a newer revision.

Start the normal API with `CJ_LOCAL_AUTH_DIR`, `CJ_LOCAL_CONNINFO` and
`CJ_LOCAL_RUN_CONTEXT` set. Run the worker with the same files:

```sh
CJ_ENV=local uv run --locked python -B scripts/run_worker.py \
  --conninfo-json conn.json --auth-dir auth --run-context context.json --once
```

`GET /v2/run-draft-status?message_id=<original-id>` uses the same development token
and returns RUN-draft-status.2. Answer exhaustion is `run_status=failed` with
`budget_exhausted_stage=answer`; draft exhaustion preserves the answer and reports
`draft_outcome=budget_exhausted`, stage `draft`. v1 remains unchanged and refuses
new outcomes it cannot represent. Reopening/querying never resends the model call.

On period rollover, retain the exact prior `current` profile under `history` and
provide a non-overlapping new current profile. Provision the new account explicitly.
Recovery locates the original step under retained profiles and never substitutes
the new account. Missing historical configuration leaves recovery unavailable;
restore the original profile, then reconcile the same run. Unknown claims keep
their exposure; there is no reset or automatic retry. Configuration-clock injection
in the host test checks period selection, not elapsed wall-clock production behavior.

The formal worker now requires `CJ_LOCAL_RUN_CONTEXT` / `--run-context` before
any pending work executes, including previously unactivated local scopes. Its CLI
rejects `--real` before credential loading. Original history remains a safe read;
missing configuration does not grant execution or automatic legacy migration.
Legacy pending work is retained, not rebound to a new attempt/period or resent.
Domain-only synthetic test seams are not formal worker entry points.

Activation is one-way. Rollback must stop the worker and preserve migrations14–17,
markers, ledgers and original period files. Do not restore a worker that ignores the
markers, delete/reset accounting, or run down on populated protection tables.

Evidence entry: `uv run --locked python -B scripts/pg_suites.py local_run_host`.
It exercises the formal factory and actual operator/worker subprocesses, plus
clearly marked local FakeProvider/ACK/config-clock fault probes. Module interleaving
and permission probes remain in local_needs_fence, local_budget_exit and
local_context_schema. No fixture is presented as native App, cloud or real-model
acceptance; A line owns the remaining native budget presentation checks.


## Registered mode (`CJ-LOCAL-RUN@2`)

Use the same explicit `meter` fields and period rules, but set the top-level version
to `CJ-LOCAL-RUN@2` and provide `output_limits` for **model**, **tool**, **memory**.
For example `{"model":1000,"tool":1000,"memory":1000}`. This config sets bounds;
it does not register a business tool, task producer or arbitrary Python executor.
History profiles retain the same protocol's original limits and meter parameters.
Do not reinterpret an old @1 pending invocation with @2 configuration.

Run the same operator `init-budget` command with the @2 file. Activation uses the
0017 database boundary under MESSAGE scope lock and refuses any unacknowledged
message or queued/running RUN. Existing account/unknown exposure is retained; an
existing profile is idempotent. Drain/reconcile original @1 work under its original
configuration before upgrading. Never reset data or switch subject/period to retry
an uncertain original. Local validation uses fresh private databases and development
identities; it does not migrate production or historical accounts.

@2 stores the new receipt requirement, one immutable RUN account/period and a
separate original operation for each stable key. The current production registry
contains only `model.answer` and `model.draft`, using FakeProvider. The shared core
supports the canonical three kinds, but controlled tool/memory infrastructure tests
are not business producer acceptance; actual integrations remain #243.

Old @1 configuration/consumers cannot execute new-mode work or submit old markers
to an upgraded scope. Both protocols keep the existing public message bytes and
RUN draft-status versions; no public execution/registration field is added.

The CLI emits minimal JSON audit records on stderr before dispatch, containing
server run/attempt IDs, kind, stage, unit and UNKNOWN/null confirmed units. A
`prepared` record is not a receipt or a statement of fees: correlate its IDs with
the original persistent operation/ledger and final RUN status. No prompt, token,
client message_id, subject or raw provider response is logged. The stdout outcome
uses the server run_id. Audit/adapter initialization precedes final admission;
no mutable logging callback is inserted after the final check.

Evidence entry: `scripts/pg_suites.py registered_exit`, included in the default
gate. This exercises actual @2 API/operator/worker plus clearly marked three-kind
PG infrastructure and ACK/timing faults. Real fees/cloud remain UNRUN.
