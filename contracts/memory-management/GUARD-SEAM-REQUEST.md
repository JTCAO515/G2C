# CJ019 guarded lifecycle: exact producer seam request

Historical gap status: reproduced on the original fixed input. Producer candidate `0045e423f004f873e2786aa98b2600b70772a921` now addresses this request; CJ019 guarded consumption is implemented in the subsequent candidate, with independent gates pending. This is not an approval request. Domain candidate remains `6e11d48815259bc3d879e63cd794e37e67694b86`; its original independent 14-PG/restart evidence is reused. This follow-up changes no domain algorithm, original MEMORY source, AUTH policy, SQL or root API. It does not implement or claim a guarded management endpoint.

## Confirmed input and non-DB probe

Fixed input `513a2eb…` and current Publish `b33184f…` expose the same MEMORY tree `e959c42d23a3879fdcbbb62dd0dc362de696da01`. The original owner's newer `cf6f9138147780de9cd6cd3df86642b0aec6ec5b` adds `consume_current`, but no lifecycle action/query or trusted extension registration point. Its private guard state is not a consumer API.

Run `python -B backend/memory_management/tests/guard_seam_probe.py` with existing Python3.11+; no PG or external effects. Actual output: [guard-seam-probe.txt](../../backend/memory_management/evidence/guard-seam-probe.txt).

The probe uses the existing `TrustedPrincipal` and public `Service.with_operation`, validates an actual five-field CJ019 action through `Action.parse`, then confirms:

- `ctx.save(raw)` rejects it via original `Command.parse` before a transaction.
- `ctx.save_manual(raw)` rejects it via original nine-field parser before a transaction.
- The context has no lifecycle write/query extension. Original `query` refers to the save ledger, not the CJ019 action ledger.

A successful bytes callback proves only the existing request entry is callable; it does not prove guarded pause/resume. No database was opened and no private context/repository state was consumed.

## Minimal request to original CJ011 owner, routed by Main

Please expose a canonical **trusted-server-only** extension to the existing guarded lifetime, with these required consumer capabilities. The following method names are proposed internal names for owner confirmation, not published wire:

1. `ctx.apply_lifecycle(original_utf8) -> cj_memory.domain.Receipt`. CJ019 supplies its immutable trusted adapter / parser at host construction, outside wire. Parse the original action ID before mutation, allow at most one action in this request lifetime, and use that exact ID for unknown-result metadata. Never wrap the action as a fake save, use a read callback for writes, or reconstruct its bytes.
2. `ctx.query_lifecycle(action_id) -> Receipt | None`. Use the same captured scope and a guarded transaction, reading only the original lifecycle receipt ledger. It cannot initiate apply/retry or infer success/failure from absence.
3. The trusted adapter receives the **already guarded current transaction** and original input (e.g. `apply(transaction, raw)` / `query(transaction, action_id)`). It must not receive private guard state or open another connection. CJ019 can extend the documented public Transaction seam (`cur`, `scope`, `lock_scope`) and use its existing lifecycle SQL. The canonical owner must specify the exact adapter registration signature and fixed module version before consumption; no guessing a generic hook.

The canonical owner continues to own all existing AUTH/identity/lifetime behavior. Required observable semantics: fresh entry/transaction/ready checks; fresh precommit check **inside** the same transaction after mutation; aftercommit and after cleanup/close check; final check after callback projection/encoding. Capture original principal, scope, repository and trusted adapter identity; replacements, cancellation, swallowed guard failures and scope drift must withhold output. Context must remain synchronous, thread-bound and invalid after return; prohibit reentry/deferred/async/streaming output. The callback returns final encoded bytes only. No second AUTH type or policy belongs in CJ019.

After commit attempt, lost ACK, cancellation, postcommit/close/final identity loss or projection failure must preserve the original action ID and typed `OperationWithheld`/`reconcile_original` semantics; never return private success bytes, say not saved, or resend. Precommit denial rolls back this attempt and does not prove an earlier same-ID attempt was absent. Query with a newly valid binding is the only recovery action. Existing save/read consumers and signatures remain compatible.

## Work available after the seam is fixed

CJ019 will consume the owner-confirmed adapter signature in its own two directories and add only targeted new guard cases: before-commit rollback; committed-but-withheld result recovery; guard changes after commit/close/projection; original-byte query; cancellation and caught failure stickiness; callback escape/reentry; A/B binding drift and repository replacement. Reuse original 14-PG/restart tests; no repeated uv/old runner or new production resource/permission probe.

Text-edit source authority/history remains a separate unresolved contract from the [domain contract](README.md#minimal-unresolved-edit-source-contract); it does not block agreeing or testing this guard seam. API/UI/RUN integration, real model/account/device and full original Issue17 remain UNRUN.
