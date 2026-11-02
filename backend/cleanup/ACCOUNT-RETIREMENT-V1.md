# CLEANUP-ACCOUNT-RETIREMENT@1

Additive owner hook seam: `cj_cleanup.store.require_account_retirement(cursor,
request) -> None`. CLEANUP@1.0/1.1 request/receipt bytes and App APIs are unchanged.

The trusted owner uses the **same dedicated Store transaction** as its own erasure.
Query `original_result` first. For a new execution, call public `require_intent`
first, then this assertion, then the owner's scope lock/fence/verified deletion
and `record_result`. The host already bound the original subject/operation and
explicit account confirmation; a caller DTO cannot supply that authority.

The assertion accepts only account selection. It performs one parameterized
SELECT for the exact original subject_digest and operation_id retirement fence.
An observed fence returns None; absence, another operation/subject or a different
selection raises Denied. Database uncertainty propagates and authorizes no work.
It opens no connection/transaction, changes no role/GUC, writes no intent/fence/
result, dispatches nothing and retries nothing. No new DB privilege is granted.

The fence is the original irreversible account revocation, not proof that a
domain is empty or that a worker/usage outcome is settled. It does not grant a C
namespace or replace C's own identity/scope/epoch validation, canonical locking,
physical erasure and original-result evidence. C need not query B private tables.

```python
with store.transaction(request.operation_id) as cursor:
    old = original_result(cursor, request)
    if old is not None:
        return old
    require_intent(cursor, request)
    require_account_retirement(cursor, request)
    # Owner implementation: validate/lock its actual scope, erase, verify empty.
    erase_and_verify_owned_scope(cursor, request)
    result = record_result(cursor, request, 'confirmed')
return result
```

UNKNOWN reconciles only its original owner result; neither this fence nor an
empty response is permission to redispatch execute or invent an erasure receipt.
No memory-item deletion selection is added by this account-only seam.

Executable evidence in `account_gateway_pg.py` uses an actual signed confirmation
and its persisted original request. A real read-only dedicated-role transaction
returns None; wrong operation, foreign bound subject, absent retirement and
diagnostic selection fail closed without writes. Existing B DomainHook/UsageHook
also use this public assertion after require_intent in their real erasure flows.
