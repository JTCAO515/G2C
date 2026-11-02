"""C-owned account-only erasure over B's original intent/retirement/result seam.

Not registered until same-PR permissions, physical/race checks and registry land.
Memory selection is intentionally failed here; #26 has a separate item pipeline.
"""
from cj_cleanup.core import Denied
from cj_cleanup.postgres import CommitUnknown
from cj_cleanup.store import (original_result,require_intent,require_account_retirement,
                              record_result,receipt_for)
from cj_agent.draft import trip_scope_for


class _AccountHook:
    target=None
    scope_table=None
    content_tables=()

    def __init__(self,store,domain_scope):self.store,self.domain_scope=store,domain_scope

    def _binding(self,request):
        if (request.protocol!='CLEANUP@1.1' or request.target!=self.target
                or request.subject_digest!=self.store.subject_digest or request.domain_scope!=self.domain_scope):
            raise Denied('original C account domain unavailable')

    def execute(self,request):
        self._binding(request)
        try:
            with self.store.transaction(request.operation_id) as cursor:
                old=original_result(cursor,request)
                if old is not None:return old
                require_intent(cursor,request)
                if request.selection.kind!='account':return record_result(cursor,request,'failed')
                require_account_retirement(cursor,request)
                cursor.execute("SELECT set_config('cj.cleanup_scope',%s,true),set_config('cj.cleanup_purpose','account',true)",
                               (self.domain_scope,))
                # Drain even a not-yet-visible first scope INSERT before the
                # canonical row lock/physical audit. Bootstrap uses shared locks.
                cursor.execute('SELECT pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(%s,0))',
                               ('cj-c-account-scope:'+self.scope_table+':'+self.domain_scope,))
                # The same canonical scope row precedes every C write. The
                # cleanup role's local column grant permits locking, not rename.
                cursor.execute(f'SELECT scope FROM {self.scope_table} WHERE scope=%s FOR UPDATE',(self.domain_scope,))
                locked=cursor.fetchone()
                if locked is None:
                    cursor.execute(f'SELECT scope FROM {self.scope_table} WHERE scope=%s',(self.domain_scope,))
                    if cursor.fetchone() is not None:raise Denied('C canonical cleanup lock unavailable')
                for table in self.content_tables:
                    # Code-owned identifiers, never registry/client SQL.
                    cursor.execute(f'DELETE FROM {table} WHERE scope=%s',(self.domain_scope,))
                for table in self.content_tables:
                    cursor.execute(f'SELECT 1 FROM {table} WHERE scope=%s LIMIT 1',(self.domain_scope,))
                    if cursor.fetchone() is not None:raise Denied('C physical erasure incomplete')
                result=record_result(cursor,request,'confirmed')
            return result
        except CommitUnknown:return receipt_for(request,'unknown')

    def reconcile(self,request):
        self._binding(request)
        with self.store.transaction(request.operation_id,writing=False) as cursor:
            result=original_result(cursor,request)
        return result if result is not None else receipt_for(request,'unknown')


class MemoryManagementAccountHook(_AccountHook):
    target='business/memory-management-actions'
    scope_table='cj_memory_scope'
    content_tables=('cj_memory_management_action',)


class MemoryAuthorityAccountHook(_AccountHook):
    target='business/memory-authoritative'
    scope_table='cj_memory_scope'
    content_tables=('cj_memory_operation','cj_memory_item','cj_memory_source','cj_memory_scope')


class TripAuthorityAccountHook(_AccountHook):
    target='business/trip-authoritative'
    scope_table='cj_trip_scope'
    content_tables=('cj_trip_scoped_action','cj_trip_scoped_result','cj_trip_scoped_basis',
        'cj_trip_needs_edit','cj_trip_needs_plan_context','cj_trip_needs_current','cj_trip_needs_action',
        'cj_trip_needs_basis','cj_trip_manual_intent','cj_trip_manual_basis',
        'cj_trip_receipt','cj_trip_record','cj_trip_proposal','cj_trip_scope')


def account_hooks(store,owner_scope):
    """Explicit local Runtime.extra_hooks binding from its captured own principal."""
    return {'business/memory-management-actions':MemoryManagementAccountHook(store,owner_scope),
            'business/memory-authoritative':MemoryAuthorityAccountHook(store,owner_scope),
            'business/trip-authoritative':TripAuthorityAccountHook(store,trip_scope_for(owner_scope))}
