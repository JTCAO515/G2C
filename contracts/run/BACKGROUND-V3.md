# RUN-BACKGROUND@3 — accepted Trip decision consumer

Append-only B interface for #403/#411/#27. BG2 and Pub2 retain their original
meaning. This is an internal local worker interface; App account/device HTTP
interfaces remain CLEANUP-API@1 and CLEANUP-DEVICE@3.

## Explicit construction and original fields

Use `BackgroundJobsV3(database=...,boundary=...,collection=DecisionCollectionAdapter(actual_C_collection),max_payload_bytes=...,clock=...)`
and pass `LocalBackgroundHost(jobs,auth_dir)` to the original
`run_worker.run_once(...,background_jobs=host)`. The default remains disabled.
The same worker, FakeProvider family, Meter and accounting ledger are used.
The organizer has runtime credentials only, never cleanup credentials.

The C adapter must explicitly declare `consumer_version="RUN-BACKGROUND@3"` and
`publication_version="MEMORY-PUBLICATION-result@3"`. Both policy factories receive
required `consumer_version="RUN-BACKGROUND@3"`; the publication factory also
receives the original Meter's `before_commit` check. These version labels select
compatibility, and confer no source/account/Trip/Memory authority.

`JobRequestV3(job_id,attempt_id,query,travel,prepared_input,decision_source_sha256)`:

- IDs retain BG2's exact Unicode and byte bounds; no normalization.
- `query` is the C command's `reader_query`, including incremental reader mode
  for a conversation-end job. C independently checks its genuine end signal.
- `travel` must be `None`. C holds the actual accepted Trip decision authority;
  a B Travel selection cannot substitute for that holder.
- `prepared_input` is C's exact filtered UTF8 `{system,messages}` with one user
  data message. Its inner version is `MEMORY-EXTRACT-DATA@3`.
- `decision_source_sha256` is exactly the inner Data3 digest, 64 lowercase hex
  characters. It is comparison data; C proves the original accepted decision.

`prepare`, `process_one`, `run_once`, `cancel`, `reconcile`, `query_original`
retain BG2's original-action lifecycle. `read_original_v3(database,boundary,token,job_id,attempt_id)`
reads own metadata without a current quota, provider or C processing policy.
Withdrawn source authority never becomes permission to dispatch again.

The operation envelope and summary have `version="RUN-BACKGROUND@3"`,
`registration_id="memory.accepted-decision.1"` and `decision_source_sha256`, in
addition to BG2's original IDs/bindings/hashes. Preparation creates no reserve,
claim, provider invocation, settlement or canonical Memory.

## Publication, limits and original recovery

C's required `MEMORY-PUBLICATION-result@3` has exactly eight fields:
`version`, `job_id`, `attempt_id`, `enqueue_input_sha256`,
`prepared_input_sha256`, `model_output_sha256`, `receipts`,
`decision_source_sha256`. B checks the version and original IDs/prepared/output/
decision digests; C's public original query independently proves its enqueue and
canonical receipts. A Pub2, duplicate field or changed digest cannot complete BG3.

Reserve/claim/settle/final publication re-enter the genuine short
MESSAGE → accepted Trip → Memory holders. Provider waits occur outside them.
C's final `before_commit` runs after its final source render and admission checks.
The existing one-step model producer exposes zero tool adapters; output/account
quota/total elapsed time remain enforced by the original Meter. A profile's
numeric `max_tools=1` is not a zero tool quota.

Only C's committed matching Pub3 can confirm completion. A lost ACK or null
observation never authorizes a new invocation/publication. UNKNOWN financial
outcomes stay UNKNOWN, including after cancellation or withdrawal. Cross-chat
canonical reuse is C's decision; B retains each original run and accounting claim.

## Storage, compatibility, cleanup and rollback

M43 appends immutable `protocol` and `decision_source_sha256` headers to the
existing `cj_run_background_job`. Existing rows become BG2 with null decision
digest; no bytes or usage commands are reinterpreted. The restrictive runtime
policy defaults to BG2 when no selector is set, so old BG2 binaries cannot pick up
BG3. Each new store sets its explicit transaction-local protocol; original owner,
active RUN and account RLS remain mandatory. Different versions cannot reuse the
same original job/attempt primary key. No new storage object is registered.

Runtime gains only INSERT on the two headers, no UPDATE/DELETE/TRUNCATE,
cleanup-role membership, BYPASSRLS or SECURITY DEFINER. An invoker trigger protects
both headers. The original dedicated cleanup role observes both protocols and
the same physical worker namespace; active workers and unresolved original usage
block erasure. Retirement refuses sensitive reads/writes and late publication;
the original restricted HTTP progress/device bridge continues to work.

Prepared content is retained until user/account deletion. Immutable commands,
headers and unknown settlement are reconciliation evidence, never 90-day logs.
The existing account-domain hook deletes these rows only after its original
intent, fence and usage prerequisites. Runtime never receives cleanup permission.
M43 down preserves inherited BG2 rows byte-for-byte and refuses any BG3 row, even
terminal/cancelled evidence. Empty up/full down/up is supported. After BG3 use,
disable its host and retain M43; do not discard evidence to force a downgrade.

## Executable positive and negative examples

`backend/cj_api/tests/background_v3_pg.py` and the isolated
`backend/run/tests/probe_background_v3.py` cover the actual signed accepted Trip,
MSG3, C holder, original worker/Fake/Meter, Pub3/cross-chat candidate reuse,
committed ACK-loss recovery, UNKNOWN cancellation, quota/output/time/final-render
limits, corruption rejection, cancellation and physical in-flight retirement.
The protected Trip test uses C's genuine NEEDS producer, signed accept and
source-bound edit/save; an old unbound manual editor is never given that authority.
Store tests distinguish inherited BG2 compatibility from actual producer proof,
and cover cross-owner denial, minimal ACL, immutable headers and down refusal.
Unit cases reject wrong request digest/role/version/Travel and Pub2/wrong digests.

Foreground MSG3 after Memory creation remains closed under its old producer
guard; this contract does not install a foreground Trip+Memory adapter. Real
provider/account/device/backup evidence remains #32/#29/#30.
