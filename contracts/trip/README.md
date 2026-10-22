# CJ-TRIP-INTERNAL@0.1.0-rc.1

Owner CJ015. Candidate only, not TRIP@1.0 publication or a second wire schema.
Fixed base: 23e12f28435ab0ddc685d544670564e3fa79db41. CJ005 owns formal API/schema.
Main/CJ014/CJ017/CJ005 consumer confirmation: PENDING.

`Proposal` in backend/trip/cj_trip/domain.py is the minimal immutable candidate.
IDs, exact canonical UTF-8 content, basis version, expected Trip version (0 = new),
expiry and server storage scope bind one SHA-256 digest. Missing fields fail; no
location/price/time defaults. Canonical JSON rejects duplicate keys and preserves
exact accepted content. Items explicitly retain pending/verified and evidence;
this schema validates shape, not truth. Only trusted candidate ingress can publish.
CJ014 real proposal mapping and eligibility/source validation remain unintegrated.

`Action` binds stable action ID, accept/reject, candidate ID/hash and confirmation
reference. `confirm(scope, action, proposal)` is a synchronous trusted host adapter:
it MUST verify server-held evidence that the same authenticated user reviewed this
exact digest/basis/version/content and explicitly chose this action. Client viewed,
owner, model text and a nonempty reference do not authorize. Default None denies.
No real UI evidence issuer exists in this slice; test callbacks are synthetic only.
Adapters must not do network IO while the scope transaction lock is held.

`Repository` is internal and scope-bound, never exposed as caller-selected storage.
`Boundary` consumes existing AUTH AdmissionChecker ALLOWED/TrustedPrincipal and a
host-owned resolver; resolver configuration is absent by default and denies.
Scope must use stable environment/issuer/subject mapping, never token timestamps,
email, body owner or unverified claims. Entry/transaction/commit/return checks do not
prove atomic concurrent revocation or live session revocation (AUTH has no fence).
Consumer confirmation of this seam remains PENDING, no new permission source/RLS.

Pending candidates may become accepted/rejected/expired/superseded only. Generation
cancellation is not rejection. Expiry is also checked against database clock at
accept/reject and immediately before commit. Retirement persists expired state;
time alone makes acceptance ineligible even before retirement runs. Supersession
requires an existing pending candidate for the same scoped Trip.

The scope row serializes all mutations (including simultaneous new Trip inserts).
Accept writes exact content, increments version, transitions state, and writes the
original action receipt in one transaction. Reject writes no Trip. Both check the
reviewed expected Trip version. Same action ID + exact input returns the original
receipt, even if Trip later advances; different input conflicts (across kinds too).
Read/query use the same scoped tables. List uses keyset ID ordering with bounded
pages; no snapshot pagination promise. A receipt records the then-committed version,
not a guess from latest Trip. Missing receipt is not proof the action never ran if
an original request is still in flight. Commit/response loss means query original
ID; do not mint a new ID or treat denied post-commit response as rollback.

Retention: no receipt/candidate deletion or expiry cleanup is implemented. Dedupe
holds while records are retained; no infinite retention promise. Contains private
itinerary content and identity partition keys; no tokens stored. CJ024/CJ005 must
register cleanup/retention and deployment privileges before real activation. SQL is
an isolated empty-DB candidate, not a formal migration, RLS or production grant.

Executable positive/negative examples: backend/trip/tests/test_trip.py. They cover
synthetic trusted confirmation, tampered candidate/hash, wrong scope, missing
confirmation, stale version, duplicates, terminal states, races, rollback, restart
and original receipt after commit ACK loss. They do not establish App review,
CJ014 real candidate quality, real account auth, provider or production acceptance.
