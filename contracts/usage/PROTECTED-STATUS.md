# Authenticated original-attempt status consumer candidate

Consumes exact AUTH `8b6abb236cf10c1865a9cc8c6155bd8ac732c07e`,
CJ-AUTH-READ-CONTEXT@0.1.0-rc.1, without copying its source or changing AUTH/MESSAGE.
USAGE parent `ccf46f696f7b50977359e1b7dc2eaf8f2fb7dcf3`. Neither independent AUTH
acceptance nor USAGE storage acceptance implies this combination's acceptance.

`AttemptStatusReader(ProtectedReadBoundary, trusted_resolver, configuration=...)`
consumes the real public context; no local JWT/admission wrapper or permission
boolean. StatusReadConfiguration requires explicit environment, issuer, audience,
historical period bounds and response-byte limit. The existing host checker owns
JWT/audience/profile/facts; missing/unknown admission denies bytes. No environment,
period, scope, units or budget comes from the request. Only token + original attempt
ID enter read; optional project is trusted host code, not caller input.

Inside one synchronous original context, principal issuer/audience must match host
configuration. Resolver receives (principal, environment, period_start, period_end)
and returns the existing canonical PostgresRepository. Host mapping uses stable
issuer/subject/audience/environment and an explicitly authorized historical period;
never token refresh times, request owner or a newly provisioned ledger. AUTH context
does not itself authorize arbitrary historical periods; resolver must apply host's
accepted mapping. No fallback/default/scope creation.

Fresh AUTH runs at entry and before bytes escape (ProtectedReadBoundary); storage
stages are not re-checked (see "Trust boundary" below). read_status validates stored ledger's
period equals the selected historical period, performs READ ONLY SELECT, projects
only the minimal status, finishes final host envelope bytes inside ctx, commits the
read and closes cursor/connection. Close/encoding/scope/identity failures withhold
bytes. The original AUTH boundary rechecks current admission before returning exact bytes. No private transformation
may be added afterwards. Transaction completion unknown retains its original error,
not a current-denial fiction or permission to execute/retry a write.

Projection is original status/units/receipt, not current balance, financial charge,
new source permission or dispatch grant. Unknown confirmed units/output/receipt stay
null; zero requires an actual confirmed receipt. Old period results remain queryable
only via an explicitly configured authorized mapping, independent of current-budget
availability; mismatch fails closed. Historical queries cannot reset the ledger.

No route/HTTP schema/registry/root lock, no AUTH edits, no MESSAGE dependency, no
Meter mutator and no provider exit. Shared AUTH-USAGE-RUN check-to-call fence, live
revocation, real users/provider costs/product RLS/I acceptance remain UNRUN.

AUTH dependency: since ADR-0004 `cj_auth` ships in the same `cj` distribution and
is imported directly. `protected_status` no longer imports `cj_auth.read_context`
itself (2026-10-28, #186), so importing it does not by itself prove the boundary is
present. The trusted host composition (`cj_api`) must construct AttemptStatusReader
with the canonical `ProtectedReadBoundary`; no stub or older boundary is supported.

## Author validation and remaining gates

Source candidate `6f2b552d1b53792dfae88647dcb8ea155319c552` syntax PASS.
`backend/usage/evidence/protected-status-tests.txt`: 12 targeted checks PASS using
actual pinned AUTH modules/canonical types plus synthetic verifier/facts/DB callbacks.
Coverage: same resolver binding, entry UNKNOWN, resolver identity/UNKNOWN, missing
config/provider, historical period mismatch, cross-scope missing row, callbacks
through final close, completed envelope, commit-unknown/cleanup priority, reentry/
cancellation, and outer AUTH final-return revocation after the storage/domain checks.
Old read SELECT-only 13-unit/11-private-PG evidence is reused; no old cluster started.
No real account/token/network/PG/resource/provider operation in these new checks.

Run from repository root:
`uv run --offline --frozen --project backend/usage python backend/usage/tests/protected_status_checks.py`

The test requires the original sibling cj-007-auth clone containing fixed head8b6abb2;
exports exact blobs with hashes, refuses differing exports, and never fetches moving
AUTH. Source dependency is explicit, not an installed production pin or root registry
change. Independent AUTH, storage, combination and full Issue9/I conclusions remain
separate. Formal root wire and real resolver/provisioning/RLS are still pending.

## P2 final callback publication repair

Review found that the outer AUTH final provider callback could replace repository
scope or reader configuration while returning the same principal; old be473a9
returned 334 status bytes. Original two FAILs and original test source are retained
as evidence/review-final-binding-original-*; author pre-fix reproduction is
final-binding-before.txt (2 FAIL). No AUTH or standalone storage gate is revoked.

After ProtectedReadBoundary finishes its last provider callback and closes the
original context, the consumer now checks captured repository scope/connection
factory and reader boundary/resolver/config identities using only direct canonical
object fields. Then it returns the already encoded exact bytes. No further checker,
resolver, SQL, projection or callback is introduced, so there is no recursive
check-after-check chain and no new authorization context. AUTH remains responsible
for its original principal/context lifecycle; the closed context is never revived.
Scope and connection factory are also compared at each in-context guard.

Targeted validation: final-binding-after.txt has 14 PASS (12 affected lifecycle
checks plus both regression cases). Original Review assertion source is run against
the repaired local fixture in review-final-binding-after.txt: 2 PASS. These are
author reruns, not independent Review approval. Old FAILs remain unchanged.
No old suites, database clusters, AUTH source, root wire or dispatch paths changed.

## Trust boundary (2026-10-28, #186)

The final-binding comparison above and the per-stage domain guard were removed.
They guarded against the host replacing its own trusted reader configuration,
resolver or repository mid-request. AttemptStatusReader now checks principal
issuer/audience once, refuses a missing host mapping, and passes an empty stage
guard to `read_status`. Fresh AUTH runs at entry and before bytes escape in
ProtectedReadBoundary, so revocation during storage, close or projection still
withholds bytes. `read_status` keeps its own scope/connect, period, size and
READ ONLY checks unchanged.
