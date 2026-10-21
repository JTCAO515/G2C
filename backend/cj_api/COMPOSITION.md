# CJ005 receive / receipt-query composition candidate

Source base: `b510b6ca7661ead67e8a719c53318545d5cb2021`; early wire proposal `2331bdadbbcce6e67663581888797fd96cd8d3bc`. Original candidate: `d886677a805db51759a3116f8d2c0d4f3b8dddb3`; this report records its historical checks. Current fixed-source and nullable-consumer repairs are recorded in `PIN-UPDATE.md`. Branch `cj/005-foundation`, original assigned clone. Requested project default gpt-6.1-sol/medium; effective UNKNOWN.

## Scope and fixed consumer confirmation

Original AUTH source `79f88b6552da1bd3d4b27e22f64a158bddf2853b` (superseded per PIN-UPDATE.md), MESSAGE source `cec92299aa77e74baafba473ecf9db7b926fbe4e`, eight runtime source SHA256s in `composition_pins.json`. Main relayed both owners' final explicit acceptance of actual 2331bdad receive/query wire, including raw bytes/media, opaque query IDs, nullable receipt meaning, trusted principal/gate and BASE error mapping. It was not inferred from tool ACK. Main also relayed CJ009's exact cec92299 rollback-source confirmation: failed commit-stage gate has no reliable successful-rollback receipt; commit_possible=false cannot authorize retry. New AUTH profile f3c8e507 is deliberately not consumed in this batch.

This candidate adds only POST `/v1/messages` and GET `/v1/message-receipts?message_id=...`, plus explicit internal dependency composition. No AUTH endpoints, UI/CJAuth/CJShell, page/cursors, conversation provisioning, pending dispatch, RUN/SSE or provider calls. The canonical `contracts/api/openapi.json` remains the sole current generator source; historical `composition-schema-proposal.json` is explicitly not consumed. BASE 1.0 schemas and existing probe definition remain unchanged; MESSAGE wire RC is an additive narrow slice, not MESSAGE/AUTH@1.0 release.

- POST octet-stream body is passed as original immutable bytes into the actual pinned Command/Boundary. No JSON reserialization, trim or Unicode normalization. Stream bytes are bounded by a mandatory positive host limit before full buffering, regardless of Content-Length. Wrong media/encoding, oversized input, duplicate/unsupported JSON fields and invalid domain values use BASE errors.
- GET decodes query percent-encoding exactly once, rejects repeated/extra/invalid parameters, preserves opaque IDs including plus/slash/percent/ampersand/non-ASCII/outer whitespace. Only Stored.receipt is projected; Stored.raw/text never leave this route. Null only means not observed in this scoped ledger, never authoritative not_received or permission to resend. Exceptions/denial/generation invalidation do not become null.
- Successful original/repeated receive still rechecks current AUTH and creation generation via the actual Boundary. Receipt output is strictly validated with no type coercion/fake field filling; run ID factory must return nonblank strings before inserts. Repository/provisioning must supply valid generation/sequence; malformed postcommit receipts produce unknown rather than a fabricated success.
- Duplicate or merged Authorization is refused. Error responses do not include token/principal/internal reason or exception text. request_id/header are server-owned HTTP-attempt tracing, not action IDs.

## Explicit host wiring and default failure

`create_composed_app(environment=..., jwt_configuration=..., verification_keys=..., access_provider=..., resolve_repository=..., new_run_id=..., max_body_bytes=...)` uses actual PyJWTVerifier → AdmissionChecker → Boundary. All dependencies are required. It accepts local environment only and also inherits create_app's explicit `CJ_ENV=local` requirement. No credentials/default identity/key/DB mapping or fallback is invented. Root Python range >=3.12,<3.15, fixed PyJWT[crypto]2.15.1 and cryptography50.0.2 match the AUTH pin; owner checks on Python3.14.7 only, 3.12/3.13 UNRUN.

The resolver is trusted host code and must bind approved environment/profile + verified issuer/subject to stable storage; token times cannot determine partitions. Only approved integration/provisioning may establish actual scope rows/chats, credentials, DB roles or authoritative membership/session lookup. No default repository, process-memory production store or accepted invite policy is supplied. Policy reads must be bounded by the host; this synchronous interface does not implement timeout/freshness/atomic revocation.

Existing zero-argument `create_app()` remains local-only probe configuration. Its two advertised MESSAGE paths return explicit 503 BASE unavailable when composition is absent; it never invents identity/receipt or quietly uses a test double. `scripts/env.sh` includes the expected monorepo AUTH/MESSAGE paths for Publish integration; missing or source-hash mismatched internal packages refuse composition. Author tree does not acquire/write backend/auth or backend/message. Source imports are verified against fixed local files, not a claim of a security boundary against arbitrary trusted-host Python monkeypatching.

## Reproduce without remote resources

From repository root:

```sh
. ./scripts/env.sh
uv sync --locked
./scripts/check-composition.sh /path/to/CJ007-git-repository /path/to/CJ009-git-repository
./scripts/check.sh
./scripts/generate.sh --check
./scripts/swift.sh test
```

The first script reads only the exact pinned Git objects, checks hashes and exports eight runtime blobs to `.local/composition-deps`, then runs tests importing those exports. It preserves existing differing exports rather than overwrite. No network fetch or working-tree read of either domain is used. Normal uv sync may require authorized dependency download to clone-local cache; no secrets involved. Publish must include original source commits before real monorepo composition; copied temp source is not committed or a second domain implementation.

Tests use actual pinned JWT crypto with per-test generated RSA keys, actual gate/domain/Boundary, isolated ASGI transport and explicit transaction doubles. Keys remain in memory, tokens are not stored in evidence. No listener, JWKS fetch, SMTP/OAuth account, old VP, cloud, PostgreSQL, migration or paid provider is contacted. This does not prove real DB concurrent isolation, crash durability, permissions, membership freshness/session revocation or revocation/commit atomicity.

## Results and four-stage matrix

`evidence/composition-tests.txt`: PASS 15 distinct tests, including eight NO/UNKNOWN stage subcases below. `evidence/base-regression.txt`: PASS canonical OpenAPI/examples/compatibility/registry check and existing Python4 regression. `evidence/generation-check.txt`: PASS generated Python/Swift byte consistency. `evidence/swift-generation-consumer.txt`: generated client compiled, existing four Swift tests PASS. New binary operation is generated as HTTPBody, never a reconstructed JSON input model; live Swift→composed API/iOS integration remains UNRUN. All are owner self-checks; independent Review/Testing pending.

| Gate stage | Write reached in transaction double | NO | UNKNOWN | Persisted rows in tested double |
|---|---|---|---|---|
| entry | No resolver/insert | 403 failed/do_not_retry | 503 unknown/retry_safe_read | 0 |
| transaction-entry | Transaction entered, no insert | 403 failed/do_not_retry | 503 unknown/retry_safe_read | 0 |
| precommit / commit check | Insert/enqueue reached, conn.commit not reached | 503 unknown/reconcile_original | 503 unknown/reconcile_original | 0 after double rollback; not proof of real PG rollback |
| return after successful commit | Insert/enqueue and successful transaction exit reached | 503 unknown/reconcile_original | 503 unknown/reconcile_original | 1; original receipt remains queryable after current access recovers |

Separate committed-but-ACK-unknown fault raises actual CommitUnknown; HTTP503 unknown/reconcile_original, original receipt can be queried without second run. All safe-read recovery values authorize only safe verification/query, never automatic POST/commit retry. Postcommit/uncertain rollback classification takes priority over ordinary identity denial. Caller must retain original action ID and exact bytes under the original bound identity; no new-key resend or fake rollback.

The initial test-harness run is preserved in `evidence/initial-test-harness-failure.txt`: importing/inheriting the fixture TestCase duplicated eight checks, and two inherited assertions referenced a reads counter absent from the wire transaction double. Factored the setup-only fixture so the original four tests remain, removed duplicate discovery, then added the four-stage matrix test: final 15 distinct tests PASS, no assertion weakened. FastAPI's existing httpx TestClient deprecation and generated Swift unused-public-import warnings remain visible; no warning suppression.

Source/contract or dependency changes invalidate their affected checks; unrelated C0, UI, provider and domain-owner evidence was not rerun as a substitute. Real DB/JWKS/OAuth/authoritative resolver/member/invite/session source, physical device, deployment, independent approval and full Issue5/8/10 acceptance remain UNRUN. No root README/brand, domain source, C2 preparation, migration or old database/security configuration changed.

Query-consumer correction: the original generated Swift4 checks did not exercise nullable receipt access; d886677 actually omitted that field due to unsupported type:null. Original generation byte-consistency/build results do not prove this query consumer worked. The failure, canonical-source fix and actual generated-type receipt/null/missing checks are in PIN-UPDATE.md; historical logs remain unchanged.
