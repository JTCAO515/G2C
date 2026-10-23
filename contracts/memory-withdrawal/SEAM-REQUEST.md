# Minimal request to original MEMORY / CJ019 / CLEANUP / RUN owners

Pinned source evidence: `backend/memory_withdrawal/evidence/inputs.json`.
These are requested seams, **not agreed signatures or accepted architecture**.
No private cursor/SQL workaround is supplied.

1. MEMORY/CJ019: public same-transaction whole-item history/reverse-reference and
   retombstone interface, on the canonical scope row lock. Bind exact original
   withdrawal bytes/action ID, owning scope, item ID, expected item version and
   expected current source ID/revision. Under that same lock, read original action
   ledger first (same bytes historical replay, different bytes conflict); enumerate
   full old/current sources and their reverse references. Unknown/shared references
   must refuse until the original owner defines an item-specific non-collateral
   strategy. Never revoke a shared source globally or reinterpret pause as delete.
2. The original owner atomically writes withdrawn item/version, applicable source
   withdrawal/version fences, full-history retombstones, epoch increment and the
   immutable original action receipt. Keep CJ019's original action namespace/ledger
   semantics; CJ021 must not create a second official MEMORY/action authority. Agree
   the resulting receipt and query semantics with the owner. Exact original query
   only after uncertain commit/return; absence cannot authorize blind resend.
3. Existing `MEMORY-lifecycle-adapter.1` is documented as **CJ019-only** and its public
   `_receipt` validation accepts active/disabled, not withdrawn. Original MEMORY
   owner must publish the lawful guarded extension, with precommit/close/final
   binding and commit-unknown semantics, before CJ021 can install a withdrawal
   provider. Public `Transaction.cur/scope` extensibility alone does not define the
   missing history/retombstone or source authority protocol. Do not patch the
   existing validator, import private helpers or write alternative SQL here.
4. CLEANUP: single-item original confirmation/scope, operation/receipt linkage and
   actual per-store hook contract for controllable online records, summaries,
   indexes, caches, necessary RUN checkpoints, original action/source metadata,
   restore/backup and applicable device boundaries. Preserve original IDs/CAS,
   exact-byte receipts and unknown-invocation reconciliation. No account-wide auth
   revocation or guessed retention/TTL can stand in for this protocol. Specify
   cleanup of content while retaining the minimal approved withdrawal linkage;
   unresolved historical-source policy or hook is never complete.
5. CJ020/RUN/MESSAGE: trusted complete lineage at every context/raw retained-chat
   ingress; current memory/source check through real publication in the accepted
   shared transaction/fence. Fencing only vector search leaves raw-message and
   re-summary bypasses. Old source revisions and retombstones must survive rebuild
   and restore; new explicit save needs a newly approved source. Actual late-run
   rejection/physical stores/model context must be demonstrated by their owners.

No physical deletion, API activation, permissions, external fees/provider, account,
deployment or old-database work is requested or performed by this candidate.
