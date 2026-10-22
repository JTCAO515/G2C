# RUN → USAGE synthetic first-step candidate

Parent RUN: b65d6ce07b3e0509d1347aa39071b4f1bea280f7.
Fixed USAGE: a6693615aa773ddcffff852a9860ec1703aa2681.
Canonical core SHA256: 149b0af63bdca59e7bf5ecfc7cf7b9857193a0761df5b0e20c860b3f1076ebfa.

Status: **15 local synthetic checks PASS; production composition HOLD with an
explicit known-gap counterexample FAIL.** Not a frozen API or enabled dispatcher.
No core, SQL, budget model, AUTH fields, sharedAPI or root lock changes.

## Implemented fixture scope

`backend/run/cj_run/usage_fixture.py` consumes the original Meter/Command/Receipt
classes, not copied budget calculations. It supports only the first queued RUN
step with one caller-supplied original started event (sequence 1). No agent loop,
second step scheduler, output generation, real tools or provider transport exists.

Construction fixes original Binding + Command. All methods reject replacement
bindings/commands, including a new attempt ID. This is a test fixture input
restriction, NOT a persistent authority. The caller must preserve original inputs;
losing them permits query/reconciliation only, never inventing replacements.

Absent synthetic_executor fails before reservation. Injected Python is trusted
fixture code, not a sandbox. Service.dispatch remains unconditionally disabled;
this fixture is never imported/registered by a host. No real executor is allowed.

The fixture reads queued state, reserves the explicit Command, rechecks queued,
claims once, writes the original started event through Service (including its
context/reentry fence), rechecks original attempt and RUN, then invokes the
synthetic executor. A returned original typed Receipt may settle usage, including
after cancellation. It never manufactures a completed RUN or answer from a fee
receipt, and never treats a RUN terminal event as a fee receipt.

ReconcileOriginal(stage) stops the invocation and preserves the original objects.
It is an internal exception, not a new public BASE error field. observe() is
read-only and always returns recovery=reconcile_original, even for reserved work;
there is no recovery method that executes. No default prices, units, budget,
clock, limits or fees are provided. Tests use explicitly synthetic-unit values.

| Failure window | Preserved result / permitted recovery |
|---|---|
| reserve ACK unknown | No claim/executor from this invocation; query original attempt |
| claim ACK unknown | No RUN start/executor; original reservation may be unknown; query only |
| claim succeeded, RUN start failed or ACK unknown | Zero executor calls; retain original unknown claim; read both originals |
| executor raised/ACK unknown | Original unknown claim remains; never automatic retry |
| settlement ACK unknown | RUN is not declared completed; query original attempt/receipt |
| cancellation during context hook | P2 core fence preserves cancel; no executor; claimed quota not released |
| cancellation during executor | Already in-flight synthetic action may return; original receipt can settle, RUN stays cancelled |
| RUN cancellation write failed | USAGE stop is not compensated; explicit partial outcome requires original-state reads |

cancel_fixture requires an existing reservation, checks exact command, stops
USAGE then writes the supplied original RUN cancellation. Either step may fail;
it exposes the stage without rollback fiction. Reserved work releases only through
canonical Meter.cancel; unknown claims remain held. This is NOT cross-store atomic.

## Concrete production blockers (do not infer authorization)

1. **Missing durable run→original attempt association.** Canonical RUN stores no
   attempt; Meter binds attempt IDs but permits another attempt for the same run.
   A fresh fixture supplied a replacement Command after old claim ACK loss can
   invoke a second synthetic executor while the old claim stays unknown. The
   deliberate `usage_boundary_probe.py` produces one call and FAIL in
   `usage-known-gap.txt`. Constructor pinning cannot fix this across instances.
   Main must route a canonical durable association/ownership contract to domain
   owners before real composition. This slice adds no second ledger or authority.
2. **No shared claim/cancel/admission fence.** Meter and RUN transactions are
   separate. Sequential reads and callback order leave a final check-to-call race;
   neither repeated snapshots nor a process-local lock proves cross-worker safety.
   Need accepted atomic boundary/fencing semantics spanning stop, current AUTH /
   context and one-shot exit. No optimistic release or compensating dispatch.
3. **Scope and provenance.** Meter has no public scope accessor. Trusted composition
   must bind the same stable issuer/sub/environment partition and preserve original
   command input digest/operation identity. This fixture neither guesses fields nor
   authenticates caller binding. Real AUTH check/revocation integration is absent.
4. **Interrupted RUN lifecycle.** Claim UNKNOWN is accounting, not RUN terminal
   unknown. Queued/running records can remain pending after interrupted composition;
   classification/timeout/reconciliation must be owned and explicit. No invented
   failure answer, new attempt or forced terminal is introduced here.

Thus the implementation only validates selected failure semantics with known
original fixture inputs. It does not establish safe real RUN→USAGE dispatch.

## Evidence and reproduction

`backend/run/evidence/usage-composition.txt`: 15 PASS using real pinned USAGE core
with synthetic in-memory repositories/executor; Python 3.14.7 (within USAGE
>=3.12,<3.15). `usage-known-gap.txt`: deliberate missing-durable-binding FAIL,
retained without weakening assertion. Main/Review/Testing must see both.

```sh
# Runs from repository root. Explicit local Git source; exports exact pinned blobs
# under backend/run/.local and refuses to overwrite differing exports. No network.
uv run --offline --no-project --with psycopg==3.3.4 python -B backend/run/tests/usage_composition_checks.py --usage-repo /absolute/path/to/cj-008-usage -v
# Expected FAIL until a future accepted durable association contract exists:
uv run --offline --no-project --with psycopg==3.3.4 python -B backend/run/tests/usage_boundary_probe.py --usage-repo /absolute/path/to/cj-008-usage
```

The existing offline Python environment selection includes cached psycopg, but
these scripts import no driver, connect no database, and do not use USAGE5c248ad's
repository. No new resources, provider/network, worker, fees or device checks.
Original core and prior evidence were not rerun because this slice does not alter
them; cancellation reentry is covered within the composition's targeted tests.
