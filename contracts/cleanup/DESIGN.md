# #402 shared cleanup design (#26 and #27)

Design baseline: main `d1d21ee5`. Only local migrations and fresh private PG are
authorized. This is the common design; domain owners implement their own hooks.
[CLEANUP@1.0](V1.md) is additive. Existing rc behavior stays frozen.

## Registry inventory and retention

Every registry node/object has `owner_line` and `retention_category` in 1.14.0.
An inventory correction adds already-provided M14–M30 association tables to their
existing domains; it provisions no storage and declares no hook implemented.

| Registry target | Line | Tables / objects | Retention category and reason |
|---|---|---|---|
| business (container) | B / owners | All business children | `domain_specific`; not a separate erased dataset. |
| business/message | B | `cj_message_scope/chat/receipt/delivery/draft`, `cj_travel_context/action`, message context/needs/travel/trip/edit profiles and references, local run protection/requirement and metered profile/requirement | `user_content`: chat/draft/travel context and original action associations until user/account deletion. Scope/profile fences are not recyclable. |
| business/usage | B | `cj_usage_ledger_candidate` | `account_reconciliation`: reservations, charges, unknown attempts and original action evidence are billing/settlement state, not logs. No 90-day truncation. Delete as part of account cleanup, subject to actual settlement and result. No newly invented compliance retention. |
| business/memory-authoritative | C | `cj_memory_scope/source/item/operation` | `user_content`, until user/account deletion. Source expiry is access policy, not a TTL. System does not proactively delete memory. |
| business/trip-authoritative | C | `cj_trip_scope/proposal/record/receipt`, manual basis/intent, needs basis/action/current/edit/plan-context, scoped basis/action/result | `user_content`, until user/account deletion; exact association/dependency order belongs to C. |
| business/needs-current-planning | B | `cj_needs_scope/record/revision` | `user_content`, until user/account deletion; revisions contain original private planning inputs. |
| business/feedback-private-actions | B | `cj_feedback_action` | `user_content`, until user/account deletion; voluntary feedback and immutable read-time source reference, no extra transcript copy. |
| business/cleanup-metadata | B | `cj_cleanup_journal_candidate` and future registered coordinator state | `account_reconciliation`: keep only minimal original progress/result and non-resurrection fence while cleanup needs it. Erase private principal/journal/confirmation metadata as its own hook; retain no user-linkable plaintext under an invented audit exception. |
| business/memory-management-actions | C | `cj_memory_management_action` | `user_content`, until user/account deletion; clean with source/item/save ledgers. |
| checkpoints (container) | B | run child | `domain_specific`. |
| checkpoints/run | B | `cj_run_scope/record/event`, `cj_run_step_usage`, `cj_run_metered_binding/operation` | `mixed_content_diagnostics`: persisted visible answers/effects and their authoritative associations remain until user/account deletion. Diagnostic-only logs/checkpoints get 90 days. Metered operation/unknown settlement is reconciliation state. Do not delete an entire run/event ledger at 90 days and thereby lose answers or accounting. #27 must separate the actual diagnostic subset before applying cutoff. |
| memory-derived | C | Not provisioned (no JT, vector or embedding placeholder added) | `user_content` when actually provided; same-PR registry and hook required. No claim of cleared storage from this placeholder. |
| device-cache | A | Container: encrypted-message-file, sdk-session-keychain, message-key-keychain, trip-pending-file | Each object `user_content`; local exact-key/file cleanup, last successful sync +14 days offline-read fence. A owns actual deletion and evidence. |
| external-processing | B / provider owners | Not provisioned | `external_unprovisioned`; no supplier retention/deletion result presumed. |

Backups: rolling 30 days, restore must replay erasure/revocation fences before any
private access. #30 owns real backup validation; neither this design nor online
receipts count as a backup PASS. Runtime/diagnostic cleanup is #27, same dedicated
role and injected clock; tests cover just before/at/after 90 days and other owner.

## Local role, tables and transaction boundaries

Plan an append-only local migration after #403 (next available version checked
under migration lock; 0031 at design baseline). Dedicated role `cj_local_cleanup`,
NOSUPERUSER/NOCREATEDB/NOCREATEROLE/NOINHERIT/NOREPLICATION/NOBYPASSRLS.
No grant of this role to `cj_m1_runtime`. Explicit trusted local cleanup connection;
no credentials in source, logs, responses or this design. FORCE RLS remains on.

Grant only SELECT needed to establish/verify the frozen selection, DELETE on each
explicit registered table and narrowly required UPDATE columns for fences/results.
No TRUNCATE, SECURITY DEFINER, ownership transfer, broad schema/default grants or
dynamic registry SQL. Per-table policies bind canonical scope (including derived
Trip/USAGE scope) to the coordinator's server-selected original account/operation.
Missing bindings deny. Cross-owner DELETE returns no rows; cross-owner INSERT/
UPDATE and runtime role switching/deletion are rejected. New domain storage must
add its own ACL/policy and hook together; this migration cannot pre-grant future tables.

The coordinator persists original intent, registry/entry digests, original IDs,
revision and result; domain deletion/result are atomic. Auth revocation and task
stop must be durably verified before erasure. Domain hooks lock their canonical
scope and respect global dependency order: C derivatives before message/run parents,
metered bindings before usage ledger, child rows before scope anchors. Failure to
resolve an FK is a visible failure, never permission to expand the selection.
Stable erased-scope fences prevent late workers, receipt resubmission or restore
from recreating private data. C supplies exact memory/candidate/source associations;
A supplies exact device selection. B does not implement either owner's hook.

## Audit, recovery and rollback

Audit stores bounded IDs/digests/status only, not deleted content, tokens, tool
payloads or exception text. It is private account-associated data and is included
in cleanup. Keep an opaque minimal original-operation result for restricted progress
and an irreversible fence; private journal/subject metadata must be erased before
its own hook confirms. No application log prints scope/request/journal bytes.

Commit intent before invoking a hook. Interruptions are unknown, then reconcile
the same invocation's durable result without dispatching. Registry changes latch
blocked and require a new explicitly confirmed scope, never an in-place scope
change. Foreign and absent operations are indistinguishable. After revocation only
the original operation's authenticated progress projection is available.

Rollback code/role activation disables new execution; revoking local grants is
reversible. Deleted content is not restored by reverting code. Empty up/down/up
must pass; down refuses populated new tables/fences/results. Never erase recovery
evidence to make down pass or resurrect erased content to roll back. Applied
migration bytes and rc contract files remain unchanged.

## Delivery and evidence boundaries

This first PR freezes the ABI, strict codecs, positive/negative examples and this
inventory/design. It does not grant roles or perform deletion. #403 follows; then
#402 implements local role, registry fail-closed and original-operation recovery.
#15 adds feedback hook; #27 adds B hooks, revocation/stop/erasure orchestration and
90-day diagnostics. L0/L1, independent redline review and exact-head CI are
reported as actually run. Real accounts/providers, cloud, backups and devices
stay UNRUN and are tracked by #32/#29/#30.
