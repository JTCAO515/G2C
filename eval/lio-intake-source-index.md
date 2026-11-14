# Synthetic intake source-index vectors

Refs #936 and #922. [Eight vectors](lio_intake_source_index_cases.v1.json) cover
ZH/EN × zero/two injected Memory items × one/two traveler originals. These are
new synthetic inputs, not a reconstruction or replay of an external tester's
request or missing model output. All results and costs are UNRUN; no calls ran.

```text
user: Stored memory data … {items: [] or two synthetic preferences}
user: traveler original 0 — Hangzhou / four days
user: traveler original 1 — start tomorrow (two-turn cases only)
```

The separate user-role Memory block has no traveler source index, even when
its item list is empty. Expected city/duration and planning-request provenance
stay at original 0; a supplied tomorrow is anchored to original 1's persisted
question day. Every returned quote must match that original's actual span. An
English city query stays an original English span; a Chinese display name is
not substituted as the source quote. Dates/party remain optional and are never
filled from these Memory preferences.

The vectors contain logical fixture Memory payloads. They do not initialize a
namespace, save Memory, grant collection/read access or prescribe a hidden
client-side injection into the DUT. A live run needs an independently qualified
server setup and must verify the actual injected count in its original input
and provider-wire artifacts. If the required setup/observation is unavailable,
the case stays UNRUN rather than treating the declared payload as evidence.

Run only after B qualifies the actual source/image, consumer, existing identity
and budget, original collector and fresh diagnostic window. Register new IDs
and use fresh conversations. The fixture registration is intake9 with the flat
intake8 output shape; it is not an exploration4 actor or a qualification for
other modes. A static capability reply cannot prove the model path ran.

Record every planned case, original MID/RUN/operation/attempt, actual output,
same-attempt input/wire/Meter/Fee and conservative/token-estimate/paid cost.
On the first FAIL/UNKNOWN, stop new dispatch; retain the original and the rest
as UNRUN. Do not repair truncated JSON, retry the original action, or present a
regenerated reply as its missing original. This eight-case diagnostic stays
separate from the 60-persona/840-factor baseline and all release cohorts.
