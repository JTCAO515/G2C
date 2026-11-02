"""CLEANUP@1.1 for the PG history queue; no cleanup role in the producer path."""
from hashlib import sha256
from cj_cleanup.core import Denied
from cj_cleanup.postgres import CommitUnknown
from cj_cleanup.store import original_result, record_result, receipt_for


TARGET = 'memory-derived'
CONTENT_TABLES = ('cj_memory_history_candidate_action','cj_memory_history_origin',
                  'cj_memory_history_job','cj_memory_history_cursor',
                  'cj_memory_history_action','cj_memory_history_consent')


class CleanupHook:
    content_tables=CONTENT_TABLES
    def __init__(self, store, domain_scope):
        self.store, self.domain_scope = store, domain_scope

    def _binding(self, request):
        if (request.subject_digest != self.store.subject_digest
                or request.domain_scope != self.domain_scope or request.target != TARGET
                or request.protocol != 'CLEANUP@1.1'):
            raise Denied('history cleanup unavailable')

    def execute(self, request):
        self._binding(request)
        try:
            with self.store.transaction(request.operation_id) as cur:
                old = original_result(cur,request)
                if old is not None:
                    return old
                # #402 owns this public check; missing support remains closed.
                from cj_cleanup.store import require_intent
                require_intent(cur,request)
                if request.selection.kind != 'account':
                    # Item/source mapping is supplied with #410/#26. No guessed
                    # association or account-wide deletion for one Memory item.
                    return record_result(cur,request,'failed')
                cur.execute("SELECT set_config('cj.cleanup_scope',%s,true),"
                            "set_config('cj.cleanup_purpose','account',true)",(self.domain_scope,))
                cur.execute('SELECT scope FROM cj_memory_scope WHERE scope=%s FOR UPDATE',
                            (self.domain_scope,))
                scope_digest=sha256(self.domain_scope.encode('utf-8')).hexdigest()
                cur.execute('INSERT INTO cj_memory_history_fence(scope_digest,erased) VALUES(%s,true) '
                            'ON CONFLICT(scope_digest) DO UPDATE SET erased=true',(scope_digest,))
                for table in self.content_tables:
                    # Code-owned identifiers only; no request/registry table selection.
                    cur.execute(f'DELETE FROM {table} WHERE scope=%s',(self.domain_scope,))
                    cur.execute(f'SELECT count(*) FROM {table} WHERE scope=%s',(self.domain_scope,))
                    if cur.fetchone() != (0,):
                        raise Denied('history cleanup incomplete')
                return record_result(cur,request,'confirmed')
        except CommitUnknown:
            return receipt_for(request,'unknown')

    def reconcile(self, request):
        self._binding(request)
        with self.store.transaction(request.operation_id,writing=False) as cur:
            result = original_result(cur,request)
        return result if result is not None else receipt_for(request,'unknown')
