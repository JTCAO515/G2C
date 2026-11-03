# M3 single-memory erasure preparation (#26 / C hooks #27)

Memory-item implementation is pending. This document provides no approved item
cleanup intent, immutable descriptor or registered item store. Account-only hooks
are now main via PR461, described in ACCOUNT-CLEANUP-V1.md with their same-PR
permissions/fences/registry. They do not authorize one-item erasure.

## Verified boundaries

- M34/M37 history jobs, model output, candidate actions and origin map have an
  account hook. Item selection currently returns failed, never account deletion.
- Memory stop-use locks the scope and advances its epoch, but retains canonical
  source/item/operation and action bytes. That is not physical deletion.
- The current stop_use.source_history follows management edits. M37 candidate
  confirmation also changes the source through history_candidate_action. A new
  erasure graph must include both edge sets, the actual canonical item/source,
  immutable save operations and complete reverse references. It cannot assume
  the management edit chain contains candidate-confirmation history.
- M30 cj_trip_scoped_result.memory_input is memory_descriptor: snapshot/payload
  hashes plus context, subject, slots and max_bytes. It has no item ID. A hash is
  not an exact reverse item mapping. Initial erasure must explicitly use a
  conservative derived range and disclose it. It must preserve unrelated owners
  and formal user-accepted Trips; no claim of precise result deletion is valid.
- M37 history_origin has foreign keys to canonical source/item, not to a job.
  Existing CandidateAction1 confirmation reads the canonical candidate/source and
  immutable origin's original job/attempt; it does not read the job payload.
  Therefore overlapping private job batches can be erased without deleting an
  unrelated candidate's origin or inventing a new confirmation protocol. The
  old V3 candidate list and V4 publication-items readers do require that payload;
  a new explicit current-candidate projection is needed for those retained
  candidates after shared-job erasure. Keep Action1's user-confirmation semantics.
- PR461 upgraded standalone typed Memory and the seven C local factories to
  ACCOUNT-ADMISSION@2. M35 supplies the shared hashed account fence
  and restrictive runtime policies for C tables, including scope INSERT checks.
  Reuse that fence; do not invent a duplicate C account-retirement store. C hosts
  consume ACCOUNT-ADMISSION@2 so retirement/uncertainty is explicit
  admission, rather than a misleading empty RLS projection or generic DB failure.

## Required order

1. Under the actual captured account and canonical Memory lock, validate the
   explicit original item/version/source/epoch. Freeze its complete association,
   stop all sources in its graph, advance the epoch and install noncontent
   source/operation/item/message barriers in the same transaction.
2. Create B's actual memory-purpose cleanup operation from that original result;
   account-purpose cleanup is never substituted for one Memory item. C must
   retain the original association while source/job rows are removed, so B's
   later original intent and ACK reconciliation do not depend on deleted rows.
3. Owner hooks consume original_result/require_intent/record_result in the same
   dedicated cleanup-role transaction as physical deletion. Reconcile is a
   separate read and never renews execution from absence or UNKNOWN.
4. Delete selected canonical content, candidates, source refs, save/action bytes,
   jobs/checkpoints/results and conservative C-derived Trip/draft ranges. Never
   delete formal Trip authority for a Memory selection. Account hooks separately
   erase the whole owned C domain and retain only irreversible hash barriers.
5. Audit actual rows and actual model requests, including late work, retained
   chats, new tasks, end summaries, source/index rebuild and other ingress. An
   old message cannot become permitted merely because its origin row was erased.
   Explicit new saving uses a new source; it never reactivates an erased source.

## Proposed B consumer seam (not frozen / not provided)

`AssociationReader(cleanup_store, captured_memory_scope).read_original(request)`
returns bounded immutable UTF8 only for a real memory-purpose request. It uses
B's public require_intent under the dedicated role, verifies its original exact
selection against C's already persisted stop-use/erasure manifest and binds the
same subject/operation. Request/descriptor dataclasses do not grant permission.

Proposed exact result:

```json
{"version":"MEMORY-ERASURE-ASSOCIATION@1","operation_id":"original-operation","subject_digest":"sha256","memory_scope_digest":"sha256","selection":{"kind":"memory","item_id":"exact original item","item_version":2,"scope_epoch":3},"source_refs":[{"source_id":"exact original source","source_version":1}],"message_refs":[{"conversation_id":"exact chat","generation":"exact generation","sequence":1,"message_id":"exact message","input_sha256":"sha256"}],"job_refs":[{"job_id":"exact original job","attempt_id":"exact original attempt"}]}
```

The frozen implementation must specify canonical encoding, strict byte/count
bounds and positive/negative examples. Source refs come from the complete graph;
message refs are exact original coordinates/hashes, not text inference. Job refs
must include pending/inflight/UNKNOWN and overlapping source jobs, not only a
completed first producer. C never asks B to inspect C SQL. B retains unsettled
or UNKNOWN financial facts, original attempt IDs/hashes and zero automatic resend.

The proposed storage/fence is local PG only, appended migration with minimal
runtime SELECT/INSERT and needed column UPDATE, no runtime DELETE, new role,
BYPASSRLS or SECURITY DEFINER. It must ship its own account/item hooks and registry
in the same PR, with empty up/down/up, populated-down refusal and owner negatives.

## Remaining acceptance

Read-only preparation now has a candidate `source_graph.capture` implementation
and actual signed-PG probe: automatic inference -> user confirmation -> typed edit
enumerates all three sources, original message refs and the first producer; foreign
owner, byte bound and unlinked selected-item source refuse. It returns no Memory
text, persists nothing and has no execution authority. Its origin_producers are
not all overlapping queued jobs. The bounded prototype is not the future immutable
B descriptor or a scalable physical-cleanup API, and is not registered as provided.

The next read-only `association.prepare` prototype now joins every exact original
message coordinate/hash to C job batches, including old-source completed/UNKNOWN,
pending and inflight work. It also captures canonical source-command operation
identities and verifies actual save-ledger originals; confirmation/edit receipts
live in their own action ledgers and are not invented as generic save receipts.
Actual signed PG checks preserve all four job states across consent versions and
refuse stale selection, foreign owner or truncated job bounds. This still writes
no intent/manifest/barrier and cannot serve B's future original cleanup reader.

Actual API/version freeze and A notice, immutable manifest/reader, non-resurrection
fences, physical C hooks, B memory-purpose payload integration, actual in-flight
publication rejection, retained-chat ingress, rows/model-context audit and full
scripts/test.py/pg_suites.py are UNRUN for #26. This preparation closes no box.

## Candidate local freeze/cleanup implementation (unregistered)

Candidate M44 SQL is intentionally not in the manifest: B owns the next M43
background-header append, and this follows that actual migration/file lock.
It adds a private immutable original manifest and minimum hashed replay barriers.
`erasure_store.freeze` uses the actual canonical Memory transaction to stop the
complete item/source graph, advance versions, capture all job/message/decision
references and persist original bytes atomically. Original same-byte replay is
stable; IDs are not normalized. No runtime physical deletion is granted.

Actual private-PG component evidence now verifies current typed model projection
becomes empty, erased source IDs cannot be reinserted, and a new explicit source
can still be saved. `AssociationReader` returns only that original persisted
selection after B's real committed in-progress CLEANUP intent; DTOs/no intent do
not grant access, and the observation-only probe returns UNKNOWN, not erasure.

Candidate C item hooks use the dedicated original Store transaction/receipts:
derived -> management -> Trip derived -> canonical Memory. C-only component
cleanup physically removes selected source/item/save/action/job bytes, preserves
new explicit entries and only reports that component inventory. Hash-only cursor
and replay barriers remain. M30 uses the disclosed owned derived scope: non-
acceptable scoped results and nonaccepted proposals/bases/actions; accepted
formal authority is retained. This is not precise item-to-M30 matching.

These files are not installed, registered, frozen or provided to B/A. Remaining:
same-PR registry + account coverage for the new manifest, canonical candidate
projection after shared-job erasure, raw chat/model ingress fences, actual B
payload hooks/worker publication races, production-shaped signed erasure API,
exhaustive physical audits and full tests/review/exact CI. M44 direct SQL empty
roundtrip/minimal privileges and component intent/physical tests do not close #26.
