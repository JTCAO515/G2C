# BASE@1.0 / C0

Owner: CJ-005, branch `cj/005-foundation`. `openapi.json` is the only current wire source. `baseline-1.0.0.json` is an immutable compatibility fixture, never a runtime/generator input. Domains add their contracts here only through the assigned shared writer. No AUTH, business resources or RUN/SSE event types are frozen by this version.

`GET /v1/probe` proves the API process answered; it says nothing about auth, database, model or other readiness. Every response has a server-generated UUID `request_id` and matching `X-Request-ID`. Incoming tracing headers are not trusted or echoed. The ID identifies one HTTP attempt, and never grants identity, deduplication or side-effect retry authority. Stable original action IDs and lookup APIs belong to future domain owners.

Errors carry open strings `code` and `category`, bilingual safe messages, explicit `outcome` and `recovery`. Unknown code/category must remain visible as generic failure. Unknown outcome/recovery enum values must fail decoding visibly, never become success or authorize retry. `reconcile_original` means preserve the original action and use its domain lookup; BASE supplies no lookup route. Transport loss alone is UNKNOWN; never manufacture a server receipt or reuse request_id as an action ID. Unknown/conflict fixtures define the envelope only; the probe does not simulate business writes or these outcomes.

Object extra fields are ignored by current Python/Swift models; tests exercise this using the old generated Swift client. The conservative compatibility guard still rejects all changes to existing definitions, including optional additions, until an explicit version/consumer review updates the historical fixture. New paths/components are allowed. This is intentionally narrower than a general semantic OpenAPI diff. Consumer confirmations: CJ-005 local Python/Swift checks only; downstream acceptance remains pending Main routing.

From repo root (Python 3.14 was tested; >=3.12 declared but older runtimes UNRUN):

```sh
. ./scripts/env.sh
uv sync --locked
./scripts/generate.sh --check
./scripts/check.sh
./scripts/swift.sh test
CJ_ENV=local uv run --locked uvicorn cj_api.app:create_app --factory --host 127.0.0.1 --port 18765 --no-access-log
```

`CJ_ENV` must be explicit `local`; every other environment fails startup. This is a local-only foundation. No production defaults, secrets, database, auth, model, CORS or public listeners are configured. Do not expose this unauthenticated probe as a business API. `--no-access-log` prevents URLs/query values being logged; error responses discard input/exception payloads. Future domain routes must use safe error handlers and register sensitive fields before activation.

`backend/migrations/manifest.json` reserves monotonically numbered PostgreSQL migrations with SHA-256. `0001` initializes only a fresh schema/ledger; it is not a migration of old data. Applying it, validating an empty PostgreSQL database and rollback are UNRUN until C2 resources are authorized. Never apply it to an existing/shared database. Later domain owners add migrations with forward/backward client compatibility and reviewed data rollback plans; no automatic destructive downgrade.

`backend/storage-registry.json` is the mandatory private-storage/external-processing entry point. Current entries are not provisioned, retention and cleanup hooks unresolved. Before storing private data, each owner must enumerate sensitive fields, server principal binding, retention, deletion hook, and restore/revocation fence. The registry does not implement cleanup. Probe requests persist no user content; request IDs exist in response memory only. No old credentials or data are used.

C2 requires an approved new isolated auth project and login/invitation policy, disposable PostgreSQL target with least-privilege migration/runtime identity, private storage/retention choices, and device-reachable HTTPS endpoint/certificate/network scope. Resource names, region, budgets, credentials and deployment authority are not supplied or inferred. C2, true account isolation, persistence/restore and physical device acceptance remain UNRUN; Issue #5 stays open.

Dependencies: `uv.lock` records Python transitives; `ios/Package.resolved` records Swift revisions. FastAPI/Pydantic use MIT; Uvicorn uses BSD-3-Clause; Apple's generator/runtime/URLSession use Apache-2.0 (Swift exception where shipped); datamodel-code-generator uses MIT. Exact installed distribution metadata and Swift checkout LICENSE files are available for review in isolated `.venv` / `ios/.build/checkouts`. Those upstream licenses do not license CJ's source or settle product legal terms. No unverified Agent/memory/rendering packages are bound into this foundation.
