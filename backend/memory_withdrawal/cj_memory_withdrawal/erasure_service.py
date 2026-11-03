"""Explicit item erasure: current user confirmation, original cleanup, no account wipe."""
from hashlib import sha256
import json

from cj_cleanup.core import Denied,digest
from cj_cleanup.coordinator import Coordinator
from cj_cleanup.hooks_v1_1 import Selection
from cj_agent.draft import trip_scope_for
from cj_memory.domain import Conflict,Unavailable,CommitUnknown
from cj_memory.erasure_fence import require_coverage
from cj_memory.runtime import RuntimeDenied
from cj_message.domain import Unavailable as MessageUnavailable
from cj_memory_jobs.postgres import encode
from cj_memory_jobs.service import OperationWithheld
from cj_api.local_account_admission_v2 import subject_digest
from .erasure_command import ErasureCommand
from .erasure_store import freeze,reference_digest
from .association_reader import AssociationReader
from .item_cleanup import erasure_hooks

BACKEND_TARGETS=('business/message','checkpoints/run','business/usage')
ORDER=('business/message','checkpoints/run','business/usage','memory-derived','business/memory-management-actions',
       'business/trip-authoritative','business/memory-authoritative','business/cleanup-metadata')


class ErasureService:
    def __init__(self,collection,cleanup_runtime,resolve_backend_hooks,*,max_sources,max_jobs,max_association_bytes):
        if resolve_backend_hooks is None:raise ValueError('explicit B memory-purpose hooks required; account hooks are not substitutes')
        self.collection,self.runtime,self.resolve_backend_hooks=collection,cleanup_runtime,resolve_backend_hooks
        self.max_sources,self.max_jobs,self.max_bytes=max_sources,max_jobs,max_association_bytes

    def _record(self,context,token,command,*,write):
        c=self.collection;repository,principal,guard=c._binding(context,token)
        scope=repository.scope;sd=sha256(scope.encode()).hexdigest()
        possible=[False]
        def record(headers):
            with repository.transaction() as memory:
                memory.lock_scope();cur=memory.cur
                cur.execute('''SELECT operation_id,item_version,scope_epoch,original_input_sha256
                    FROM cj_memory_erasure_fence WHERE scope_digest=%s AND kind='action' AND reference_sha256=%s''',
                    (sd,reference_digest('action',command.action_id)))
                fence=cur.fetchone()
                if fence is not None:
                    if fence[3]!=sha256(command.raw).hexdigest():raise Conflict('original delete action bytes differ')
                    operation,version,epoch,_=fence
                    cur.execute('SELECT association,association_sha256 FROM cj_memory_erasure_manifest WHERE scope=%s AND operation_id=%s',(scope,operation))
                    row=cur.fetchone()
                    if row is not None:
                        raw=bytes(row[0])
                        if sha256(raw).hexdigest()!=row[1]:raise Unavailable('immutable delete association corrupt')
                        association=json.loads(raw)
                    else:association=None
                elif write:
                    raw=freeze(memory,command,subject_digest(principal),max_sources=self.max_sources,max_jobs=self.max_jobs,max_bytes=self.max_bytes,headers=headers)
                    association=json.loads(raw);operation=association['operation_id'];version=association['selection']['item_version'];epoch=association['selection']['scope_epoch']
                else:raise Unavailable('original delete outcome unknown; absence does not permit resubmission')
                try:require_coverage(cur,scope,operation,version,epoch,encode(association) if association is not None else None)
                except RuntimeDenied as error:raise Unavailable('original complete history capture unavailable') from error
                possible[0]=write
                guard('item_erasure_record')
            return repository,principal,guard,operation,version,epoch,association
        if not write:return record(None)
        # Recovery of an already frozen original must not depend on later
        # unrelated MESSAGE inventory or capture new post-delete references.
        with repository.transaction() as memory:
            memory.lock_scope()
            memory.cur.execute("SELECT 1 FROM cj_memory_erasure_fence WHERE scope_digest=%s AND kind='action' AND reference_sha256=%s",
                (sd,reference_digest('action',command.action_id)))
            existing=memory.cur.fetchone() is not None
        if existing:return record(None)
        try:
            result={}
            def capture(headers):
                value=record(headers);result['record']=value
                return encode(value[-1]) if value[-1] is not None else b'null'
            context.with_erasure_headers(capture,max_refs=10000,max_result_bytes=self.max_bytes)
            return result['record']
        except Exception as error:
            if possible[0]:raise OperationWithheld(command.action_id) from error
            if isinstance(error,MessageUnavailable):raise Unavailable('original message metadata unavailable') from error
            raise

    def _binding(self,principal,scope):
        binding=self.runtime.bind(principal)
        if binding.owner_scope!=scope:raise Unavailable('item cleanup owner differs')
        hooks=erasure_hooks(binding.store,scope)
        backend=self.resolve_backend_hooks(binding.store,scope,AssociationReader(binding.store,scope))
        if set(backend)!=set(BACKEND_TARGETS):raise Unavailable('complete explicit B item hook inventory required')
        hooks.update(backend);hooks['business/cleanup-metadata']=binding.hooks['business/cleanup-metadata']
        return binding.store,hooks

    def delete(self,token,original,*,request_id=None):
        command=ErasureCommand.parse(original);possible=False
        def apply(context):
            nonlocal possible
            # Validate composition before installing a partial new user intent.
            repo,principal,_=self.collection._binding(context,token)
            store,hooks=self._binding(principal,repo.scope)
            repo,principal,guard,operation,version,epoch,association=self._record(context,token,command,write=True)
            possible=True
            coordinator=Coordinator(store,self.runtime.registry,hooks)
            selection=Selection('memory',command.item_id,version,epoch)
            plan={target:dict(domain_scope=trip_scope_for(repo.scope) if target=='business/trip-authoritative' else
                store.subject_digest if target=='business/cleanup-metadata' else repo.scope,selection=selection.to_dict()) for target in ORDER}
            if association is not None:
                coordinator.create(operation,digest(original),'memory',plan)
            self._clean(store,repo.scope,coordinator,operation,plan,selection,association,guard)
            progress=coordinator.query(operation);guard('item_erasure_final_projection')
            return encode(dict(action_id=command.action_id,operation_id=operation,item_id=command.item_id,
                item_version=version,scope_epoch=epoch,stop_use='stopped',online_status=progress['status'],steps=progress['steps'],
                derived_range='owned_trip_derived_scope',precise_item_match=False,
                retained=['original_chat','accepted_formal_trip','minimum_hashed_barriers'],
                limits=['already_sent_model_requests','already_displayed_history','external_provider_retention']))
        try:return self.collection._invoke(token,apply,request_id,'MEMORY-ERASURE-response@1')
        except CommitUnknown as error:raise OperationWithheld(command.action_id) from error
        except Exception as error:
            if possible:raise OperationWithheld(command.action_id) from error
            raise

    @staticmethod
    def _advance_targets(coordinator,operation,plan,selection,association,targets):
        for target in targets:
            progress=coordinator.query(operation)
            if progress['status'] in ('blocked','failed'):return False
            state=next(s['state'] for s in progress['steps'] if s['target']==target)
            if state=='confirmed':continue
            request=coordinator.request(operation,target,plan[target]['domain_scope'],selection)
            if state=='pending':
                if association is None and target!='business/cleanup-metadata':
                    raise Unavailable('original association gone before all domains confirmed')
                coordinator.advance(request)
            else:coordinator.reconcile(request)
            updated=coordinator.query(operation)
            if next(s['state'] for s in updated['steps'] if s['target']==target)!='confirmed':return False
        return True

    def _clean(self,store,scope,coordinator,operation,plan,selection,association,guard):
        self._advance_targets(coordinator,operation,plan,selection,association,ORDER)

    def query(self,token,original,*,request_id=None):
        """Exact original command required; safe read never dispatches/recreates."""
        command=ErasureCommand.parse(original)
        def read(context):
            repo,principal,guard,operation,version,epoch,_=self._record(context,token,command,write=False)
            store,_=self._binding(principal,repo.scope)
            try:progress=store.query(operation)
            except Denied:progress=dict(status='unknown',steps=[])
            guard('item_erasure_query')
            return encode(dict(action_id=command.action_id,operation_id=operation,item_id=command.item_id,
                item_version=version,scope_epoch=epoch,stop_use='stopped',online_status=progress['status'],steps=progress['steps']))
        return self.collection._invoke(token,read,request_id,'MEMORY-ERASURE-response@1')

    def progress(self,token,action_id,*,request_id=None):
        from cj_memory_jobs.codec import pg_identity
        pg_identity(action_id,16384)
        def read(context):
            repo,principal,guard=self.collection._binding(context,token)
            with repo.transaction() as memory:
                memory.lock_scope();memory.cur.execute('''SELECT operation_id,item_version,scope_epoch FROM cj_memory_erasure_fence
                    WHERE scope_digest=%s AND kind='action' AND reference_sha256=%s''',
                    (sha256(repo.scope.encode()).hexdigest(),reference_digest('action',action_id)))
                record=memory.cur.fetchone()
                if record is None:raise Unavailable('original delete outcome unknown')
            operation,version,epoch=record;store,_=self._binding(principal,repo.scope)
            with repo.transaction() as memory:
                try:require_coverage(memory.cur,repo.scope,operation,version,epoch)
                except RuntimeDenied as error:raise Unavailable('original complete history capture unavailable') from error
            try:progress=store.query(operation)
            except Denied:progress=dict(status='unknown',steps=[])
            guard('item_erasure_progress_projection')
            return encode(dict(action_id=action_id,operation_id=operation,item_version=version,scope_epoch=epoch,
                               stop_use='stopped',online_status=progress['status'],steps=progress['steps']))
        return self.collection._invoke(token,read,request_id,'MEMORY-ERASURE-response@1')
