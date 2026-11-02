# RUN-BACKGROUND@1 — original C job, independent Run and unique Meter

Additive B interface for #23/#27. No MESSAGE receipt, conversation generation or
terminal MESSAGE RUN is fabricated/reused. This candidate's actual registration
and acceptance require its main-chain migration/registry and exact-head checks;
the isolated SQL fixture is not deployment or main acceptance.

## Explicit trusted host construction

`BackgroundJobs(database,boundary,collection,max_payload_bytes,clock)` uses the
canonical local database, ACCOUNT-ADMISSION@2 MESSAGE Boundary, explicit registered
local quota profile and C's **filtered V2** processing/publication adapter.
Construct `FilteredCollectionAdapter(actual_collection)` explicitly: it binds only
processing_policy_v2, publication_policy_v2, query_publication_v2_in_context and
transition_original_in_context, plus NoEligibleSource. There is no Data1 fallback.

`LocalBackgroundHost(jobs,auth_dir)` is passed as
`run_worker.run_once(...,background_jobs=host)`. Existing default None remains
closed. MESSAGE work runs normally; pending background jobs also run when no
MESSAGE delivery remains. The host uses the same explicit synthetic-local signed
identity/invitation source. Only FakeProvider's registered family is enabled.
No key/account/provider/cloud resource is created by activating this constructor.

## Original data and public methods

`JobRequest(job_id,attempt_id,query,travel,prepared_input)` contains data only:

- C original job/attempt IDs: exact Unicode, at most256 characters/1024 UTF8 bytes,
  nonblank, no NUL or invalid surrogate; no trim/normalize.
- query: unchanged SourceQuery eight fields. travel: None for long-term, or actual
  B Selection(id,expected_version) for current publication; neither grants consent.
- prepared_input: exact C prepared UTF8 `{system,messages}`. The actual source
  policy re-renders and compares its original bytes. Historical messages remain
  user-role data, never system/assistant/tool roles.

`prepare(token,request)` verifies current own authority/actual C inflight job and
source, records a new server Run UUID and one immutable registered command.
Same original data/config returns its existing job; changed bytes conflict.
Preparation does not reserve, claim, invoke, settle or publish.

`query_original(token,job_id,attempt_id)` is fresh own-account metadata only.
`read_original(database,boundary,token,job_id,attempt_id)` is the separate read
without a current quota/model/C processing dependency. Withdrawal does not renew
source authority, and status/IDs alone never authorize dispatch.

`process_one`/host run_once acquire the one physical worker lease, perform the
one-way queued→running claim and use the single existing MeteredExitCore/Meter.
Only registration memory.history-extract.1/kind memory/reserve1 is available.
The full operation envelope binds the original server Run, owner digest, C IDs,
source/Travel reference and exact prepared bytes. Its Meter input SHA is distinct
from C's prepared-input SHA. No second accounting engine/ledger is initialized.

`cancel` stops C's original metadata then B's original job and existing Meter run.
Unclaimed reserves may release; claimed UNKNOWN remains UNKNOWN, never zero cost.
NoEligibleSource cancels through this metadata path without inventing empty
provider output or claiming an old unknown invocation was uncharged.

`reconcile` reads C's actual typed MEMORY-PUBLICATION-result@2 outside a source
holder. Only matching original job/attempt/prepared/output hashes can confirm B's
publication. Null is absence observation, never authority to retry a provider or
publication. Unknown/running/publishing intents cannot return to queued.

## Source, lifetime, budgets and publication

Every local reserve/claim/settlement re-enters the real C processing policy with
the protected SourceSnapshot. Current work uses MESSAGE-SOURCE@2 with the original
genuine Travel lease. These short MESSAGE→Travel→MEMORY leases perform only local
work; provider/network waits occur after release. Physical worker ownership and
the original job-row first-outflow fence prevent a second owner/call.

The same code-owned Meter enforces account quota, one memory step, zero tool
adapters, output and total time. Mutable source/input preparation and final
publication are included in the original deadline. No old quota period is silently
replaced by a current one; missing original configuration is UNKNOWN.

Model EOF and acknowledged original settlement precede publication intent. C's
public publication policy commits its checkpoint/canonical items/cursor/typed
receipt together. B records only output/receipt hashes **after** successful C and
outer MESSAGE exits. Unknown commit reads the original receipt; it never resends
the provider or writes a synthetic success. Raw rejected model output is not a
second B content store.

Account retirement immediately denies ordinary access and later writes; the
cleanup role observes the actual background physical lease as well as MESSAGE
workers. Busy workers/unresolved original costs block domain erasure. The new
job's input/command/config are execution/reconciliation evidence, not90-day logs;
only user/account deletion may erase content, with minimal hashes/fences retained
for original reconciliation. An erased input cannot rehydrate or execute.

The SOURCE@2 lease-check P2 is fixed by retaining the canonical captured admission
guard in the context; lease.check now performs immediate fresh admission as well
as callback lifetime/thread checks. Old frozen source fields remain unchanged.

## Executable examples

background_jobs_pg.py: real signed source/C policy, one new Fake/Meter invocation,
typed publication, no fake MESSAGE/terminal Run reuse, budget0-outflow denial,
UNKNOWN retention/cancel after withdrawal and fresh-process original read.
background_inflight_pg.py: actual blocked background worker/lease, confirmation
and original device continuation do not erase live records, late output refused.
background_current_pg.py: actual send.2 and Travel→joint lease→canonical current
Memory; stale selection prevents the first model/claim and cannot redispatch.
background_limits_pg.py: actual step1/tools0, output overrun, in-flight clock and
post-source-preparation deadline; no canonical publication beyond any bound.

These fixed-candidate/private-PG/Fake results do not prove real model quality,
provider charging/Auth/cloud/backup/device behavior (#32/#29/#30).
