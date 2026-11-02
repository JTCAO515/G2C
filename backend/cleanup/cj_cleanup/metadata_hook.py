"""CLEANUP@1.0 own metadata erasure; minimal opaque progress and fences remain."""
from .core import Denied, digest
from .hooks import make_receipt
from .store import original_result, record_result


class MetadataHook:
    def __init__(self,store,legacy_scope_bytes):
        if digest(legacy_scope_bytes)!=store.subject_digest:
            raise Denied('cleanup subject mismatch')
        self.store,self.legacy_scope_bytes=store,legacy_scope_bytes

    def execute(self,request):
        if request.subject_digest!=self.store.subject_digest or request.domain_scope!=self.store.subject_digest or request.selection.kind!='account':
            raise Denied('cleanup metadata unavailable')
        with self.store.transaction(request.operation_id) as cur:
            old=original_result(cur,request)
            if old is not None:return old
            _,manifest,blocked,_=self.store._load(cur,request.operation_id,lock=True)
            cur.execute('SELECT target,state FROM cj_cleanup_step WHERE subject_digest=%s AND operation_id=%s',
                        (self.store.subject_digest,request.operation_id))
            states=dict(cur.fetchall())
            if blocked or any(states.get(t)!='confirmed' for t in manifest.inventory if t!=request.target):
                raise Denied('cleanup metadata awaits original results')
            cur.execute("SELECT set_config('cj.cleanup_scope_hex',%s,true),set_config('cj.cleanup_purpose','account',true)",
                        (self.legacy_scope_bytes.hex(),))
            cur.execute('DELETE FROM cj_cleanup_journal_candidate WHERE scope_bytes=%s',(self.legacy_scope_bytes,))
            # Clear every original scope/selection/request in this account, not the
            # bounded digests/outcomes needed to reconcile or deny resurrection.
            cur.execute('UPDATE cj_cleanup_operation SET plan_bytes=NULL WHERE subject_digest=%s',(self.store.subject_digest,))
            cur.execute('UPDATE cj_cleanup_step SET request_bytes=NULL WHERE subject_digest=%s',(self.store.subject_digest,))
            result=record_result(cur,request,'confirmed')
        return result

    def reconcile(self,request):
        with self.store.transaction(request.operation_id,writing=False) as cur:
            value=original_result(cur,request)
        return value if value is not None else make_receipt(request,'unknown')
