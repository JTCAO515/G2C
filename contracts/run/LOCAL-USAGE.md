# RUN-USAGE-LOCAL@1 — local provider-call admission

Issue #170, JT approval 6488161293. Contract-first stage; consumers and formal host
activation arrive in subsequent ordered PRs. This does not activate Service.dispatch,
SyntheticFirstStep or LocalExit as a real executor. Historical FAIL/HOLD evidence in
USAGE-COMPOSITION.md and USAGE-BINDING.md remains historical evidence, not acceptance
of this composition.

Only CJ_ENV=local with FakeProvider is supported. Unit is provider_call, reserve=1
for each admitted answer/draft invocation; no money/token billing, tools, production
provider, cloud or payment. Operator configuration explicitly supplies budget,
period_start/end, max_steps/tools/output/seconds; invalid/missing configuration or
ledger refuses execution. No automatic budget default, period reset or new account.

The ledger scope is `u` + SHA256 of UTF8 compact JSON
[message_scope,"provider_call",period_start,period_end], separators comma/colon,
ensure_ascii=False. The canonical message scope is derived by the current verified
local issuer/subject/environment host, never request metadata. Provisioning creates
one ledger row per explicit period; original associations retain the original
ledger/period for read-only reconciliation across later periods.

Use canonical Meter/Command/Receipt, not a second arithmetic authority. Only the
approved runtime SELECT and UPDATE(ledger,revision) are granted on the existing
ledger; initialization owns INSERT. No runtime scope_id/format_version UPDATE or
DELETE/TRUNCATE. Preserve forced RLS and role capability checks.

Stage A commits the original STEP-USAGE association independently and acknowledges
it before reserve. ACK uncertainty permits original lookup only, no new attempt.
Stage B reacquires RUN fence, checks original binding/current identity/terminal,
then reserves and claims the original attempt through committed Meter transitions.
Only an acknowledged first claim permits provider first advance while RUN fence
still orders cancellation. Release USAGE row locks before invoking provider; release
RUN fence after first advance, as the existing stream design does. Lock order is
RUN then USAGE; never hold a USAGE lock while obtaining RUN.

Unknown reserve/claim/dispatch/settlement is not limit_exceeded. Do not reconstruct
attempts or dispatch after unknown claim. Completion provides an original idempotent
FakeProvider receipt for one provider_call and actual output length; incomplete
calls retain unknown exposure. RUN terminal events are not accounting receipts.
Cancellation persists RUN terminal first; Meter cancellation failure only permits
original cancellation/query reconciliation, not revival or optimistic refund.

Definite pre-answer limit rejection records budget_denied(value=answer) and RUN
failed; definite pre-draft rejection records budget_denied(value=draft) and a
separate draft_outcome=budget_exhausted, preserving the answer. These are ordered
under the RUN fence, never appended after a terminal state; cancellation winning
first remains cancellation. Completion/receipt ACK failures remain UNKNOWN.

Consumers must prove all commit/call edges and cancellation interleavings with real
private PG plus explicitly labelled fault injection. Contract/schema preparation
alone is not formal-host L1 acceptance. Dedicated L1 suite enters pg_suites.py in
host integration PR4 before this feature is considered complete.
