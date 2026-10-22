# Internal history/draft slice — message-history.1 candidate

Parent 3828e9dac48cba1bd5c7bb6267fc640d9a2e9eb4. Changes only backend/message/**;
client fresh-authority candidate remains byte-unchanged for its independent review.
No shared migration number/registry, HTTP route, OpenAPI or generated client modified.
This is an internal interface proposal for CJ005 confirmation, not a second wire contract.

## Exact service and AUTH boundary surface

| Service method | Inputs | Return / meaning |
|---|---|---|
| conversations(cursor=None, limit=20) | internal ChatListCursor or first-page None | (list[ChatSummary], next cursor or None) |
| message_history(conversation_id, cursor=None, limit=20) | existing internal Cursor binding scope/chat creation generation/data epoch/high-water | (list[HistoryMessage], next cursor or None) |
| read_draft(conversation_id, generation) | explicit current creation generation, not None/empty | Draft or None (no draft in this valid current chat only) |
| save_draft(conversation_id, generation, original_utf8, expected_revision) | immutable UTF8 bytes; revision0 means no existing draft | committed Draft at revision+1; stale revision InputConflict |

Boundary exposes the same methods with token first, always using _service → current
AdmissionChecker → server-owned repository resolver → transaction/commit/return guards.
No caller owner/scope parameter, permissive fallback or separate read-only auth shortcut.
Unknown/denied identity/membership/email/invitation is blocked before repository resolve.
Whether uninvited users may read past history remains a product/AUTH decision; this slice
keeps the existing conservative restricted-business gate, not a new access policy.
Missing provider/default composition fails closed. Internal Service alone is not auth.

ChatSummary fields: conversation_id, generation, epoch, list_sequence. ChatListCursor:
scope, scope_generation, epoch, through, after. HistoryMessage: receipt, original_utf8,
text parsed from the original validated body. Draft: conversation_id, generation,
revision, original_utf8. Cursor scope is trusted internal binding, never deserialized
from caller fields as authority. Public cursor signing/encoding/expiry belongs to future
CJ005 wire work. Limit1..100 is current internal guard, not a newly approved product quota.

## Snapshot and data integrity

Scope row is locked first, then chat, preserving existing lock order. Chat list uses
identity list_sequence and a fixed high-water boundary so append does not enter an
existing scan. Scope history_generation distinguishes scope recreation; history_epoch
changes through a local candidate trigger when chats are deleted or generation/epoch/
active changes. Old snapshots reject ResyncRequired instead of silently skipping removed
items or returning recreated IDs. A changed scope invalidates its whole old list snapshot;
other scopes remain unaffected. New snapshots still enumerate surviving neighboring chats.

Body pagination preserves raw bytes and sequence ordering; validates message ID/chat ID
and raw SHA256 against each receipt. Missing sequence/old creation/data generation fails
rather than silently yielding partial history. Foreign/missing/inactive chat is Unavailable
with no returned text. No fake Trip; current messages still require nullable Trip path.

Draft save is a separate transaction and versioned compare-and-write under scope lock.
It never creates a message receipt, run or delivery obligation; empty UTF8 draft is an
explicit saved value, not message send/deletion. Cross-generation access is rejected.
CommitUnknown is inherited unchanged: query current original draft/revision to reconcile;
a retry with stale expected_revision conflicts, never overwrites silently. There is no
durable per-draft-action dedup journal and no claim that equal content proves which
writer's unknown update committed. No blind retry or force overwrite API is supplied.

## Candidate SQL / integration constraints

candidate.sql adds scope history_generation/history_epoch, chat identity list_sequence,
a scoped active-list index, cj_message_draft with current-chat-generation foreign key,
and a chat change trigger. Its trigger is not SECURITY DEFINER and grants no permissions.
All mutation/cleanup writers must take scope lock before chat rows to avoid inverted lock
order; direct unsupported scope-owner rewrites are not an API. These DDL statements are
for a NEW empty isolated database only, not an upgrade of any deployed prior candidate.
No shared migration registered; CJ005 must review a versioned migration/compatibility path
before real integration. Existing external consumers must not apply CREATE TABLE blindly.

CJ009 owns draft/raw/history-cursor data and eventual hooks; CJ005 registers formal stores
and permissions, CJ024 coordinates retention/revocation/backup cleanup. No retention TTL,
physical cleanup lifecycle, RLS/grant policy or backup restoration guarantee implemented.
History generation is a cursor invalidation mechanism, not the client's external
nonrollbackable original-action authority. Live client POST remains disabled.

## Actual validation (new independent local cluster)

New private directory backend/message/.local-pg-02, PostgreSQL16.15, explicit cj009 user,
Unix socket only under its s directory, identifier55440, listen_addresses empty. Private
0700 directories/socket; no existing database/VP/cloud/other tree read or modified.
Reused ONLY the previously installed task-local Python3.14.7/psycopg3.2.10 interpreter,
not its stopped .local-pg-01 database. No install/global config/launchd changes.
Applied module candidate.sql only to new empty task database, exact SHA256 in
history-pg-environment.json: 4060541a06fdd1233b787b212917ecd69728aa272f2e9ce46b34d48d44b1107b.

PASS: 6 real PG tests in history-pg-tests.txt (list/high-water/scope, delete/recreate,
exact message UTF8/body/epoch, draft reopen/revision/no-run, old generation, empty/inactive).
PASS: 2 additional executions in history-pg-additional.txt (draft checkpoint preparation
and new concurrency/missing-generation test). These are 7 unique PG methods, not 8.
PASS: 2 actual fixed AUTH79f88b gate + injected facts + real PG checks in history-auth-tests.txt:
allowed paths, denied/unknown before resolver, commit-boundary revocation actual rollback.
Synthetic verifier/facts are NOT real JWT/identity/provider or RLS acceptance.
PASS: real graceful cluster restart + new Python process exact list/body/draft revision
readback (history-pg-restart.txt). Final safe stop (history-pg-stop.txt), data/logs retained;
no postmaster.pid or task socket remains. Only synthetic test rows were deleted to simulate
same-ID recreation in this new database; no production cleanup API/old data deletion.

Python syntax/diff checks PASS. Prior backend/Swift evidence reused; no broad old-suite
rerun. Real target auth, RLS/privileges, provider/model, deployed migration, TTL/physical
cleanup, crash/power loss, device/API and independent review remain UNRUN/PENDING.
Issue10 remains open. CJ005 can now confirm this exact internal slice before formal wire.

CJ005 proposal consumption: HISTORY-CONTEXT.md confirms exact e3a15696 wire proposal and
introduces Boundary.with_history_context for same-principal/scope codec binding. Do not
consume _service or independently reauthenticate for cursor authority. SQL/txn semantics
remain unchanged; no old database application is authorized by this interface delta.
