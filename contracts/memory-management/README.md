# CJ019 lifecycle-internal.1 — pause/resume candidate

Domain-only extension of [MEMORY-internal.1](../memory/README.md#transaction-and-subsequent-lifecycle-seams). Fixed input is main `513a2ebaa8cc6724cf71c68937075f0349e98a9d`, including original CJ011/426 implementation. This is an internal consumption proposal for Main/CJ005 confirmation, **not a MEMORY@1.0 public wire freeze**. No API route, generated client, AUTH rule, migration registration, UI or RUN publication adapter is included.

`backend/memory_management/cj_memory_management` imports CJ011 `Receipt`, `Command`, errors and public `Repository.transaction` / `Transaction` extension seam. The extension uses the yielded transaction's public `cur` and `scope`, inheriting original lock/read/current-context methods. It never reads underscored repository state. There is one authority: existing `cj_memory_scope/source/item`. The only new table holds original lifecycle action receipts. CJ011 source/item bytes and its original save ledger remain untouched. No Trip import or write exists.

## Internal interface and limits

Trusted server composition constructs `Repository(fresh_non_autocommit_connect, trusted_scope)` and `Service(repository)`. `Service.apply(original_utf8) -> existing cj_memory.domain.Receipt`; `Service.query(action_id) -> Receipt | None`. The caller supplies scope from the existing trusted binding; raw input cannot supply owner, scope, source authorization, confirmation flags or replacement source data. No default connection string or environment fallback exists.

`apply` requires immutable UTF8 JSON bytes, at most 32768 bytes, exact keys:

| Key | Type / values |
| --- | --- |
| action_id, item_id | Nonblank exact string, at most 4096 characters |
| operation | `pause` or `resume` |
| expected_version | Integer >= 1, bool rejected |
| expected_source_version | Integer >= 1, bool rejected |

All keys required; duplicate keys and extras rejected. IDs and original input are preserved without trimming or Unicode normalization. Example fixtures are in [examples.json](examples.json); actual executable examples live in `backend/memory_management/tests/checks.py`.

This Service is a **trusted internal domain entry only**. It does not authenticate and must not be exposed directly as HTTP. CJ005 must first obtain an agreed guarded producer seam from the original MEMORY owner, reusing existing AUTH decisions and request lifetime checks before commit and after projection. Existing `Service.with_operation` does not yet expose these actions; there is no private bypass or copied AUTH implementation here. Deployment and protected wire consumption remain UNRUN. Existing CJ011 methods remain compatible.

## State, CAS and receipts

Under the SAME `cj_memory_scope` row lock used by CJ011: read original action → exact-byte replay or conflict → find scoped item → compare expected item version → lock original source → compare both current source revision and item's source revision with expected_source_version → update item status/version → increment scope epoch → insert original action receipt → commit. A commit exception/interruption retains unknown outcome. All new state and receipt commit or roll back together; the original repository owns commit/rollback/cleanup behavior.

`pause` accepts an `active` item and makes it `disabled`. This increment manages already effective facts, experiences and preferences. Candidate/withdrawn items are not promoted or reinterpreted. Pausing an item whose source has expired or been deauthorized is allowed only when both revisions still match, and confers no source authority.

`resume` accepts a `disabled` item only if its exact current version has this module's own prior `pause` receipt. A generic disabled row may have come from a candidate or another withdrawal reason and cannot be safely enabled. Original source must still have matching revision AND exact approved bytes, authorization, confirmation, semantic resolution, active status and unexpired validity. Inference remains excluded. Resume cannot renew expiry, change consent, repair source revisions, revive withdrawn entries or replace a newer active item in the same canonical subject/slot/extent/context. Canonical-slot collision is Conflict; a user must review the newer entry.

Existing `Receipt.operation_id` contains the original `action_id`, with item ID, resulting item version/status and SHA256 of the **persisted original action bytes**. Receipt is historical; original pause replay after a successful resume returns the original disabled/version receipt without mutating the new active version. Lifecycle IDs are scoped to the lifecycle action ledger (one namespace shared by pause and resume); save IDs retain the original CJ011 ledger namespace. Same lifecycle ID/different bytes conflicts, including whitespace or operation changes. Query absence does not prove an earlier unknown action never committed or authorize re-send after cleanup. Receipt retention/tombstone policy is unresolved, so there is no unlimited dedupe guarantee.

`InvalidInput`, `Conflict`, `Unavailable` reuse the original domain classes. Missing/other-scope items both produce generic Unavailable. `ActionUnknown` is a subclass of original `CommitUnknown` with original `action_id`, `commit_possible=True`, `recovery='reconcile_original'`; catches commit errors and BaseException interruptions already normalized by CJ011. Preserve original bytes/ID and query only under a newly valid caller. No automatic retries or replacement IDs exist. Cancellation before commit propagates after rollback of this attempt; it is never proof that a prior attempt with the same ID did not commit. No JSON/public success response is constructed here.

## Read and publication compatibility

Existing CJ011 detail/list/group reads immediately observe disabled/version state; effective reads exclude disabled items with the existing query. Resume exposes the unchanged original text/source/scope only while that source remains effective. Other users, other entries, subject and temporary context boundaries are unchanged. Scope epoch invalidates old `Context` through original `Transaction.require_current`; it also rechecks time/source validity. RUN must retain that SAME transaction/lock through real publication. The PG test exercises the shared lock and original `require_current` only; it is not actual RUN integration or publication authorization. `check_fence` remains only a probe.

New `cj_memory_management_action.original_input` contains identifiers and action bytes. CJ021/CJ024 must include this ledger in cleanup/backup/restore scope alongside original source/item/save ledgers. No deletion, retention, roles, grants or RLS change is supplied. Disabled is not deleted. Candidate SQL remains unregistered and is tested only in a fresh private cluster.

## Minimal unresolved edit-source contract

The original source approval binds the exact original `Command.raw`; changing text while keeping that approval would break provenance and authorization. No text edit is implemented until Main/CJ011/CJ005 confirm:

1. The trusted producer that approves **the new exact edit bytes** for the unchanged subject/slot/kind/extent/context, including sensitivity/purpose/expiry; client approval booleans are not an option.
2. How a new correction source/revision links to the original source while retaining necessary history, and which owner supplies the history/cleanup seam. Do not overwrite old approved bytes or invent source consent/retention.
3. The source/item expected-version CAS and receipt contract for edits, without candidate promotion or Trip mutation. Existing scope lock, atomic epoch/version increment and unknown-action rules are mandatory.

This field-level gap blocks text edits only. Pause/resume code and its verification are independently reviewable. Original #17 UI, same-conversation next answer, actual model context, new chat, RUN late-result rejection and downstream combinations remain open/UNRUN.
