# CJ015 candidate display / CJ005 consumption seam

Additive internal Python candidate on parent63bcf9c; formal wire stays CJ005-owned.
Consumer acceptance PENDING; this document supplies the exact shape for Main to route.

`Boundary.proposal_detail(token, proposal_id) -> ProposalDetail`:
- `proposal`: frozen Proposal with proposal_id, trip_id, expected_version (0=new),
  basis_version, expires_at (Unix seconds), content (exact canonical UTF8 bytes).
- `candidate_hash`: actual stored digest revalidated against all original Proposal
  fields plus the internal server scope. Not a hash of the API's reserialized body.
- `status`: stored pending/accepted/rejected/expired/superseded.

The caller cannot choose scope/owner. Existing fresh AUTH admission, resolver,
transaction/commit/private-return guards apply. Missing and wrong-scope candidates
both raise Denied('candidate unavailable'). No private result escapes return denial.
Terminal candidates remain readable to their admitted owner. A pending candidate may
already have elapsed expires_at: reads DO NOT run retirement or change its status;
API/UI must show that deadline and cannot infer acceptance eligibility from pending.
Displayed data may become stale; act still checks exact hash/state/version/expiry.
GET is not proof of review, user confirmation, or permission to accept. confirm stays
absent/deny by default; no second evidence table, issuer, or publish/retire route.

`Boundary.list_trips(token, after='', limit=20) -> list[Trip]`:
- limit must be an integer 1..100 (bool invalid). after must be a string; empty means
  start, otherwise the existing identifier syntax applies. Nonexistent after IDs
  are valid lexical boundaries, not resource lookups.
- PostgreSQL C collation for both `trip_id > after` and ascending ORDER BY: stable
  byte order independent of database locale, matching the ASCII identifier alphabet.
- Internal after is the FULL previous last trip_id, an opaque identity whose interior
  must not be parsed/incremented as a counter or timestamp. No encoded public cursor
  is supplied here. If wire requires one, CJ005 owns scope-bound encode/decode policy.
- At most limit rows; empty or short page is exhausted at this read instant. Exactly
  limit rows DOES NOT prove more rows. Do not invent has_more=true from a full page.
  A client can request the following page using the last returned ID and stop on empty.
- No cross-page snapshot promise: concurrent inserts before cursor can be missed and
  later inserts can appear. Resource scope is rechecked on every request. List and
  detail use the same current formal records; no historical snapshot is fabricated.

No wire/schema/AUTH/confirmation ownership transferred. Main should route this fixed
contract and positive/negative tests to CJ005 before formal API consumer integration.
