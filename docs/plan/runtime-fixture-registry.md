# #762 fixture reuse registry and reservations

This is B's internal source-control component, not a change to the frozen
`G2C-runtime-adapter.1` request or `G2C-cross-binding-fixture.1` envelope.
It records no fee and dispatches no MESSAGE, model, tool or Trip mutation.
Native preparation, observation, isolation, disclosure scanning and publication
remain separate prerequisites. This component alone does not enable E/F.

`cj_api.runtime_fixture_registry` accepts an existing B-owned 0600 policy file
and existing B-owned 0700 reservation directory. It never creates either.
The consumer host supplies its **original native MESSAGE admission lock**,
current consumer qualification guard and native source guard. The latter must
freshly authenticate the producer/observer and the selected frozen definition,
then return its original `{ref, sha256}`. A JSON declaration or an expected pin
is not an implementation of that source guard. No token is stored here.

## Exact policy fields

The version is `G2C-fixture-use-registry.1`. Every field below is required;
unknown keys, duplicate JSON keys, noncanonical bytes and nonfinite values fail.

| Field | Type / constraint |
| --- | --- |
| `version` | Exact version above |
| `registry_id`, `fixture_id` | Existing adapter identifier, 1–256 UTF-8 bytes, no NUL |
| `fixture_revision` | Positive integer; booleans rejected |
| `producer_binding_sha256` | Original native producer `Binding.key` |
| `consumer_binding_sha256` | Original native consumer `Binding.key` |
| `baseline` | Exact keys `trip_id_sha256`, `trip_version`, `content_sha256`; hashes are 64 lowercase hex, version positive integer |
| `consumer_pins_sha256` | Original consumer `Pins.key` |
| `consumer_registration_ref`, `experiment_ref`, `public_release_ref` | Exact `{ref,sha256}`; `ref=original-<64hex>`, hash 64 lowercase hex |
| `batch_ids`, `candidate_ids` | Nonempty unique lists of at most 100 adapter identifiers |
| `languages` | Nonempty unique subset of `zh`, `en` |
| `valid_from`, `valid_until` | Timezone-aware ISO timestamps, start strictly before end |
| `maximum_uses` | Integer 1–100, matching the currently approved evaluation ceiling; not a new spending allowance |

The constructor verifies that producer and observer have the **same complete
native binding**, while producer and consumer have different owner scopes.
It does not reconstruct a binding from fields supplied by a task.

The registry policy intentionally has **no definition hash**: a definition may
refer to the independently issued registry header without creating a hash
cycle. The native source guard selects the actual definition. Each reservation
subsequently pins its original reference/hash. Publisher integration must also
prove that definition's fixture/revision/baseline and purpose match this policy;
neither the reference syntax nor these controls prove that by themselves.

## Exact reservation input and durable body

Only B constructs the input from its original claimed E request and frozen
consumer registration. It is not a new client fixture-selection field.
Input has exactly these keys:

`binding_sha256`, `pins_sha256`, `batch_id`, `candidate_id`, `task_id`,
`language`, `attempt_id`, `step_id`, `request_sha256`.

Binding/pins match the current original consumer, `task_id=val-owner`, and
batch/candidate/language must already be allowed by the policy. The remaining
IDs use existing adapter identifiers and the request digest is 64 lowercase hex.

The saved body has exactly `version`, `policy_sha256`, `definition_ref`, `use`,
`ordinal`, `reserved_at`. The `use` is the exact input object. `ordinal` is
one-based within that immutable policy. This is a reservation, not an assertion
that a task was sent, observed, settled or passed.

The canonical filename is derived from original consumer scope, ledger,
producer, attempt and step. Session, candidate, registry and policy revision
are excluded from its namespace. Thus a new session or registry cannot create
a second selection for an old original operation. A genuinely new original can
use a newly approved policy; older records remain unchanged.

Reservation is serialized under the host's existing native admission lock.
All records use O_EXCL/NOFOLLOW, 0600, file fsync and directory fsync. A complete
same-original re-query returns the same ordinal and consumes no extra slot.
An incomplete/corrupt/unsafe record stops new reservations; it is not deleted or
repaired into fresh permission. Every saved reservation counts, including one
whose dispatch/result remains FAIL, UNKNOWN or UNRUN. Outcomes never refund it.

Before and after access, guards recheck actual consumer/source authority,
unchanged policy bytes and validity. Definition drift or revocation after a
write withholds the result while retaining the original slot. `read` does not
reserve again; it remains subject to current read qualification and expiry.

## Verification and remaining boundaries

The local unit controls test only these reservation mechanics. Their synthetic
guards and mutex are not native AUTH, source isolation or an experiment result.
The additional `runtime_fixture_registry` PG group uses fresh local JWT keys,
native signed conversation admission and runtime-role MESSAGE transactions.
It observes the competing row waiter in PostgreSQL before releasing the lock,
then checks concurrent same-original reuse, foreign-owner denial and invitation
withdrawal while admission is blocked. The revoked waiter has a spare use slot,
so quota exhaustion cannot explain its denial. Previously saved slots survive.
Its ledger/pins/source-definition fixtures are explicitly synthetic: actual
financial qualification and producer Trip publication remain unimplemented.

Source-body mappings, preparation/cost provenance, actual registry/definition
reference publication, source fences, exhaustive E surfaces and late-write
closure remain required by X01–X12. No resolver may use this module as a cached
ALLOWED witness. No paid E use may start until those boundaries are connected
and independently verified. Existing original-reader formats are unchanged.
