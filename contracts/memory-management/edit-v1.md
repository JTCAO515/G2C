# MEMORY-MANAGEMENT-EDIT@1 (local runtime only)

Frozen by C under JT's 2026-10-30 C1 authorization, additive to the immutable
five-field pause/resume action. No production/cloud activation or iOS change.

`POST /v1/memory-edit-actions`, bearer AUTH, `application/octet-stream`, identity
encoding. Body is the exact original UTF8 JSON, at most 32768 bytes, with exactly:

```json
{"version":"MEMORY-MANAGEMENT-EDIT@1","action_id":"edit-1","operation":"edit","item_id":"item-1","expected_version":2,"expected_source_version":1,"text":"新的原文 / corrected original"}
```

IDs and text are nonblank strings of at most 4096 characters. Versions are positive
integers (bool rejected). No duplicate/extra fields or Unicode normalization.
Owner, subject/slot, kind, extent/context, approximate time, source approval,
expiry, new source ID and pause anchor are server-owned. `edit` on the old endpoint
is rejected; old pause/resume fields, schemas and response bytes remain compatible.

The explicit local host is `cj_api.local_app.create_local_memory_management_app`:
existing strict JWT/admission and transaction-lifetime MEMORY guard, runtime
nonowner PG connections and explicit `LocalMemoryConfiguration`. Its profiles
approve the new command and exact original edit bytes through `ManualPolicy`.
Absent, expired, disallowed or semantically unresolved collection is rejected.
The historical closed factory remains closed; no review-harness factory is used.

Under the original MEMORY scope lock: original action lookup, item/source CAS,
current source exact-byte/authorization/confirmation/semantic/expiry check,
server policy evaluation, immutable new source insert, item source/text/version
update, epoch increment and original action receipt all share one transaction.
Facts, experiences and preferences are eligible; inference/candidate/withdrawn
items are not. Editing a disabled item requires the module's own pause history,
retains disabled status and its validated pause-version anchor. Resume requires
that anchor and current source authority, and rejects an occupied canonical slot.

`source_id = edit-v1:` plus SHA256(original edit bytes), scoped by the authenticated
owner. It identifies provenance, never authorization. Old sources and original
save/action bytes remain intact. New source version is 1; source expiry comes
only from current explicit server policy. History links previous/new sources and
own-pause version in the existing management ledger; reads validate these against
original bytes and source records. No second version or semantic engine.

The receipt uses the existing `MemoryManagementReceipt`. Its action ID/hash are
the persisted original action bytes. Historical replay returns the original
receipt without changing current state or renewing policy/source expiry.
`GET /v1/memory-management-receipts?action_id=...` reads the same original ledger;
a missing row is not permission to resend an unknown action. Different bytes
with the same ID conflict. Commit/return uncertainty withholds success and keeps
`reconcile_original`, with no automatic retry, replacement ID or provider call.
Fresh admission applies to reads, replay, precommit and private return.

Error wire retains BASE and the existing management codes: malformed input 400,
CAS/slot/original-byte conflict 409, access 401/403 (unknown 503), unresolved source
or write outcome 503. Do not display a 503 as saved. No Trip write, physical delete,
cleanup, real provider or external account access is performed.

Migration 0019 is local runtime only: adds nullable lineage columns and checks,
FORCE RLS on the action ledger, runtime SELECT/INSERT and only item
UPDATE(status,version,original_input,source_id,source_version). No source approval
UPDATE, ledger UPDATE, DELETE/TRUNCATE, new role or SECURITY DEFINER. Empty-schema
up/down/up is reversible. Once edit history exists, down refuses atomically and
preserves data; never delete history to force rollback. Old migrations are fixed.

Positive/negative executable examples: `edit_host_pg.EditManagementChecks`, loaded
by the existing `memory_run` PG group. These exercise the actual signed API,
runtime SQL, source history, paused edit/resume, three kinds and bilingual bytes,
concurrent CAS, canonical-slot conflict, candidate/unknown policy, cross owner,
ACK unknown, rollback, fresh admission, process object reconstruction, scope reset,
minimal ACL, nonempty down refusal and actual worker/FakeProvider recall in two
conversations. Actual process recall is also retained in the original memory_run
checks. #270 owns lifecycle-to-inflight-fence combinations; #273/#227 own typed
travel scope. iOS regeneration/client consumption belongs to A/#271.
