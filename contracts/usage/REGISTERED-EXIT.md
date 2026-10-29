# USAGE-REGISTERED-EXIT@1 — one registered execution core

Issue #242, JT approval6497345414. Additive private composition protocol, not a
public HTTP schema or permission to activate real providers. M1 LOCAL@1 and its
immutable two-step source remain supported without rewriting their bytes. Generic
original associations use [RUN-USAGE-OPERATIONS@1](../run/REGISTERED-USAGE-BINDING.md).

## One authority and registration

Canonical Config/Command/Receipt/Meter remain the only accounting arithmetic and
ledger. A single execution core serves registered model/tool/memory operations and
the M1 facade; copying the reserve/claim/settle algorithm is not allowed. Registry
entries are reviewed host code, not request/config-supplied Python executors.
Unknown registration, unsupported origin/ABI, missing config or mismatched original
identity refuses before reserve/claim. A snapshot or ALLOWED boolean grants nothing.

Each actual outbound invocation reserves1 provider_call in local L1. Background
work must meter every outbound invocation, not count an entire task once. Monetary
cost is UNKNOWN, never inferred to be zero or equated with these units. Actual
business tool/background producers must prove their own accepted origins and
integration; generic binding/controlled-adapter probes do not complete those tickets.

Current formal business adapters are local Fake model operations. Real providers
are not enabled. The formal worker must reject --real before loading credentials;
manual provider_smoke is separately authorized L2 diagnostics, not a business path.
Any pending formal run_once work without explicit run_context must refuse before
RUN acceptance or invocation. Old results remain safe reads; old pending work is
not silently rebound or replayed. Existing owner harnesses migrate without removing
or weakening their security assertions; A files remain A-owned.

## Dispatch order

1. Trusted source proves owner/origin/currentness and positively commits a NEW
   original operation under RUN ownership/fence. Existing or uncertain acceptance
   permits original lookup only.
2. Under the RUN cancellation fence, obtain fresh canonical AUTH and original
   state, reserve and claim with positive ACK through Meter. Never obtain RUN locks
   while holding USAGE row locks; order remains RUN then USAGE.
3. Finish all mutable registration, adapter initialization, input materialization,
   logging and ledger IO. Release USAGE row locks. Recheck fresh AUTH/currentness
   and trusted clock, then directly advance the actual adapter's first step while
   the RUN fence still orders cancellation. No new callback/logging gap after the
   final check. Read contexts are not execution leases.
4. Enforce configured output/time limits, EOF and final authority. Only a trusted
   completion receipt can settle its original attempt. Unknown commit/execution/
   receipt retains original exposure; never retry, re-arm or optimistically refund.
5. Consumer publication retains its own source/NEEDS/currentness and RUN fences.
   Accounting settlement is not permission to publish or mark a RUN completed.
   Persist cancellation first; cancel only original unclaimed reservations through
   Meter. Late original receipts never revive a stopped RUN.

## Validation and audit

Validate raw config, DB rows/persistent bytes, external outputs and authority at
boundaries. Domain factories establish valid immutable values once. Do not add
callable/getattr/inspect shape probes for internal adapters, repeat own typed value
checks, or repeatedly replay validated rows. Existing security guard/session/type
checks and runtime coroutine closing remain where they carry safety duties.

Structured audit allows only server-generated run_id/attempt_id, kind, stage/result,
unit and confirmed units. Unknown units stay null/UNKNOWN. No client message_id,
scope/subject, prompt, header/key, raw response or exception text. Logging cannot
change accounting outcomes or mask the primary error; initialization/log callbacks
must occur before the final admission check. Use existing package-local patterns,
not a new cross-domain shared package.

## Required examples and acceptance

| Scenario | Required result |
|---|---|
| Allowed registered local call with valid original identity/config | Actual call occurs and original receipt is recorded; not an all-disabled demonstration |
| Missing config, denied/unknown current AUTH, unknown adapter or source | Zero new invocation; no fallback registration |
| Kind/registration/operation/bytes replaced | Refuse before a new accounting attempt |
| Read-only reconstruction after any ACK uncertainty | Original reconciliation only |
| Account's final allowance raced by separate runs | Canonical serialized Meter admits no over-allocation |
| Registry/audit/adapter initialization revokes AUTH or exhausts time | Final check prevents invocation |
| Cancel wins before start; or while invocation is already in flight | No later new call/publication; unknown exposure is not refunded |
| Malformed provider output or incomplete invocation | Unknown usage, never a manufactured settled/zero-cost receipt |
| Late original receipt after stop | Idempotent original settlement only |
| Fake tool/memory adapter used in infrastructure tests | Label controlled infrastructure evidence, not real business/fee acceptance |

Consumer acceptance requires actual formal host/operator/worker, canonical AUTH and
runtime private PG, cross-owner/period negatives, immutable original associations,
all ACK/cancel timing windows, limits and secret-free audit. Tests enter default PG
suites. Frozen public RUN/BASE fields are not expanded by this private protocol;
any new public output mapping requires its own explicit proposal. Real fees/cloud
remain UNRUN under L2 #32 authorization, actual producer loops under #243, App #244.
