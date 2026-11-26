"""Verify-only CLEANUP@1.1 hook for business/service-sessions (#1770, ADR-0009 sections 4 and 6).

Service conversation content (cj_service_message, cj_service_message_authority) is its own
sensitive storage domain, but it is erased by ON DELETE CASCADE when the business/message hook
deletes cj_message_chat. This hook deletes nothing and holds no DELETE grant: after the
original account fence it confirms both tables are empty for the scope and otherwise refuses,
so the operation stays fail-closed. The gateway runs unlisted targets after business/message.
"""
TABLES = ('cj_service_message_authority', 'cj_service_message')


class ServiceSessionHook:
    def __init__(self, store, scope):
        self.store, self.scope = store, scope

    def execute(self, request):
        from cj_cleanup.core import Denied
        from cj_cleanup.store import original_result, record_result, require_account_retirement, require_intent
        if (request.subject_digest != self.store.subject_digest or request.domain_scope != self.scope
                or request.selection.kind != 'account'):
            raise Denied('service session cleanup unavailable')
        with self.store.transaction(request.operation_id) as cur:
            old = original_result(cur, request)
            if old is not None:
                return old
            require_intent(cur, request)
            require_account_retirement(cur, request)
            cur.execute("SELECT set_config('cj.cleanup_scope',%s,true),set_config('cj.cleanup_purpose','account',true)",
                        (self.scope,))
            for table in TABLES:
                # Explicit code-owned identifiers only.
                if cur.execute(f'SELECT 1 FROM {table} WHERE scope=%s LIMIT 1', (self.scope,)).fetchone() is not None:
                    raise Denied('service session cleanup unconfirmed')
            return record_result(cur, request, 'confirmed')

    def reconcile(self, request):
        from cj_cleanup.store import original_result, receipt_for
        with self.store.transaction(request.operation_id, writing=False) as cur:
            value = original_result(cur, request)
        return value if value is not None else receipt_for(request, 'unknown')
