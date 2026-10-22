# CJ015 guarded synchronous projection seam

Additive on 0e2c3241825d81b89cc7bdb2f2c6daa967038068; formal API remains CJ005.
Main/CJ005 consumer confirmation PENDING. Reuses the accepted MEMORY principles
(request lifetime, sticky failure, final serialized guard, original-op recovery),
not its domain/authority implementation. No new permission source or wire schema.

`Boundary.with_operation(token, operation) -> bytes` is the route composition entry.
Only trusted server composition supplies operation. It receives a request-lifetime
ctx exposing:
- act(Action) -> Receipt (at most one action per callback)
- query_action(action_id) -> Receipt | None
- detail(trip_id) -> Trip | None
- list_trips(after='', limit=20) -> list[Trip]
- proposal_detail(proposal_id) -> ProposalDetail
- read-only metadata -> frozen OperationMetadata(principal, scope)

Metadata uses the existing AUTH TrustedPrincipal and the ACTUAL captured repository
scope. It is server-side input for projection/cursor codecs, never client owner or
new authority. No raw repository, connect, guard, publish or retire entry is exposed.
Captured checker/resolver/confirmation configuration identities, repository.connect,
repository.confirm and actual repository.scope must remain unchanged at each guard,
checked before AND after fresh AUTH. Scope cannot drift even if checker stays ALLOWED.
No API caller needs _repository, _proposal, a new wrapper, or private introspection.

Sequence: AUTH bind → fresh entry after resolver → callback → each repository's
transaction/commit/private-return checks → callback JSON projection/size validation/
UTF8 encoding → fresh final serialized_return → exact bytes returned.
Callbacks with no DB access also undergo entry/final guard. The callback must finish
all projection, validation and encoding synchronously and return type bytes exactly;
no coroutine, iterator, async generator, lazy response or object is returned. It must
not send/stream/store private output itself. CJ005 returns the exact resulting bytes;
no delayed private projection after this boundary. JSON format and output size policy
remain CJ005's existing formal wire responsibility, checked inside callback.

Any guard failure/interruption is sticky; callback catching it cannot return private
bytes or resume ctx operations. All ctx DB failures also block its further use.
Context expires in finally; cross-thread or active nested-request reuse is denied.
The original context cannot be used after the callback, even for public metadata.
A context is not a cryptographic token or sandbox against malicious trusted Python.

OperationWithheld exposes only action_id, commit_possible, recovery. For a submitted
Action its original ID is captured before act; known return, CommitUnknown, cancellation
or postcommit projection failure retain recovery='reconcile_original'. A swallowed
guard failure also ends withheld. Precommit cancellation has commit_possible=False
for this attempt, which does NOT prove no prior original-ID attempt committed.
Exceptions/interruptions after a possible commit never become not-received or success;
no private receipt is attached to withheld output. Caller preserves exact original
Action bytes and queries its original ID through fresh admission. Existing normal
precommit validation/conflict/denial exceptions remain distinguishable if propagated.
Repository commit_possible is conservative (including committed read transactions),
not evidence of a business write; action_id=None never implies an action was created.

Old Boundary act/query_action/detail/list_trips/proposal_detail methods remain internal
compatibility for existing callers/tests. Their object-return guard is NOT a finalized
HTTP projection boundary; CJ005 routes must use with_operation. No removal until
consumer integration is confirmed; a separate coordinated change may narrow them.

## Exact list consumption

Ascending opaque ASCII/UTF8 trip IDs, explicit PostgreSQL C byte collation; after is
empty start or full last ID. limit integer1..100. Public projection can set next_after
= last row.trip_id for ANY nonempty result, else null. This is a continuation boundary,
not proof another row exists; do not fabricate has_more. The next request can be empty.
Live keyset traversal, NOT snapshot: inserts before cursor may be missed, later inserts
may appear. All fields and rows belong to the captured server scope. Public encoded
cursor handling, if any, stays CJ005-owned and uses ctx.metadata inside the callback.
