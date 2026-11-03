"""Candidate original-intent reader; not installed or frozen for B consumption."""
from hashlib import sha256
from cj_cleanup.core import Denied
from cj_cleanup.store import require_intent
from cj_agent.draft import trip_scope_for
from cj_memory.domain import strict_object,InvalidInput

TARGETS=('business/message','checkpoints/run','business/usage','memory-derived',
         'business/memory-management-actions','business/memory-authoritative','business/trip-authoritative')


class AssociationReader:
    def __init__(self,store,memory_scope):self.store,self.memory_scope=store,memory_scope

    def read_original(self,request):
        expected=trip_scope_for(self.memory_scope) if request.target=='business/trip-authoritative' else self.memory_scope
        if (request.protocol!='CLEANUP@1.1' or request.target not in TARGETS or request.selection.kind!='memory'
                or request.subject_digest!=self.store.subject_digest or request.domain_scope!=expected):
            raise Denied('original item-erasure reader unavailable')
        with self.store.transaction(request.operation_id,writing=False) as cursor:
            # The public helper is read-only; it never creates/retries an intent.
            require_intent(cursor,request)
            cursor.execute("SELECT set_config('cj.cleanup_scope',%s,true),set_config('cj.cleanup_purpose','memory',true)",(self.memory_scope,))
            cursor.execute('SELECT association,association_sha256 FROM cj_memory_erasure_manifest WHERE scope=%s AND operation_id=%s',
                           (self.memory_scope,request.operation_id))
            row=cursor.fetchone()
            if row is None:raise Denied('original immutable association absent; no reconstruction grant')
            raw=bytes(row[0])
            if not 0<len(raw)<=1_000_000 or sha256(raw).hexdigest()!=row[1]:raise Denied('original immutable association corrupt')
            try:value=strict_object(raw)
            except (InvalidInput,RecursionError) as error:raise Denied('original immutable association invalid') from error
            if (type(value) is not dict or value.get('version')!='MEMORY-ERASURE-ASSOCIATION-DRAFT@2'
                    or value.get('operation_id')!=request.operation_id or value.get('subject_digest')!=request.subject_digest
                    or value.get('memory_scope_digest')!=sha256(self.memory_scope.encode()).hexdigest()
                    or value.get('selection')!=request.selection.to_dict()):
                raise Denied('original immutable association differs from approved selection')
            return raw
