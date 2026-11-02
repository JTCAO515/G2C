# MESSAGE-SOURCE@2 — joint current Travel/history lease

Additive B backend seam for #403/#23; SOURCE-V1.md and all V1 fields/semantics
remain unchanged. This is not an App deletion API or a background dispatch grant.

Inside the canonical `Boundary.with_history_context(token, callback)`, call:

```python
context.with_enabled_source_and_travel(query, policy, selection, project)
```

- `query` is the unchanged SourceQuery: conversation_id, generation, epoch,
  after, through, source_version, withdrawal_epoch, mode. Epoch zero is valid.
- `policy` is C's real principal/scope-bound SourcePolicy.hold implementation.
  Collection stays default off; versions/intervals must match its durable consent.
- `selection` is B's Travel Selection(id,expected_version), a comparison value.
  It is checked against that principal's current active Travel row.
- `project(source_snapshot, travel_lease)` is a synchronous callback returning
  fully materialized bytes, at most 524288. SourceSnapshot is unchanged. The
  genuine CurrentTravelLease exposes `context` (the checked Selection) and
  `check()`, with the existing same-thread, active-lifetime and fresh-admission
  checks. Neither object is a future authorization token.

The one canonical MESSAGE transaction takes its scope lock, then Travel SHARE,
then enters C's policy/MEMORY transaction: **MESSAGE → TRAVEL → MEMORY**.
No second MESSAGE connection is opened for Travel. The callback runs while all
three locks remain held; Memory policy exit and fresh authority checks finish
before locks release and bytes publish. The lease becomes unusable on exit.
Principal and scope come from the protected context, never arguments in a body.
Current hosts use ACCOUNT-ADMISSION@2 so retirement is checked independently of
physical cleanup progress.

C owns its policy and domain writes. A processing policy may additionally bind
its original job/attempt/state/input digest within that same held MEMORY scope;
B does not read C's private transaction/SQL. Do not call another history boundary,
the old public hold_current, or a C method that reacquires MESSAGE/MEMORY from
inside this callback. Prepare detached data outside, then compare and authorize
it within this fresh lease. Re-enter the seam with original references at each
later dispatch/candidate/publication phase; no lease spans a provider/network wait.

Long-term collection without a current Travel selection continues using V1.
Manual-save Travel authority remains its existing separate entry. V2 cannot turn
manual data into history consent, enable a service conversation, create a Trip,
dispatch a provider, claim/cancel a RUN, settle usage, or promote a candidate.
The separate background-job/Meter bridge must supply those operations.

Executable positive/negative example: `backend/cj_api/tests/source_travel_pg.py`.
It uses real signed users, original committed messages, the actual Travel action
API and C's durable consent/policy. Separate runtime connections verify simultaneous
MSG/Travel/Memory writer exclusion. It covers default off, foreign Travel,
changed Travel version, withdrawn source, expired callback lifetime and late
admission loss withholding already materialized bytes. No permit/receipt is
fabricated and no model/job/Meter completion is claimed. Existing message_source
and memory_history PG suites remain V1 compatibility controls.
