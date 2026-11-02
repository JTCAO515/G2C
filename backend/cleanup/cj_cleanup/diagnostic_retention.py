"""RUN-DIAGNOSTIC-RETENTION@1. Clock-injected 90-day metadata-only erasure."""
from .core import Denied
from .store import require_intent,original_result,record_result,receipt_for

SECONDS=90*86400


class DiagnosticHook:
    def __init__(self,store,scope,clock):self.store,self.scope,self.clock=store,scope,clock

    def execute(self,request):
        if (request.subject_digest!=self.store.subject_digest or request.domain_scope!=self.scope
                or request.selection.kind!='diagnostics'
                or request.selection.before_unix!=int(self.clock())-SECONDS):
            raise Denied('approved diagnostic cutoff required')
        with self.store.transaction(request.operation_id) as cur:
            old=original_result(cur,request)
            if old is not None:return old
            require_intent(cur,request)
            cur.execute("SELECT set_config('cj.cleanup_scope',%s,true),set_config('cj.cleanup_purpose','diagnostics',true)",(self.scope,))
            cur.execute('UPDATE cj_run_event SET diagnostic_at=NULL WHERE scope=%s AND diagnostic_at<to_timestamp(%s)',
                        (self.scope,request.selection.before_unix))
            if cur.execute('SELECT 1 FROM cj_run_event WHERE scope=%s AND diagnostic_at<to_timestamp(%s) LIMIT 1',
                           (self.scope,request.selection.before_unix)).fetchone() is not None:
                raise Denied('diagnostic retention incomplete')
            result=record_result(cur,request,'confirmed')
        return result

    def reconcile(self,request):
        with self.store.transaction(request.operation_id,writing=False) as cur:result=original_result(cur,request)
        return result if result is not None else receipt_for(request,'unknown')
