# CJ021 author result

Base: `8ea1b35756726f60727f10deaf157c40b8df1072`.
Branch: `cj/021-memory-withdrawal`. Root was absent before independent clone.
Write scope: `backend/memory_withdrawal/**`, `contracts/memory-withdrawal/**` only.

PASS — 21 targeted synthetic unittest methods, Python 3.14.7, standard library,
existing pinned MEMORY/CLEANUP/AUTH imports. [Actual final log](tests.txt).
Tests cover strict original bytes/IDs/versions, wrong scope, immutable historical
receipt recovery, item/source CAS metadata, missing/shared/ambiguous history,
old source IDs/summary/index/late-result references, unknown provenance, old epoch,
closed execution/public factories, original CJ024 states/restart reconciliation,
failed terminal refusal, finite manifest completion retaining CJ021 blockers,
missing hooks, original operation/confirmation/manifest drift, full-target shape,
and missing or inconsistent original cleanup receipt bytes. These are validations
of synthetic observations; no durable withdrawal or genuine authority is claimed.

PASS — 17 consumed/inspected inputs matched fixed Git blobs and SHA256, recorded
in [inputs.json](inputs.json). No moving owner source consumed. Only MEMORY domain,
CLEANUP core and its AUTH interface imports are needed at runtime. No dependency
installation, DB cluster, port, listener, secret, global setting or shared registry.

FAIL preserved — first command used system Xcode Python 3.9; existing AUTH union
type annotation failed at import, before tests. See [initial-failure.txt](initial-failure.txt).
Corrected the command to the already installed Python 3.14.7. Initial 20 tests
passed; adding validation of bare/inconsistent cleanup flags justified the final
21-test run. There was no observed domain-test FAIL in this candidate. Existing
upstream/native FAIL records were neither modified nor rerun.

BLOCKED — no public same-tx full source-history/reverse-reference/retombstone
producer; CJ019 lifecycle adapter accepts only active/disabled receipts; no
single-item cleanup confirmation/hook mapping; retained-chat ingress, real RUN
publication and actual derived-store cleanup are not integrated. The exact
[owner seam request](../../../contracts/memory-withdrawal/SEAM-REQUEST.md) names
the minimum changes. No private SQL workaround, status-update-only deletion,
second MEMORY/action ledger or guessed source/retention policy was added.

UNRUN — persistent withdrawal, PostgreSQL/storage/permissions, real AUTH or provider,
actual model context, UI/device, source-history physical cleanup, independent
Review/Testing, CI, deployment, release and full Issue26/I acceptance. No hooks
invoked, physical deletes, fees, account operations, pushes, PRs or issue changes.
No source input or cleanup finite-completion fixture proves whole-item deletion.
