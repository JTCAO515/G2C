"""Candidate C item hooks; explicit immutable-intent binding, no account wipe."""
import json
from cj_cleanup.core import Denied
from cj_cleanup.postgres import CommitUnknown
from cj_cleanup.store import original_result,require_intent,record_result,receipt_for
from cj_agent.draft import trip_scope_for
from .association_reader import AssociationReader


class _ItemHook:
    target=None
    trip=False
    def __init__(self,store,memory_scope):
        self.store,self.memory_scope=store,memory_scope
        self.domain_scope=trip_scope_for(memory_scope) if self.trip else memory_scope
        self.reader=AssociationReader(store,memory_scope)

    def execute(self,request):
        if (request.protocol!='CLEANUP@1.1' or request.target!=self.target or request.selection.kind!='memory'
                or request.subject_digest!=self.store.subject_digest or request.domain_scope!=self.domain_scope):
            raise Denied('original item cleanup domain unavailable')
        try:
            with self.store.transaction(request.operation_id) as cursor:
                old=original_result(cursor,request)
                if old is not None:return old
                require_intent(cursor,request)
                association=json.loads(self.reader.read_original(request))
                cursor.execute("SELECT set_config('cj.cleanup_scope',%s,true),set_config('cj.cleanup_purpose','memory',true)",(self.domain_scope,))
                table='cj_trip_scope' if self.trip else 'cj_memory_scope'
                cursor.execute(f'SELECT scope FROM {table} WHERE scope=%s FOR UPDATE',(self.domain_scope,))
                if cursor.fetchone() is None:raise Denied('canonical item cleanup lock unavailable')
                self.erase(cursor,request,association)
                return record_result(cursor,request,'confirmed')
        except CommitUnknown:return receipt_for(request,'unknown')

    def reconcile(self,request):
        if (request.protocol!='CLEANUP@1.1' or request.selection.kind!='memory' or request.target!=self.target
                or request.subject_digest!=self.store.subject_digest or request.domain_scope!=self.domain_scope):
            raise Denied('original item cleanup domain unavailable')
        with self.store.transaction(request.operation_id,writing=False) as cursor:result=original_result(cursor,request)
        return result if result is not None else receipt_for(request,'unknown')


class DerivedItemHook(_ItemHook):
    target='memory-derived'
    def erase(self,cursor,request,association):
        scope=self.memory_scope;iid=association['selection']['item_id'];sources=[r['source_id'] for r in association['source_refs']]
        cursor.execute('DELETE FROM cj_memory_history_candidate_action WHERE scope=%s AND candidate_id=%s',(scope,iid))
        cursor.execute('DELETE FROM cj_memory_history_origin WHERE scope=%s AND (item_id=%s OR source_id=ANY(%s))',(scope,iid,sources))
        for ref in association['job_refs']:
            cursor.execute("DELETE FROM cj_memory_history_job WHERE scope=%s AND job_id=%s AND attempt_id=%s AND encode(sha256(original_input),'hex')=%s",
                           (scope,ref['job_id'],ref['attempt_id'],ref['original_input_sha256']))
            cursor.execute('SELECT 1 FROM cj_memory_history_job WHERE scope=%s AND job_id=%s',(scope,ref['job_id']))
            if cursor.fetchone() is not None:raise Denied('original copied job retained')
        cursor.execute('SELECT 1 FROM cj_memory_history_origin WHERE scope=%s AND (item_id=%s OR source_id=ANY(%s)) LIMIT 1',(scope,iid,sources))
        if cursor.fetchone() is not None:raise Denied('selected origin retained')
        # Hash-only processing cursors remain as replay prevention. No source
        # text, candidate, model input/output or job bytes remain in those rows.


class ManagementItemHook(_ItemHook):
    target='business/memory-management-actions'
    def erase(self,cursor,request,association):
        cursor.execute('DELETE FROM cj_memory_management_action WHERE scope=%s AND item_id=%s',
                       (self.memory_scope,association['selection']['item_id']))
        cursor.execute('SELECT 1 FROM cj_memory_management_action WHERE scope=%s AND item_id=%s LIMIT 1',
                       (self.memory_scope,association['selection']['item_id']))
        if cursor.fetchone() is not None:raise Denied('selected management action retained')


class AuthorityItemHook(_ItemHook):
    target='business/memory-authoritative'
    def erase(self,cursor,request,association):
        progress=self.store.query(request.operation_id)
        if progress['status']=='blocked' or any(s['state']!='confirmed' for s in progress['steps']
                if s['target'] not in (self.target,'business/cleanup-metadata')):
            raise Denied('earlier original erasure domains unconfirmed')
        scope=self.memory_scope;selection=association['selection'];iid=selection['item_id']
        cursor.execute('SELECT status,version FROM cj_memory_item WHERE scope=%s AND item_id=%s',(scope,iid))
        if cursor.fetchone()!=('withdrawn',selection['item_version']):raise Denied('original stopped item unavailable')
        sources=[r['source_id'] for r in association['source_refs']]
        cursor.execute('DELETE FROM cj_memory_operation WHERE scope=%s AND item_id=%s',(scope,iid))
        cursor.execute('DELETE FROM cj_memory_item WHERE scope=%s AND item_id=%s',(scope,iid))
        cursor.execute('DELETE FROM cj_memory_source WHERE scope=%s AND source_id=ANY(%s)',(scope,sources))
        cursor.execute('DELETE FROM cj_memory_erasure_manifest WHERE scope=%s AND operation_id=%s',(scope,request.operation_id))
        cursor.execute('''SELECT 1 FROM cj_memory_item WHERE scope=%s AND item_id=%s
            UNION ALL SELECT 1 FROM cj_memory_source WHERE scope=%s AND source_id=ANY(%s)
            UNION ALL SELECT 1 FROM cj_memory_operation WHERE scope=%s AND item_id=%s
            UNION ALL SELECT 1 FROM cj_memory_erasure_manifest WHERE scope=%s AND operation_id=%s LIMIT 1''',
            (scope,iid,scope,sources,scope,iid,scope,request.operation_id))
        if cursor.fetchone() is not None:raise Denied('selected authoritative bytes retained')


class TripDerivedItemHook(_ItemHook):
    target='business/trip-authoritative';trip=True
    def erase(self,cursor,request,association):
        scope=self.domain_scope
        # M30 has no item FK. This is explicitly the owned derived scope, not
        # precise item deletion; accepted formal authority is retained.
        cursor.execute('DELETE FROM cj_trip_scoped_result WHERE scope=%s',(scope,))
        cursor.execute("SELECT proposal_id FROM cj_trip_proposal WHERE scope=%s AND status<>'accepted'",(scope,))
        proposals=[r[0] for r in cursor.fetchall()]
        for table in ('cj_trip_scoped_action','cj_trip_needs_edit','cj_trip_manual_intent','cj_trip_needs_action',
                      'cj_trip_needs_plan_context','cj_trip_scoped_basis','cj_trip_manual_basis','cj_trip_needs_basis','cj_trip_receipt'):
            cursor.execute(f'DELETE FROM {table} WHERE scope=%s AND proposal_id=ANY(%s)',(scope,proposals))
        cursor.execute('DELETE FROM cj_trip_proposal WHERE scope=%s AND proposal_id=ANY(%s)',(scope,proposals))


class _PurposeHook:
    """New explicit factory; the old account-only factory remains separate."""
    def __init__(self,account,memory):self.account,self.memory=account,memory
    def execute(self,request):
        if request.selection.kind=='account':return self.account.execute(request)
        return self.memory.execute(request)
    def reconcile(self,request):
        if request.selection.kind=='account':return self.account.reconcile(request)
        return self.memory.reconcile(request)


def erasure_hooks(store,memory_scope):
    from .account_cleanup import account_hooks
    from cj_memory_jobs.cleanup import CleanupHook
    account=account_hooks(store,memory_scope);account['memory-derived']=CleanupHook(store,memory_scope)
    return {cls.target:_PurposeHook(account[cls.target],cls(store,memory_scope)) for cls in (
        DerivedItemHook,ManagementItemHook,TripDerivedItemHook,AuthorityItemHook)}
