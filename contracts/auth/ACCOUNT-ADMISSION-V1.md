# ACCOUNT-ADMISSION@1 — local business-host composition

Public factory: `cj_api.local_worker_context.account_checker_for(auth_dir,database)`.
`auth_dir` is the existing explicit local signed identity/invitation source;
`database` is the host's canonical `LocalDatabase`. No client scope, separate
cleanup capability/signing key, new account or external authority is needed.

The result is the canonical `AdmissionChecker` with the original verified JWT,
email/member/invitation facts and a **fresh** `cj_account_fence` lookup for that
same verified principal. It uses only a subject-bound SELECT through the existing
approved `cj_local_cleanup` role. Committed retirement produces DENIED before
physical domain hooks run. Storage/role/schema/identity uncertainty produces
UNKNOWN, never presumed ALLOWED or device-deletion permission.

C installs this checker in its own history/collection/business boundary and
continues the existing entry, callback, precommit and final publication checks.
No new scope mapping, token issuer or mutable current-user global is introduced.
The public lower seam `cj_api.local_account_admission.retired_for(database)`
returns the same principal→Fact lookup; it may be composed explicitly as
`AccountRevocationAccess(base_access,lookup)` for another accepted host factory.
`Runtime.retired(principal)` delegates to this seam and remains public.

The old `checker_for(auth_dir)` retains its original invitation-only semantics.
It is not proof of current account membership after retirement. Its additive
`account_retired=lookup` keyword performs the same explicit composition. Local
system cleanup recovery remains a separate original-operation authority and must
not regain business access by using that old identity-only factory.

Positive: a current signed own principal with actual current facts is ALLOWED;
after its committed fence, the same token/checker is DENIED even if a live worker
prevents all physical erasure. An unrelated current account remains ALLOWED.
Negative: wrong/expired identity, missing role/schema, failed fence lookup and
unknown base facts never become ALLOWED. Capability tokens are not business JWTs.

Only C edits its own host consumers. Local signed/private-PG evidence is distinct
from real account/Auth/cloud/device acceptance in #32/#29.
