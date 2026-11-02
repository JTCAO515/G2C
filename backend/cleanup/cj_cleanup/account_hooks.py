"""B-owned CLEANUP@1.1 physical account hooks, explicit tables and trusted scopes."""
from .core import Denied
from .store import require_intent,require_account_retirement,original_result,record_result,receipt_for
from cj_usage.codec import decode

MESSAGE=(
 ('cj_message_edit_result_profile','scope'),('cj_message_edit_reference','scope'),('cj_message_edit_profile','scope'),
 ('cj_message_trip_reference','scope'),('cj_message_trip_profile','scope'),('cj_message_travel_reference','scope'),
 ('cj_message_context_profile','scope'),('cj_message_metered_requirement','scope'),
 ('cj_message_needs_binding','message_scope'),('cj_message_needs_selection','message_scope'),
 ('cj_local_run_requirement','scope'),('cj_message_delivery','scope'),('cj_message_draft','scope'),
 ('cj_message_receipt','scope'),('cj_travel_context','scope'),('cj_travel_context_action','scope'),
 ('cj_local_metered_profile','scope'),('cj_local_run_protection','scope'),('cj_message_chat','scope'),('cj_message_scope','scope'))
RUN=(('cj_run_background_job','scope'),('cj_run_metered_operation','scope'),('cj_run_metered_binding','scope'),('cj_run_step_usage','scope'),
     ('cj_run_event','scope'),('cj_run_record','scope'),('cj_run_scope','scope'))
NEEDS=(('cj_needs_revision','scope'),('cj_needs_record','scope'),('cj_needs_scope','scope'))


class DomainHook:
    def __init__(self,store,scope,tables):self.store,self.scope,self.tables=store,scope,tables

    def execute(self,request):
        if request.subject_digest!=self.store.subject_digest or request.domain_scope!=self.scope or request.selection.kind!='account':
            raise Denied('original account domain unavailable')
        with self.store.transaction(request.operation_id) as cur:
            old=original_result(cur,request)
            if old is not None:return old
            require_intent(cur,request)
            require_account_retirement(cur,request)
            cur.execute("SELECT set_config('cj.cleanup_scope',%s,true),set_config('cj.cleanup_purpose','account',true)",(self.scope,))
            for table,column in self.tables:
                # Explicit code-owned identifiers; never registry/request paths or SQL.
                cur.execute(f'DELETE FROM {table} WHERE {column}=%s',(self.scope,))
            for table,column in self.tables:
                if cur.execute(f'SELECT 1 FROM {table} WHERE {column}=%s LIMIT 1',(self.scope,)).fetchone() is not None:
                    raise Denied('physical domain cleanup unconfirmed')
            result=record_result(cur,request,'confirmed')
        return result

    def reconcile(self,request):
        with self.store.transaction(request.operation_id,writing=False) as cur:result=original_result(cur,request)
        return result if result is not None else receipt_for(request,'unknown')


class UsageHook:
    """Approved exact owner ledger scopes, captured before RUN bindings are erased."""
    def __init__(self,store,owner_scope,ledger_scopes):self.store,self.scope,self.ledger_scopes=store,owner_scope,tuple(ledger_scopes)

    def _scopes(self,cur):
        cur.execute("SELECT set_config('cj.cleanup_owner_scope',%s,true),set_config('cj.cleanup_purpose','account',true)",(self.scope,))
        cur.execute('SELECT scope_id FROM cj_usage_ledger_candidate WHERE public.cj_cleanup_usage_owner(scope_id,ledger) ORDER BY scope_id')
        return tuple(sorted(set(self.ledger_scopes)|{row[0] for row in cur.fetchall()}))

    def require_settled(self,operation_id):
        with self.store.transaction(operation_id,writing=False) as cur:
            cur.execute("SELECT set_config('cj.cleanup_purpose','account',true)")
            for scope in self._scopes(cur):
                cur.execute("SELECT set_config('cj.cleanup_scope',%s,true)",(scope,))
                cur.execute('SELECT format_version,ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(scope,))
                row=cur.fetchone()
                if row is None:continue
                if row[0]!=1:raise Denied('original usage format unresolved')
                ledger=decode(row[1])
                if any(a.state=='unknown' and a.receipt is None for a in ledger.attempts.values()):
                    raise Denied('original usage outcome unresolved')

    def execute(self,request):
        if request.subject_digest!=self.store.subject_digest or request.domain_scope!=self.scope or request.selection.kind!='account':
            raise Denied('original usage scope unavailable')
        self.require_settled(request.operation_id)
        with self.store.transaction(request.operation_id) as cur:
            old=original_result(cur,request)
            if old is not None:return old
            require_intent(cur,request)
            require_account_retirement(cur,request)
            cur.execute("SELECT set_config('cj.cleanup_purpose','account',true)")
            for scope in self._scopes(cur):
                cur.execute("SELECT set_config('cj.cleanup_scope',%s,true)",(scope,))
                cur.execute('DELETE FROM cj_usage_ledger_candidate WHERE scope_id=%s',(scope,))
                if cur.execute('SELECT 1 FROM cj_usage_ledger_candidate WHERE scope_id=%s',(scope,)).fetchone() is not None:
                    raise Denied('usage physical cleanup unconfirmed')
            result=record_result(cur,request,'confirmed')
        return result

    def reconcile(self,request):
        with self.store.transaction(request.operation_id,writing=False) as cur:result=original_result(cur,request)
        return result if result is not None else receipt_for(request,'unknown')
