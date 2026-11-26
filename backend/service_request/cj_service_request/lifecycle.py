"""SERVICE-REQUEST@1 scope fence and account-erasure hook (#1769, ADR-0009 section 6).

Same shape as FEEDBACK@1.0: the runtime locks a live, never-retired scope row before any
read or write; the hook retires the row irreversibly under the same lock, then erases every
request, history entry (with evidence bodies and staff refs) and escort view audit row, and
de-links the staff audit (#1771).
"""
from hashlib import sha256

TABLES = ('cj_service_request_view', 'cj_service_request_history', 'cj_service_request')
DELINK = 'UPDATE cj_service_request_staff_audit SET scope=NULL,request_id=NULL WHERE scope=%s'
LINKED = 'SELECT 1 FROM cj_service_request_staff_audit WHERE scope=%s LIMIT 1'


def scope_digest(scope):
    return sha256(scope.encode('utf-8')).hexdigest()


def bind_runtime(cursor, scope):
    from .store import Unavailable
    cursor.execute("SELECT current_setting('cj.message_scope',true)")
    if cursor.fetchone()[0] not in (None, ''):
        raise Unavailable()
    cursor.execute("SELECT set_config('cj.message_scope',%s,true)", (scope,))
    key = scope_digest(scope)
    cursor.execute('INSERT INTO cj_service_request_scope(scope_digest) VALUES(%s) ON CONFLICT DO NOTHING', (key,))
    cursor.execute('SELECT retired FROM cj_service_request_scope WHERE scope_digest=%s FOR UPDATE', (key,))
    if cursor.fetchone() != (False,):
        raise Unavailable()


class ServiceRequestHook:
    """Injected only by the original local account-cleanup composition."""

    def __init__(self, store, scope):
        self.store, self.scope = store, scope

    def execute(self, request):
        from cj_cleanup.core import Denied
        from cj_cleanup.store import original_result, record_result, require_intent
        if (request.subject_digest != self.store.subject_digest or request.domain_scope != self.scope
                or request.selection.kind != 'account'):
            raise Denied('service request cleanup unavailable')
        with self.store.transaction(request.operation_id) as cur:
            old = original_result(cur, request)
            if old is not None:
                return old
            require_intent(cur, request)
            cur.execute("SELECT set_config('cj.cleanup_scope',%s,true),set_config('cj.cleanup_purpose','account',true)",
                        (self.scope,))
            key = scope_digest(self.scope)
            # Waits for any writer holding the live row; afterwards no writer can lock it again.
            cur.execute('INSERT INTO cj_service_request_scope(scope_digest,retired) VALUES(%s,true) '
                        'ON CONFLICT(scope_digest) DO UPDATE SET retired=true', (key,))
            # Staff audit (#1771): keep staff, time and action; drop the user-linkable request id and
            # scope first, so the cascade from the request deletion below does not take the rows.
            cur.execute(DELINK, (self.scope,))
            for table in TABLES:
                cur.execute(f'DELETE FROM {table} WHERE scope=%s', (self.scope,))
            if cur.execute(LINKED, (self.scope,)).fetchone() is not None:
                raise Denied('service request cleanup unconfirmed')
            for table in TABLES:
                if cur.execute(f'SELECT 1 FROM {table} WHERE scope=%s LIMIT 1', (self.scope,)).fetchone() is not None:
                    raise Denied('service request cleanup unconfirmed')
            if cur.execute('SELECT retired FROM cj_service_request_scope WHERE scope_digest=%s',
                           (key,)).fetchone() != (True,):
                raise Denied('service request fence unconfirmed')
            return record_result(cur, request, 'confirmed')

    def reconcile(self, request):
        from cj_cleanup.store import original_result, receipt_for
        with self.store.transaction(request.operation_id, writing=False) as cur:
            value = original_result(cur, request)
        return value if value is not None else receipt_for(request, 'unknown')


class ServiceStaffAuditHook:
    """CLEANUP@1.1 hook for business/service-staff-audit (#1771, PIPIA section 9).

    The append-only staff audit keeps staff ref, time and action after erasure; this hook clears
    the erased owner's scope and request id (the only user-linkable values) under the original
    account operation and confirms none remain. Idempotent with ServiceRequestHook, which also
    de-links before deleting, so either order holds; it deletes nothing.
    """

    def __init__(self, store, scope):
        self.store, self.scope = store, scope

    def execute(self, request):
        from cj_cleanup.core import Denied
        from cj_cleanup.store import original_result, record_result, require_intent
        if (request.subject_digest != self.store.subject_digest or request.domain_scope != self.scope
                or request.selection.kind != 'account'):
            raise Denied('service staff audit cleanup unavailable')
        with self.store.transaction(request.operation_id) as cur:
            old = original_result(cur, request)
            if old is not None:
                return old
            require_intent(cur, request)
            cur.execute("SELECT set_config('cj.cleanup_scope',%s,true),set_config('cj.cleanup_purpose','account',true)",
                        (self.scope,))
            cur.execute(DELINK, (self.scope,))
            if cur.execute(LINKED, (self.scope,)).fetchone() is not None:
                raise Denied('service staff audit cleanup unconfirmed')
            return record_result(cur, request, 'confirmed')

    def reconcile(self, request):
        from cj_cleanup.store import original_result, receipt_for
        with self.store.transaction(request.operation_id, writing=False) as cur:
            value = original_result(cur, request)
        return value if value is not None else receipt_for(request, 'unknown')
