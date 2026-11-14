# Original database release witness

`NativeReleaseWitness` reads the existing Hong Kong checkpoint release protocol.
The host supplies its actual runtime database, original scope, control directory,
current qualification guard and the existing `deploy.hk.checkpoint` module.
None of these are task, candidate or client-selected values. No production
caller or configuration activation is added by this slice.

The reader verifies the signed `release.json`, compares it with the actual
`cj.deployment_identity` instance/lineage and checks the exact applied schema.
It returns an immutable pair of actual instance and lineage IDs. This is not a
new counter, signing key, role, table, permission or source of authority.

The accepted checkpoint implementation rotates the instance on export, on
the source and target of restore, and when revoking a rehearsal target. Native
restore/export uses the existing exclusive `checkpoint.RELEASE_LOCK`; this
reader takes its actual shared counterpart. Thus an old signed file cannot
authorize a database with a different native instance, even when business
content/version happens to match. A valid newly signed release still produces
a different witness and cannot reuse an old expected pair.

`with_current` checks the expected pair, runs a bounded fully encoded local
projection while the existing release barrier remains held, then repeats the
signed/native check and current qualification. It checks qualification again
after transaction exit. Native 5-second lock and 10-second statement timeouts
are installed before the host scope hook can acquire the release barrier.
Connection/verification failures withhold results;
projection programming exceptions are not silently converted to success.
`observe` reads the pair without reserving a model, tool, task or fee.

## Evidence and remaining work

The fresh private PG group uses the real `cj_m1_runtime` role and a temporary
signed release. It tests actual SELECT-only epoch access, tampered signatures,
signed-file/database disagreement, a real blocked exclusive restore writer,
bounded reader refusal while that exclusive barrier is held, changed native
generation against the old expected pair, caller revocation
during projection and lazy-result rejection. Temporary keys and a fixed local
authorization clock are test fixtures; no Hong Kong key or account is used.

This barrier protects native database release changes only. It does not replace
Trip version/content checks, canonical MESSAGE/Travel protection, Memory epoch
and history fences, account/session checks, consumer qualification or a durable
metadata publication protocol. It must never surround a provider/network wait.
A callback's file side effect is not a successful publication: later native
transaction/return/qualification failure must still leave that original
unpublished or query-only. Manual SQL or arbitrary file replacement is not an
accepted restore path. Full fixture isolation/publisher/E/F activation remains
UNRUN until the required native protections are composed and tested together.
