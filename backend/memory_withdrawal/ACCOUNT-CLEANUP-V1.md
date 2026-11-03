# C account cleanup V1 (#27)

Local C owner hooks for CLEANUP@1.1; the three existing C registry leaves are
registered in this same change. This does not implement a #26 memory selection
or assert whole-device/backup/provider erasure.

`cj_memory_withdrawal.account_cleanup.account_hooks(store, owner_scope)` is an
explicit local `Configuration.extra_hooks` factory. B passes its already captured
own principal namespace; C derives the existing Trip scope with trip_scope_for.
No request JSON, source text, manual flag or caller table/path chooses authority.
It returns MemoryManagementAccountHook, MemoryAuthorityAccountHook and
TripAuthorityAccountHook for their three exact existing registry targets.

Each account hook binds protocol1.1/target/subject/domain. It queries original_result
first; new execution requires B's public require_intent and exact original
require_account_retirement in the same dedicated Store transaction. It then holds
the canonical C scope lock, deletes its explicit code-owned tables in FK order,
verifies empty and records the original result atomically. ACK uncertainty returns
UNKNOWN; reconcile is read only and never obtains execution permission from absence.
Memory selection records failed with zero physical mutation, never an account wipe.

M41 appends only local permissions/policies and invoker triggers, no content table,
new role, runtime DELETE/TRUNCATE, BYPASSRLS or SECURITY DEFINER. Scope-only cleanup
UPDATE enables the canonical row lock, with frozen-plan/step RLS preventing rename
or another target/namespace. A first runtime scope INSERT also holds a shared
transaction advisory fence; cleanup takes the matching exclusive fence before its
scope read. A volatile invoker trigger rechecks current account retirement after
acquisition. Thus an invisible, in-flight first scope cannot commit raw owner data
after confirmed erasure. Shared acquisition is nonblocking if cleanup owns it, so
an old guard re-resolve cannot deadlock cleanup while holding a canonical row lock.

Existing history/output/origin/consent cleanup remains the memory-derived hook and
executes first in B's account order. Then C management precedes canonical Memory;
Trip erases its scoped draft/result/basis/action, NEEDS/manual, accepted and pending
record/proposal/receipt bytes before the Trip scope. This account path consumes B's
retirement barrier, not a second account authority or organizer cleanup privilege.

Actual private-PG component tests use signed candidate/confirmation/edit sources,
signed Trip acceptance and signed account confirmation with explicit C extra_hooks.
Physical initializer audits check C records empty and Bob retained; runtime roles
have no deletion privilege. Original replay/reconcile and foreign domain denial,
empty M41 up/down/up and populated-down refusal are tested. A deterministic first
scope pre-COMMIT pause reproduced a late raw scope surviving a false complete;
that original RED is retained and the final fenced scenario is PASS. Component
inventory excludes unrelated B/device/external stores and is never global cleanup
acceptance.

The original configured host must explicitly install account_hooks as its
Configuration.extra_hooks; merely importing the module or adding a registry
protocol does not install authority. A missing installation still blocks the
original operation. Existing B hooks and the independent complete inventory are
retained, not replaced by the component fixture.
