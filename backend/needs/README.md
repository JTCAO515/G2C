# CJ013 manual current-travel NEEDS candidate

The additive local runtime is documented in
[CJ-LOCAL-NEEDS@1](../../contracts/needs/LOCAL-RUNTIME-V1.md), with the separately
frozen [NEEDS@1.0 data codec](../../contracts/needs/V1.md) and
[unconfirmed preview](../../contracts/needs/PREVIEW-V1.md). The existing candidate
and default closed composition below remain available to their original consumers.
`CJ_LOCAL_NEEDS_PROFILE=manual-v1` explicitly enables manual API use; model preview
uses the existing registered worker with `--tools-profile synthetic-needs-v1`.
All current model evidence is synthetic L1; real models/services and App acceptance
remain separately gated.

Implements strict explicit-input validation, local companion applicability,
user-provided fixed intentions, partial corrections, immutable provenance/version
history, CAS and exact-byte original action receipts. Reuses existing AUTH checker
and response-lifetime pattern. No NLU, solver, Memory promotion, formal Trip write,
HTTP route, root migration, permission configuration or real-provider operation.

Contract and consumer gaps: [../../contracts/needs/README.md](../../contracts/needs/README.md).
`sql/candidate.sql` is **only** a new-empty-PG candidate, not a production migration.

## Reproduce in this checkout

```sh
uv sync --frozen --offline --project backend/needs
uv run --frozen --offline --project backend/needs pytest -q -s backend/needs/tests
```

Requires existing `/opt/homebrew/opt/postgresql@17/bin` and cached locked test
packages. Test harness creates a fresh random private directory under
`backend/needs/.local/`, initializes a new synthetic-only role/database, binds only
a private Unix socket (`listen_addresses=''`, port 56413), and explicitly passes
user/database/socket/port/empty password/empty passfile. Inherited `PG*` choices are
removed in the test process. It never reads a DSN, connects an old instance or
calls providers. Finally stops PG and preserves cluster/log/STOPPED evidence.

Tests use real transactions and synthetic AUTH facts. They prove neither real
account membership nor production RLS/cleanup, deployment, App, model or Issue I
acceptance. AUTH/SQL/storage composition must be confirmed by owners before wiring.

## Additive protected current-read projection

See [protected read signature](../../contracts/needs/PROTECTED-READ.md). The new
`cj_needs.protected_read.ProtectedReader` composes canonical AUTH8b with original
readers, strict storage close and final host/config/repository settlement. Legacy
write/UNKNOWN semantics and schema remain unchanged.

For the new targeted checks, first export the exact AUTH object from an explicit
read-only repository containing it (no source checkout changes or network fetch):

```sh
python3 backend/needs/tests/prepare_auth8b.py <local>/Documents/Codex/2026-10-21/cj-publish/Go2China
uv run --frozen --offline --project backend/needs pytest -q -s backend/needs/tests/test_protected_read.py backend/needs/tests/test_postgres.py
```

The ignored `.local/auth8b` dependency export has exact-source hashes in
`evidence/auth8b-manifest.json`. Tests select that fixed canonical package; no
moving source-owner module is imported. The final report reuses original domain
validation evidence because grammar/content/schema were not changed.
