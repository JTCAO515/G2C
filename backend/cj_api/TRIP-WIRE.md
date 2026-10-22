# TRIP wire preparation — not route-ready

Parent is completed Memory57336d501e5691302a3d5e9770f07666d1c57d4a. This increment
adds only official OpenAPI output components, public value projections, explicit
local AUTH factory and fixed-source preparation checks for producer
0e2c3241825d81b89cc7bdb2f2c6daa967038068. No TRIP operation/path is yet activated
or frozen. Original Issue20 was read from GitHub API; App confirmation/CJ014 real
proposal integration remain requirements, not optional follow-up.

Remaining blocker sent through Main: public Boundary methods return domain values
before final JSON encoding/size checks and resolver is not rechecked after entry.
Producer must supply a public guarded projection lifetime. Candidate snapshot and
C-collation/list continuation are now confirmed at fixed0e2c324;
CJ005 will consume that fixed public interface rather than read internal tables or
wrap repository transactions. Current source is preparatory, not wire-ready.

Output components in the sole contracts/api/openapi.json:

- TripActionReceipt: original action/kind/proposal/hash/trip and required nullable
  committed_version. Accept requires positive then-version, reject requires null.
- TripRecord: exact canonical UTF8 bytes as base64 plus typed title/items with
  pending/verified/evidence. Shape checks do not certify factual accuracy.
- Original action query and Trip detail use required explicit null for not observed;
  never infer noncommit or create a replacement action ID. List uses confirmed C
  byte order and full opaque last Trip ID; next_after is the last ID on every nonempty
  page and null only on an empty page. It is not snapshot/has-more.

Action body proposal sent to Main: exact public Action.raw canonical five-string
UTF8 JSON array. parse_action checks five strings, producer Action rules and exact
raw equality; no caller viewed/owner/approval fields. This is not yet a frozen
public request body. No action hash is guessed from caller scope or current Trip.

trip_projection.py uses only public domain values/functions and official generated
output models, not _repo/_proposal or an alternate business implementation.
trip_composition.py constructs the existing public Boundary with strict fixed
PyJWTVerifier and the unique existing CJAccessProvider, trusted host resolver and
optional server confirmation validator. Missing validator stays missing (denies
fresh actions). This factory creates no app/service/storage or implicit scope,
credential, review evidence, policy or real provider ingress.

TripProposalSnapshot/Response now project only public ProposalDetail: exact original
proposal fields/content plus producer-validated candidate_hash and stored status.
Missing and wrong-scope candidate reads both deny; no fabricated null candidate.
Elapsed pending stays pending and readable; deadline is shown as original Unix
seconds, never inferred eligibility/retirement. Reading is not review/confirmation
proof and creates no proof issuer or new evidence table.

trip_pins.json binds all four current producer runtime files and the unchanged
AUTHf3 source. prepare-trip-deps.py exports only those fixed Git blobs to ignored
clone-local dependencies; no moving-source imports or package install. Future
public interface changes require an explicit new fixed pin before consumption.

Author preparation checks: three public Python projection/canonical checks PASS;
Swift generated component decode checks PASS, including original/reject-null,
required/missing/unknown invalid fallback, canonical Action bytes and exact content/
pending verification state. No listener/DB/runtime API or independent gate proof.
All accepted57336 Memory/BASE/MESSAGE schemas and operations compared unchanged.
No Memory domain/CJShell/Trip domain/SQL/RLS/grant or initialization-apply change.

Public-read increment: fixed0e2c324 contracts/trip/PROPOSAL-READ.md consumed;
one focused Python proposal-projection test PASS for all five states, original
digest/content/deadline and malformed status/hash; official Swift regeneration and
updated actual generated-component consumer PASS. No database or HTTP test run.
Prior three source preparation checks remain their original evidence, not rerun.
Registry1.3.0 adds only the four TRIP candidate tables, private content/actions and
explicit unimplemented retention/cleanup/restore boundaries; schema apply remains
unregistered and unexecuted. Producer's authored PG evidence is not our runtime
or independent gate result.
