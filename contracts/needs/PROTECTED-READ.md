# NEEDS protected read/projection seam

`CJ-NEEDS-PROTECTED-READ@0.1.0-rc.1`, additive to c821b34. Not NEEDS@1.0 freeze.
This is the owner-confirmed producer signature for CJ035 to pin and consume after
independent gates. Full consumer/root entry remains closed until those gates pass.

```python
from cj_auth.read_context import ProtectedReadBoundary
from cj_needs.protected_read import ProtectedReader, ReadConfiguration

# Trusted host setup, never request-supplied owner/scope/config or allow flag:
auth = ProtectedReadBoundary(canonical_checker, max_response_bytes=explicit_cap)
reader = ProtectedReader(
    auth,
    resolve,  # resolve(TrustedPrincipal, environment: str) -> (fresh_connect, opaque_scope)
    configuration=ReadConfiguration(environment, issuer, audience, explicit_cap),
)
# Trusted, fixed domain projector; request only selects token/needs ID.
raw = reader.read(token, lambda operation, context:
                  project_current(operation, context, needs_id, limits=explicit_limits))
```

`canonical_checker` is existing AUTH AdmissionChecker. Required AUTH fixed source:
`8b6abb236cf10c1865a9cc8c6155bd8ac732c07e`, public
`CJ-AUTH-READ-CONTEXT@0.1.0-rc.1` ProtectedReadBoundary/ProtectedReadContext. No AUTH
logic/types copied or alternative principal policy. Import the new module directly;
legacy `cj_needs` imports keep their previous dependency surface.

The resolver is trusted server composition. It receives the current canonical
principal plus the captured explicit environment and returns the same **stable
connect callable identity** and opaque scope for that binding. Every actual
resolver call is surrounded by fresh canonical AUTH. It must use the supplied
configuration environment, not a hidden device/request environment or caller owner.
Environment/configuration changes must replace reader.configuration; no mutable
hidden environment selector is a supported host contract. No default configuration,
resolver, scope provisioning, production migration or registered root factory added.

`reader.read(token, project) -> bytes` accepts one synchronous trusted projector:
`project(operation: cj_needs.boundary.Operation,
         context: cj_auth.read_context.ProtectedReadContext) -> bytes`.
The operation is the **original canonical Operation**, preserving metadata,
Snapshot, Revision, detail and history semantics. In this lifetime only `detail`
and `revision` are allowed; act/query_action are denied and poison the read even
if the projector catches the denial. It does not grant generic business callbacks,
write/claim/dispatch, action recovery or arbitrary caller-selected projections.
CJ035's existing fixed projector/evaluator and its input/history limits stay owned
by CJ035; this producer does not reimplement history validation or feasibility.

Each original PG reader opts into strict close: an ordinary close exception or
cancellation withholds output; after successful close it immediately runs fresh
AUTH/current-environment binding settlement. This applies only to the new read
repository. Legacy Boundary, write transactions, receipts, UNKNOWN reconciliation,
schema and old persisted bytes retain their accepted semantics.

After the projector fully encodes **exact bytes**, the seam checks the explicit
output cap, re-resolves current host binding, and runs canonical AUTH checks.
The canonical AUTH boundary then executes its final fresh admission callback.
After that callback and context retirement, the seam performs only callback-free
comparisons of original reader/auth/resolver/configuration identity and values,
and original repository/connect/scope/guard/strict-close fields. A changed
configuration/repository during that final callback refuses the bytes. No resolver,
AUTH/provider callback, IO, lazy iterator or second encoding follows this last check.

All Operation and AUTH context handles retire on every exit. A read/close/cancel
failure is unavailable, never missing-data success, rollback proof or permission
to replace an original write action. Failures carry no private response bytes.
A successful full projection proves the checked read lifetime, not a global atomic
latest record across independent transactions; consumer's final Snapshot reread
and version equality remain necessary.

Scope of validation: real NEW private Unix-only PostgreSQL plus synthetic canonical
AUTH. Original two consumer FAILs are reproduced semantically by local tests:
ordinary close failure and trusted scope remapping on close now withhold. Final
AUTH configuration/repository mutations, cancelled/escaped handles, strict output
and read-only denial are also tested. CJ035 integration/independent gates, HTTP,
real accounts/App/provider and original Issue I acceptance remain UNRUN.
