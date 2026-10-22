# TRIP-WIRE@0.1.0-rc.1

Trip additions are based on Memory57336d501e5691302a3d5e9770f07666d1c57d4a;
all accepted573 operations/schemas remain unchanged. Sole formal source is
contracts/api/openapi.json; Python/Swift are official generator output. Public
producer is fixed5fd115fc97e542bc8776a445d8245fd272000e56, including public
proposal read0e2 and guarded operation. AUTH remains fixedf3c8e507. This is a local
candidate, not TRIP@1.0 freeze or Issue20/App/CJ014 acceptance.

| Operation | Path | Result |
|---|---|---|
| actOnTripProposal | POST /v1/trip-actions | original committed accept/reject receipt |
| queryTripAction | GET /v1/trip-action-receipts?action_id=… | original receipt or required null |
| listTrips | GET /v1/trips?limit=…&after=… | current formal records, live C keyset |
| getTrip | GET /v1/trip-details?trip_id=… | formal record or required null |
| getTripProposal | GET /v1/trip-proposals?proposal_id=… | protected immutable display snapshot |

POST application/octet-stream carries exact public Action.raw() UTF8 bytes:
compact five-string JSON array `[action_id,kind,proposal_id,candidate_hash,confirmation_ref]`.
IDs use producer ASCII identifier rules, kind is accept/reject, candidate_hash is
64 lowercase hex. parse_action calls public Action then requires raw equality;
no normalization, caller owner/viewed/approval or alternative input is accepted.
Freeze original bytes/ID; unknown results require original action query, never
replacement ID or inference from latest Trip. No HTTP publish/retire/proof issuer.

Proposal display directly projects public ProposalDetail: exact content/base64,
typed document, original ID/basis/expected version/Unix-second deadline, producer
revalidated stored scoped hash and status. Never hash API presentation JSON or
invent owner scope. Terminal candidates remain readable; elapsed pending is not
silently retired. Read/display does not prove review/confirmation/eligibility.
Pending facts remain pending when accepted; schema checks are not provider proof.

List uses confirmed C byte order of opaque ASCII IDs, explicit limit1..100 bounded
by mandatory host configuration, and full last-ID `after`. next_after is the last
ID for any nonempty page, null for empty. A short final page may need an empty read;
no has-more or cross-page snapshot/completeness guarantee. List/detail read the
same current formal records. Receipt committed_version is then-version for accept,
required null for reject; original receipt never silently becomes latest Trip.

## Composition and private output

create_trip_composed_app requires explicit local strict JWTConfiguration/verification
keys, unique existing CJAccessProvider, trusted resolver and TripWireConfiguration.
Existing create_composed_app also accepts the same Trip configuration/resolver/
validator beside MESSAGE/Memory, sharing the existing AUTH provider. No production
configuration, credential discovery, database default or new authority exists.
Resolver maps approved environment/profile and verified issuer/subject/audience
to fresh connection factory and non-reused server scope; never client scope or
JWT timestamps. Missing configuration fails closed.

confirmation_validator defaults None and stays None. Only trusted server-held
proof that this actor reviewed the exact candidate/hash/content/basis/version and
chose this action may allow a fresh action. A nonempty reference or caller viewed
flag is insufficient; validator must not perform network IO under the transaction
lock. Real CJ014 ingress/App confirmation evidence is not supplied. Synthetic
fixture callbacks prove only the local transaction/consumer path.

Every route exclusively uses Boundary.with_operation(token, callback). Callback
calls only ctx.act/query_action/detail/list_trips/proposal_detail; projection,
generated-model checks, aggregate/private response bounds and complete JSON bytes
finish inside this lifetime. Response publishes only returned bytes, no delayed
serialization. No _repository/_proposal/private metadata, transaction wrapper or
outer authorization implementation. Producer enforces fresh admission, captured
actual scope/configuration, sticky failures, one action and final serialized_return;
expired/cross-thread/nested contexts cannot escape. This is not an atomic distributed
AUTH/revocation guarantee.

No token/URL/query/body/ID/exception string is logged by routes. BASE request_id,
X-Request-ID, bilingual generic errors and no-store remain unchanged. Stored private
content/original action+confirmation references are in registry1.3; retention,
physical cleanup and restore fences are still UNDECIDED/UNIMPLEMENTED. Candidate SQL
is unregistered; this feature does not expand initialization apply or RLS/grants.

## Failures

Missing bearer401; malformed/noncanonical input400; media415; body/private read
size413; propagated known precommit Conflict409. Public producer Denied currently
conflates AUTH denied/unknown, absent confirmation and missing/wrong-scope candidate.
Wire conservatively reports503 TRIP_ACCESS_UNAVAILABLE / access / unknown rather
than guessing a reason or leaking existence. No second AUTH policy classifies it.
Writes retain reconcile_original; reads retry_safe_read. Typed reason distinctions
would require a future producer contract increment.

CommitUnknown, cancellation/interruption, lost ACK, postcommit denial or projection
failure return503 unknown with original action reconciliation and no private receipt.
A rollback of this attempt cannot disprove an earlier same-ID commit. Read-only
withheld results do not imply a write/action. No auto retry or generated ID exists.
Missing receipt is not proof of noncommit. Swift oneOf null fallbacks must have
value == nil; a nonnull container is invalid, not absence.

Use the existing `Configuration.memory` with the official Swift Client; Trip Unix
expiry is integer and needs no new date parser. No Memory consumer defaults changed.

## Checks

```sh
UV_OFFLINE=1 ./scripts/check-trip-wire.sh AUTH_GIT_REPOSITORY TRIP_GIT_REPOSITORY
UV_OFFLINE=1 ./scripts/generate.sh --check
./scripts/check-generated-trip.sh
./scripts/build-trip-loopback-client.sh
```

The scoped fixture suite labels mocked public output separately from actual AUTH
entry rejection. Public projection and generated checks do not prove database or
HTTP readiness. The prepared real runner requires a newly authorized task-private
empty PostgreSQL directory, fixed candidate SQL and synthetic immutable candidates/
server confirmation evidence; never point it at retained/old/shared state. No package
install or prior PR49/59/Memory regression rerun is implied. Independent gates,
real account/provider/App review, two product entrances/reopen, production and full
Issue20 I closure remain distinct and unrun until separately evidenced.

Actual author combination at e40d703 passed nine groups including the official
Swift Client over real HTTP/private PostgreSQL; see tests/evidence/trip-wire/REPORT.md
and loopback-result.json. Both local services stopped. This synthetic confirmation/
account/candidate evidence does not close Issue20's App/CJ014/real-policy requirements.
