"""CLEANUP@1.0 own metadata erasure; minimal opaque progress and fences remain."""
from .core import Denied, digest
from .store import original_result, record_result, receipt_for, require_intent


class MetadataHook:
    def __init__(self,store,legacy_scope_bytes,*,additional_erasure=None):
        if digest(legacy_scope_bytes)!=store.subject_digest:
            raise Denied('cleanup subject mismatch')
        self.store,self.legacy_scope_bytes=store,legacy_scope_bytes
        self.additional_erasure=additional_erasure

    def execute(self,request):
        if request.subject_digest!=self.store.subject_digest or request.domain_scope!=self.store.subject_digest:
            raise Denied('cleanup metadata unavailable')
        with self.store.transaction(request.operation_id) as cur:
            _,manifest,blocked,_,targets=self.store._load(cur,request.operation_id,lock=True)
            old=original_result(cur,request)
            if old is not None:return old
            require_intent(cur,request)
            cur.execute('SELECT target,state FROM cj_cleanup_step WHERE subject_digest=%s AND operation_id=%s',
                        (self.store.subject_digest,request.operation_id))
            states=dict(cur.fetchall())
            if blocked or any(states.get(t)!='confirmed' for t in targets if t!=request.target):
                raise Denied('cleanup metadata awaits original results')
            if request.selection.kind=='account':
                cur.execute("SELECT set_config('cj.cleanup_scope_hex',%s,true),set_config('cj.cleanup_purpose','account',true)",
                            (self.legacy_scope_bytes.hex(),))
                cur.execute('DELETE FROM cj_cleanup_journal_candidate WHERE scope_bytes=%s',(self.legacy_scope_bytes,))
            # Clear every original scope/selection/request in this account, not the
            # bounded digests/outcomes needed to reconcile or deny resurrection.
            condition='' if request.selection.kind=='account' else ' AND operation_id=%s'
            args=(self.store.subject_digest,) if request.selection.kind=='account' else (self.store.subject_digest,request.operation_id)
            cur.execute('UPDATE cj_cleanup_operation SET plan_bytes=NULL WHERE subject_digest=%s'+condition,args)
            cur.execute('UPDATE cj_cleanup_step SET request_bytes=NULL WHERE subject_digest=%s'+condition,args)
            if self.additional_erasure is not None:self.additional_erasure(cur,request)
            result=record_result(cur,request,'confirmed')
        return result

    def reconcile(self,request):
        with self.store.transaction(request.operation_id,writing=False) as cur:
            value=original_result(cur,request)
        return value if value is not None else receipt_for(request,'unknown')
