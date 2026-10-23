# CLEANUP-PROGRESS-WIRE@0.1.0-rc.1

Current ALLOWED account reads only its existing original cleanup operation:
`GET /v1/account-cleanup-progress?operation_id=<original id>` with bearer AUTH.
This route does not start cleanup. It cannot create/recover/retry/import receipts,
invoke hooks, restore permissions or issue post-logout credentials.

Source: CJ-024 runtime `514aba717dd0e0a7f7783b6d9072d347cdb0a623`, evidence
`6635bb9b301b567edeef91689c0097b25c576ba9`; AUTH runtime
`8b6abb236cf10c1865a9cc8c6155bd8ac732c07e`.
`cleanup_progress_pins.json` fixes every runtime file hash. Export via
`scripts/prepare-cleanup-progress-deps.py`; producer worktrees stay read-only.

The trusted host supplies local environment, strict issuer/audience/key verifier,
current access provider, explicit max_steps (1..128), final max_response_bytes
(1..65536), and `resolve(principal, environment, guard)` returning the exact
canonical cleanup PostgreSQL Repository, derived Scope and exact original guard.
`create_composed_app` shares the MESSAGE AdmissionChecker. Each HTTP request
creates a separate canonical ProtectedReadBoundary with that checker; contexts
are never cached. Optional dependencies must be complete; absent config returns
503. Caller owner/environment/capability/extra query fields return 400.

200 requires nonnull `{request_id, progress}`. `progress` contains only
`operation_id, revision, status, steps, reasons`. Each step contains exactly
`target, state, reason`; status/state/reasons use fixed enums from OpenAPI.
No raw receipt, confirmation, invocation, journal, scope or free-form gap details
are exposed. No truncation, empty success or null progress replaces unavailable
storage. Current denial is 401/403, access unknown is 503; unavailable original
operation/storage/projection is safe BASE 503. Headers are request-id/no-store.

The official generated Python model validates the whitelist. The entire BASE
JSON bytes (including server request_id) are encoded inside the original native
protected lifetime, then bounded. Canonical query verifies exact original journal
and derived state with recover_inflight=False. Final storage close, domain guard,
outer AUTH and callback-free captured binding checks finish before those exact
bytes are returned. In-flight stays in-flight; unknown stays unknown. The query
uses SELECT without FOR UPDATE and cannot dispatch a hook. Missing hooks, pending
backups, offline devices and external retention remain visible barriers.
`complete` describes only the original frozen metadata operation; it is never
proof of universal physical account deletion or production acceptance.

OpenAPI is authoritative; official generation only. All pre-existing operation
and component definitions remain unchanged. No UI, schema migration, grant,
production resource, provider, backup policy or accepted architecture is added.
The cleanup metadata registry entry records sensitive contents and unresolved
retention/cleanup/restore policy; production activation remains blocked.

Run scoped checks:

```
UV_OFFLINE=1 ./scripts/check-cleanup-progress-wire.sh AUTH_REPO CLEANUP_REPO
UV_OFFLINE=1 ./scripts/check-generated-cleanup-progress.sh
```

The former uses canonical AUTH/cleanup implementations, original journal replay
and controlled DB-API callbacks; it does not connect to PostgreSQL. The latter
builds official CJAPI and executes a generated Swift consumer with fixture
transport. Those source-f87 checks do not establish a real account/API/database/UI chain.
Subsequent author integration in `evidence/cleanup-progress-live/REPORT.md` adds
actual new private PostgreSQL + loopback HTTP + official Swift-client evidence,
using canonical AUTH with synthetic keys/accounts. It does not establish real
account C2, UI, cleanup hooks or production authority. Producer 6635bb9 evidence
remains separate. The new private instance and HTTP server were stopped; no old
cluster was restarted or reused. Main-owned independent Review/Testing/Publish
gates remain separate; Issue #5 remains open.
