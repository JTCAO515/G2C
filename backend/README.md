# Backend

One Python distribution (`cj`, root `pyproject.toml` + `uv.lock`). Each domain keeps its
import name (`cj_auth`, `cj_message`, `cj_run`, ...); `backend/cj_api` composes them by
plain import — the Git commit is the pin (ADR-0004).

| Entry | Purpose |
|---|---|
| `uv sync --locked` | Install everything, editable; no `PYTHONPATH` needed |
| `uv run --locked python -B scripts/test.py` | All non-database suites and check scripts |
| `uv run --locked python -B scripts/pg_suites.py [GROUP ...]` | PostgreSQL suites on fresh private Unix-socket clusters |
| `uv run --locked python -B scripts/migrate.py verify` | Migration chain up → down → up ([migrations](migrations/README.md)) |
| `scripts/check.sh` | Both of the above, as CI runs them |

PostgreSQL binaries: `CJ_PG_BINDIR` (else `pg_config --bindir`); suites that need a
specific major read `CJ_PG16_BINDIR` / `CJ_PG17_BINDIR`.

Per-feature run instructions in older `*-WIRE.md`, `*VALIDATION.md` and domain READMEs
(per-module `uv sync --project ...`, `check-*-wire.sh`, git-export or `--auth-repository`
arguments, Homebrew-only paths) predate ADR-0004 and are superseded by the entries above.
Their evidence is archived at tag `evidence-archive-2026-10-27` ([docs/evidence.md](../docs/evidence.md)).

## Local walking skeleton (P2a)

```bash
export CJ_ENV=local
uv run --locked python -B scripts/dev_auth.py init .local/dev-auth --invite alice
uv run --locked python -B scripts/migrate.py up --conninfo-json .local/conn.json   # your own empty local DB
CJ_LOCAL_CONNINFO=.local/conn.json CJ_LOCAL_AUTH_DIR=.local/dev-auth \
  uv run --locked uvicorn cj_api.local_app:app_from_environment --factory --host 127.0.0.1 --port 8765
uv run --locked python -B scripts/run_worker.py --conninfo-json .local/conn.json --auth-dir .local/dev-auth  # FakeProvider; --real needs a key
TOKEN=$(uv run --locked python -B scripts/dev_auth.py token .local/dev-auth --subject alice)
```

Flow: `PUT /v1/conversations?conversation_id=c1` → `POST /v1/messages` (application/octet-stream,
MESSAGE-draft.1 JSON) → worker answers → `GET /v1/run-events?message_id=...` streams the answer.
`conn.json` holds psycopg keyword arguments for a database you created; nothing here creates one.
Trip draft: send with `creation_intent: "consider_trip"`; the worker publishes proposal `p-<run_id>`
(`GET /v1/trip-proposals?proposal_id=...`), accept or reject with `POST /v1/trip-actions`
(canonical `[action_id, kind, proposal_id, candidate_hash, confirmation_ref]`), then
`GET /v1/trip-details?trip_id=...`. Real model check: `scripts/provider_smoke.py` (4 requests).
`scripts/pg_suites.py e2e` runs the same flow automatically on a fresh private cluster.

M1 local database isolation (#160): migration 11 creates `cj_m1_runtime` with no
superuser, BYPASSRLS, role/database creation or table ownership. MESSAGE/RUN/TRIP
tables use forced RLS. The migration/initialization identity remains separate;
`LocalDatabase` never uses it for application or worker SQL. It requires an explicit
local Unix socket and returns an IDLE non-autocommit runtime connection with no
scope installed. Each MESSAGE/RUN/TRIP transaction calls its `bind_scope` hook
after selecting isolation and before reading data; direct host `with` consumers
use the same entry. Both MESSAGE scope and derived TRIP scope are set LOCAL to the
transaction and expire on commit/rollback. Checkout and transaction entry reject
either nonempty M1 `cj.*` authority setting and close the connection; they never
overwrite retained authority. Plain unbound SQL after a completed transaction
does not automatically rebind. There is no production pool or caller owner setting. The
trusted backend sets this context: RLS does not defend against a compromised backend
deliberately issuing arbitrary scope-setting SQL. Other domain tables receive no
runtime grants. The worker requires the explicit local invitation directory and
checks invitations again before each model call. Missing role/schema/configuration
fails visibly; there is no privileged fallback. This is a local-only acceptance path,
not authorization to create roles, migrate data or deploy policy in a cloud database.
The local private cluster uses Unix-socket authentication; initialization passwords
and passfiles are not reused by the runtime role. Ambient `PG*`/`LIBPQ*`, service
aliases, remote hosts and host addresses are rejected before any connection.

The optional transaction hook preserves the injected DB-API interface for other
trusted repository hosts. The concrete M1 local factory always supplies it; a raw
runtime connection without binding is denied by the unchanged RLS policy. The
same-physical-connection tests simulate checkout/return leases over real private
PG and cover all 12 tables. They do not verify a cloud pooler's reset behavior;
the [C2 activation gate](c2-preparation/C2-CLOSURE-PLAN.md#pooler-激活门禁182) must
be satisfied before any pooler is enabled.

macOS note: Python 3.14 ignores `.pth` files carrying the `hidden` file flag. If imports
such as `cj_api` suddenly fail after `uv sync`, run
`chflags nohidden .venv/lib/python3.*/site-packages/_cj.pth`.

## P2c signed Trip confirmation preparation

`POST /v1/trip-confirmations` is additive. With an authenticated owner, send JSON
`{action_id, kind, proposal_id, candidate_hash}` (`kind` is `accept` or `reject`).
It returns the canonical proposal, `expires_at`, and `action_utf8_base64`: the exact
original five-field TRIP action, containing a server-issued confirmation reference.
Issuance does not write a Trip or record acceptance. The client must show that proposal,
retain those exact action bytes, and submit them to the existing `/v1/trip-actions`
only after the explicit user action. Unknown outcomes use `/v1/trip-action-receipts`
with the original action ID; do not regenerate bytes or replace the ID to retry.

The trusted host must explicitly supply the same `ConfirmationSigner` as issuer and
TRIP transaction validator. Use a dedicated random key of at least 32 bytes per
environment, supplied through an operator-approved secret mechanism, never a JWT,
client session token or model key. No key is created/read by this implementation.

```python
from cj_trip.confirmation import ConfirmationSigner
from cj_api.local_app import create_local_app

signer = ConfirmationSigner(key=confirmation_key, lifetime_seconds=300)
app = create_local_app(conninfo_path=conninfo_path, auth_dir=auth_dir,
                       confirmation_signer=signer)
```

References bind the verified scope, original action ID/kind, proposal ID/content hash,
expected version and expiry. The existing scope-locked transaction checks the proof,
and rechecks expiry using database time after its final AUTH guard. A committed exact
action replay returns the existing receipt even after expiry/key rotation; an uncommitted
old proof is denied. Keep a stable key for the intended proof lifetime; provisioning,
rotation and actual use with real identities require separate operator authorization.

Compatibility: without a signer, the new endpoint returns 503. `app_from_environment`
(the runnable local entry) always uses the signed path: it loads the dedicated key
`trip-confirmation.key` from `CJ_LOCAL_AUTH_DIR` (created by `scripts/dev_auth.py init`,
or `dev_auth.py confirmation-key DIR` for an existing directory; mode 0600, 32 random bytes)
and refuses to start without it. Only `create_local_app`'s default keeps the permissive P2b
callback, for existing tests; remove it once those tests use explicit signer composition.
iOS live writes are granted only by a host that uses this signed entry. No migration or
cloud configuration was changed.
