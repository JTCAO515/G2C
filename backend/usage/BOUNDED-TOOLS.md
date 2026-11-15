# Code-owned smaller tool reservations

`InvocationInput(..., tool_output_limit=8192)` declares a smaller output bound
for one code-owned tool registration. The default `None` retains the original
profile value and original input/command format. The new declaration must be
a positive integer no larger than the original tool profile. Model and Memory
registrations cannot use it. It is not a client option or a new provider grant.
The registration must establish its complete serialized reply bound; page size
alone does not establish that bound. Existing stream accounting rejects output
above the recorded original command limit, retaining original uncertainty and
charges. No truncation, omitted source, quota increase or refund is introduced.

`reserve_final_model=True` still takes the minimum of this declaration and the
actual original remaining run output after the configured final-model reserve.
A smaller remaining amount may still be refused or exceeded. Each real send
keeps its own original operation, Meter claim and financial exit; concurrency
cannot combine multiple HTTP requests into one charged operation.

`RegisteredExit.read_run_capacity(binding, guard=..., max_response_bytes=4096)`
returns `G2C-original-run-capacity.1` bytes from the original account/period.
The caller supplies its live canonical authority guard, not a cached permission.
It shares the protected status reader's READ ONLY transaction, original scope
binder, period/binding checks, commit-ACK and cleanup withholding. No ledger
write or dispatch occurs. Values are point data; a subsequent original reserve
remains authoritative against competing work.

The result contains version, limits_source=`original-account-config.1`,
admission=`NOT_GRANTED`, unit, output_unit=`Python str characters`, original
period_start/period_end, run_state (`not_started`, `open`, `cancelled`),
remaining_calls, remaining_steps, remaining_tools and remaining_output.
`not_started` means no reservations in the exhaustive validated original ledger;
a missing account or mismatched period is unavailable, never fresh capacity.
Cancelled runs have zero run capacity while existing unknown holds remain in
the account. Output is measured by the original stream's `len(str)`, not tokens
or wire bytes. This is the original base profile, not a larger native4 profile.

This does not change existing 800 credits, 24 steps, 12 tools, 65536 run output,
per-call profiles, time limits, role/identity, ledger codec or stored commands.
It does not make the future six-model / forty-five-tool pipeline eligible.
