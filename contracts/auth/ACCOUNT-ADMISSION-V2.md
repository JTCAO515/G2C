# ACCOUNT-ADMISSION@2 — runtime-only retirement admission

Public factory:
`cj_api.local_account_admission_v2.account_checker_for(auth_dir,database)`.
This additive version supersedes the unaccepted cleanup-role candidate @1 at
5706c2ad. Its original frozen document/history remain; C explicitly declined
that candidate before consumption. No V1 cleanup-role business factory is shipped
as a compatibility fallback. No deployed/accepted consumer is removed.

`auth_dir` is the existing explicit local signed identity/invitation source;
`database` is the canonical `LocalDatabase`. The result is the canonical
AdmissionChecker, preserving the original identity/email/invitation facts and
freshly checking the same verified principal's committed retirement fence.

The lookup uses **only** `LocalDatabase.connect(scope_for(principal.issuer,
principal.subject))`, role `cj_m1_runtime`, and M35's minimal SELECT through
`cj_account_scope_current`. It never creates a connection as cj_local_cleanup,
reads a cleanup capability/signing key, issues a token or accepts a caller scope.
No extra permission/migration is needed. Missing schema/role, failed query,
uncertain facts and expired/changed identity never become ALLOWED.

`retired_for(database)` is the public principal→Fact callback from this module
for explicit `AccountRevocationAccess(base_access,lookup)` composition. Local
cleanup Runtime.retired delegates to the same runtime-only lookup. C installs
this version in its own history/collection/business boundaries, including the
existing callback/precommit/final-publication rechecks. C performs no SQL on B
tables and never takes the dedicated deletion role for background processing.

Committed retirement returns DENIED immediately, before physical hooks execute.
An unrelated current signed account remains ALLOWED. Runtime query uncertainty
returns canonical UNKNOWN. The old checker_for(auth_dir) remains invitation-only;
it is not evidence of post-retirement business admission. Explicit original-op
system recovery remains separate from ordinary business membership.

Actual positive/negative examples are account_gateway_pg.py and
account_inflight_pg.py: signed current owner, unrelated owner, lookup-failure
UNKNOWN, and a fence committed while the real original worker still prevents all
domain erasure. Local runtime/private PG is not real Auth/cloud/device evidence.
