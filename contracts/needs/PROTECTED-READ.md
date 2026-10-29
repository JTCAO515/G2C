# NEEDS protected read/projection seam

`CJ-NEEDS-PROTECTED-READ@0.1.0-rc.2`, additive to c821b34. Not NEEDS@1.0 freeze.
rc.2 (2026-10-28) removes mid-read re-checks of trusted host composition; see
"Trust boundary" below. Signature unchanged.
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
principal plus the reader's explicit configuration environment and returns
`(fresh_connect, opaque_scope)` for that principal. It is called once per read,
after the canonical AUTH entry check. It must use the supplied configuration
environment, not a hidden device/request environment or caller owner. No default
configuration, resolver, scope provisioning, production migration or registered
root factory added.

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
cancellation withholds output. This applies only to the new read repository.
Legacy Boundary, write transactions, receipts, UNKNOWN reconciliation, schema and
old persisted bytes retain their accepted semantics.

After the projector returns, the seam requires exact `bytes` within the explicit
output cap. The canonical AUTH boundary then runs its final fresh admission check
before any bytes escape, so revocation or identity change during the read refuses
the output.

## Trust boundary

Checked: canonical AUTH admission at entry and immediately before return
(ProtectedReadBoundary), principal issuer/audience against configuration, read-only
operation lifetime, strict close, exact bytes and output cap. Not checked: the
host's own reader, resolver, configuration and repository objects. They are
trusted server composition and are not re-resolved or compared during a read;
a host that replaces `reader.configuration` affects subsequent reads only.

All Operation and AUTH context handles retire on every exit. A read/close/cancel
failure is unavailable, never missing-data success, rollback proof or permission
to replace an original write action. Failures carry no private response bytes.
A successful full projection proves the checked read lifetime, not a global atomic
latest record across independent transactions; consumer's final Snapshot reread
and version equality remain necessary.

Scope of validation: real NEW private Unix-only PostgreSQL plus synthetic canonical
AUTH. Ordinary close failure, AUTH revocation/identity change during the read,
cancelled/escaped handles, reentry, strict output and read-only denial are tested.
rc.1 tests for host scope remapping on close and host configuration/repository
mutation during the final AUTH callback were removed with those checks. CJ035 integration/independent gates, HTTP,
real accounts/App/provider and original Issue I acceptance remain UNRUN.

The separate [REVISION-LEASE.md](REVISION-LEASE.md) local publication fence does not
change this read-only signature or permit side effects in its projector. Its host
consumer is independently gated; this reader is not a publication lock.
