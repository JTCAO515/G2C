# M3 single-memory erasure preparation (#26 / C hooks #27)

Implementation is pending. This document provides no runtime factory, approved
cleanup intent, descriptor or registered store. Do not advertise any hook as
provided until its physical implementation, fence and same-PR registry land.

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
- Main's standalone typed Memory and several C local factories still construct
  invitation-only admission. M35 already supplies the shared hashed account fence
  and restrictive runtime policies for C tables, including scope INSERT checks.
  Reuse that fence; do not invent a duplicate C account-retirement store. C hosts
  should also consume ACCOUNT-ADMISSION@2 so retirement/uncertainty is explicit
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

Actual API/version freeze and A notice, immutable manifest/reader, non-resurrection
fences, physical C hooks, B memory-purpose payload integration, actual in-flight
publication rejection, retained-chat ingress, rows/model-context audit and full
scripts/test.py/pg_suites.py are UNRUN for #26. This preparation closes no box.
