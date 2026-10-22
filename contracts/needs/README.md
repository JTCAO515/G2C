# CJ NEEDS internal candidate 0.1.0-candidate.1

Status: implementable local candidate, **not NEEDS@1.0 frozen**, not HTTP/OpenAPI,
not App acceptance. CJ013 owns this directory and `backend/needs/**`. Based on
`8f2ff45519d1d09f178f1fa766b6829d81bda77a`. CJ005/CJ035 confirmation and wire
integration remain UNRUN. Original scope: CJ013 / GitHub Issue 14.

## Authoritative interface and trust

Python validator: `backend/needs/cj_needs/domain.py`; public host entry:
`cj_needs.Boundary(checker, resolve).with_operation(token, callback)`.
`checker` consumes existing `cj_auth.admission.AdmissionChecker` and
`CJ-AUTH-SERVER@0.1.0-rc.1` at the fixed base. A trusted host resolver maps the
verified `TrustedPrincipal` and deployment to `(fresh_connection_factory, opaque_scope)`.
No scope, account owner, membership flags or source authority are accepted from a
command. Provisioning scopes is host work, not an operation in this API. Direct
Repository access is server-private and must never be mapped to caller arguments.
The candidate SQL is an empty-database test schema, not production grants/RLS.

The callback is synchronous and returns fully encoded `bytes`. AUTH and captured
binding are rechecked before SQL, before commit, after commit and after encoding.
Operation handles expire at callback exit and cannot cross threads or nest into
another operation's lifetime. One write per callback. This follows the existing
TRIP response-lifetime pattern without depending on TRIP private storage/classes.

| Callback method | Input | Return |
|---|---|---|
| `act(Command(original_utf8))` | Strict bytes validated below | `Receipt(action_id, needs_id, version, operation='manual_patch')` |
| `detail(needs_id)` | Local opaque identifier | `Snapshot(needs_id, version, content: bytes, source_kind='user_provided')` or `None` |
| `revision(needs_id, version)` | Exact historical positive version | `Revision` with immutable original input bytes, full snapshot bytes, action ID and `source_kind='user_provided'`, or `None` |
| `query_action(action_id)` | Original ID; never a replacement | Original receipt or `None` |

`None` is an authorized current lookup with no committed row. It is **not** a
rollback/absence proof for an in-flight request, authorization to replace the ID,
or proof that a lost response failed. AUTH denial/unknown withholds content.
`OperationWithheld` includes only original `action_id`, `commit_possible` and
`recovery`; all cancellation/commit-ACK uncertainty keeps the original command.
Read errors are unavailable, never converted to empty results. No automatic retry.

## Command grammar

Exactly these top-level keys; duplicate keys, non-UTF8, unknown keys, nonfinite
numbers and extra source fields are rejected. Maximum original bytes: 128 KiB.

```json
{
  "action_id": "manual-1",
  "needs_id": "visit-1",
  "expected_version": 0,
  "source": {"kind": "manual", "text": "We are three; dates are undecided. 日期未定。"},
  "changes": {"party_size": {"state": "known", "value": 3}}
}
```

`expected_version=0` creates; later corrections require the exact current
version. An account-local `needs_id` is a **current planning record**, not a
formal Trip ID. No Trip, profile or Memory rows are written. Sources are manual
explicit user entries/corrections only; no model extraction, MESSAGE/RUN IDs,
confirmation boolean, order-verification flag or external reference is accepted.
A user claim of a booking remains user-provided, never verified with a supplier.

`changes` is a nonempty patch of the fields below. An omitted top-level field
keeps its previous value (or remains absent on creation). Present nested objects
and lists replace that whole field. No automatic list merge or monetary arithmetic.
An explicit empty list/map clears that collection, with the prior version retained.
Removing a companion still referenced by retained items/conditions fails atomically;
remove or correct those references in the same command.

Each **observation** is exactly one of:

- `{"state":"missing"}`: explicitly recorded as not supplied.
- `{"state":"unknown"}`: known to be undetermined.
- `{"state":"uncertain","note":"user's uncertainty"}`: unresolved text, no numeric/date substitute.
- `{"state":"known","value":...}`: explicit user value, not externally verified fact.

| Field | Known observation value / structure |
|---|---|
| `party_size` | Positive integer; never bool or inferred count from companions |
| `destination_timezone`, `overseas_timezone` | Explicit IANA timezone string |
| `budget_currency` | Explicit three uppercase letters; format validation only, no currency/exchange service |
| `budget_total`, `budget_per_person`, `budget_paid` | Nonnegative decimal **string**, exact representation retained; no implicit zeros, conversion or division |
| `budget_basis` | `total` or `per_person`; unknown supported separately |
| `budget_includes` | Nonempty list of explicit user strings, e.g. `includes hotels`, `excludes international airfare`; no inferred coverage |
| `pace` | Explicit user text |
| `overseas_departure`, `arrival`, `departure` | Event object described below |
| `companions` | Map of local ID to user label; empty allowed; no global account references |
| `fixed_items` | List of fixed-item objects below; empty allowed |
| `temporary_conditions` | List of current-trip condition objects below; empty allowed |

Event object: exactly `date`, `time`, `timezone`, `place`, each an observation.
Known values are `YYYY-MM-DD`, local `HH:MM` or `HH:MM:SS`, IANA zone, and user text.
Partial events use missing/unknown observations. Date/time **never convert via the
device timezone**. DST ambiguity or nonexistent wall times are not resolved into
instants: the stored values express what the user said. A solver must obtain
missing/ambiguous instant information if that particular calculation needs it.
Independent destination/overseas zones are not silently copied into event zones.
These arrival/departure fields capture user-reported real travel constraints;
they are not schedule search results or externally verified movement facts.

Fixed item has exactly:

```json
{
  "item_id": "hotel-1", "kind": "hotel", "description": "User says hotel is booked",
  "applies_to": ["self", "companion:mother"],
  "locked": {"state":"known","value":true},
  "booking_status": {"state":"known","value":"booked"},
  "start": {"date":{"state":"unknown"},"time":{"state":"unknown"},"timezone":{"state":"unknown"},"place":{"state":"unknown"}},
  "end": {"date":{"state":"unknown"},"time":{"state":"unknown"},"timezone":{"state":"unknown"},"place":{"state":"unknown"}}
}
```

`kind`: hotel / transport / appointment / intent. `booking_status`: booked /
intended / cancelled, always a **user claim**. `locked` is a boolean observation,
not default false. There is no automated writer allowed to relax this intent.
Explicit user corrections may change it with CAS and retained history.
`applies_to` is a nonempty unique list of `self`, `party` or `companion:<local-id>`.
A companion must exist in this record's resultant map, never another record/account.
Conditions have exactly `condition_id`, `applies_to`, `description`. They apply to
this planning record only; no long-term lifetime or promotion flag exists.

Identifiers: ASCII alphanumeric first, then alphanumeric/`_.:-`, at most 96 chars.
Text: nonempty, <=4096 Unicode scalars. Collections <=100 items, subjects/coverage
lists <=32, party size <=100000, money <=15 integer/6 fractional digits: defensive
encoding bounds, **not** approved travel/solver/city limits. Result snapshot <=128 KiB.

## Original action and correction semantics

Uniqueness: `(trusted account scope, 'manual_patch', action_id)`. Same original
bytes return the original receipt even after later corrections. Different bytes
(including whitespace, escaping or translated text) conflict. UTF8 original bytes,
source text, complete revision, server record time and receipt persist in one
transaction. CAS locks the account scope, covering concurrent first inserts and
updates; two commands based on one version yield one winner. No content-only hash
substitutes for original-byte equality. This candidate retains all revisions and
receipts until a future authorized cleanup integration; no TTL/deletion promise.

Read revisions 1..current version to inspect which fields each original patch
changed and its source text. A snapshot's source label means **all inputs were
user-provided**; it does not claim its latest source text supplied every field.
No per-field source is invented when a partial correction retains older fields.

`InvalidInput`: invalid grammar/reference; `Conflict`: stale version or differing
original bytes; `Denied`: AUTH/binding/scope unavailable; `OperationWithheld`:
result withheld, possibly committed; database/timeout errors remain failures.
CJ005 must map these into its existing BASE contract; no parallel HTTP errors here.

## Consumer request and outstanding integration

CJ005: confirm trusted principal/environment resolver and opaque account scope;
wire the four methods through the existing API, response-lifetime gate and BASE
errors; retain original action bytes for UNKNOWN recovery. No routes generated here.
CJ035: pin this candidate's version and independently state required fields for
its chosen calculation. Missing budget must not block saving known arrival data;
a complete snapshot alone is not feasible/validated/solved. All locked/uncertain
and companion applicability values must remain visible to the consumer.
MESSAGE/RUN producers: provide an owner-confirmed **public** identity, ownership,
source-version and current-context contract before a source mode is added. Current
mode rejects those references; no fabricated source or permissive allow callback.
Cleanup owner: production integration must register scope-bound revision/original
input data, retention/deletion and restore behavior before product release.

Owner confirmations: **PENDING**. Real App, model extraction and Issue I dependencies:
**UNRUN**. Candidate is not a NEEDS@1.0 freeze or an Issue closure claim.
