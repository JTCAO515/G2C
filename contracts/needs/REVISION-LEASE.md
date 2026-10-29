# CJ-NEEDS-REVISION-LEASE@1 — local publish fence

Additive trusted host seam; does not turn PROTECTED-READ rc.2's bytes projector into
an executor. Its allowed operations, retired context and final AUTH checks remain
unchanged. Lease/currentness is new functionality to be implemented and tested in
PR2, not implied by the old reader's PASS evidence.

Runtime NEEDS scope is `n` + SHA256(UTF8 canonical message_scope). Local operator
selection maps the exact (message_scope,conversation_id,generation) to one matching
needs_scope/needs_id. This mapping is M1 scaffolding, not product/App semantics.
No client-selected scope/version, text extraction or latest-record search.

At first message acceptance, acquire the shared advisory lease, verify the exact
selection and NEEDS record and persist needs_version/content_sha256 in
cj_message_needs_binding in the SAME MESSAGE receipt/outbox transaction. The
original message lookup precedes this: same bytes replay the original receipt even
after a revision, different bytes conflict. Never bind old accepted messages anew.
MESSAGE-send.1 wire and stored bytes are unchanged. Required-binding mode refuses
missing/foreign/unknown selection instead of silently accepting an unfenced run.

Lock key is the database function public.cj_needs_fence_key(scope):
pg_catalog.hashtextextended('CJ-NEEDS-FENCE@1:' || scope, 0). Readers use
pg_advisory_xact_lock_shared; row writer SECURITY INVOKER triggers acquire its
exclusive counterpart on INSERT/UPDATE/DELETE. Scope changes are rejected; TRUNCATE
is rejected while the fence protocol is active. Hash collision may serialize
unrelated work but never establishes ownership. No SECURITY DEFINER or extra role.

Runtime only SELECTs the three NEEDS tables. An authenticated, trusted local lease
uses a fresh READ ONLY transaction and plain SELECT under that shared lock; it must not use
SELECT FOR UPDATE or write permissions. Final canonical AUTH/current-identity
checks and strict connection cleanup withhold output on failure. Leases never
escape their authenticated host lifetime and are never cached as permission.

Publication acquires RUN then NEEDS then TRIP; an outer resource scope keeps the
NEEDS lease alive until the RUN receipt transaction exits. Existing Operation
transactions end too soon and cannot substitute for this lifetime. Never hold a
NEEDS lock during model IO. Recheck exact original version/digest immediately before
actual publish. Revision winning first produces context_invalid and zero publisher
calls; publication winning first preserves its committed candidate. Cancellation
winning first forbids publication, terminal state is not overwritten.

TRIP commit with uncertain RUN acknowledgement preserves possible publication and
requires original recovery, never compensating deletion or a new run. Lease loss
before invoke forbids the call; loss after commit withholds success, not a claim
of rollback. The runtime cannot bypass RLS or substitute a privileged connection.

Four LOCAL scopes (message/trip/needs/usage) must be installed at explicit transaction
entry by the verified host and rejected if retained at checkout; scope handling is
implemented in later PRs. Schema tests setting LOCAL directly test the DB policy,
not acceptance of that not-yet-implemented host.
