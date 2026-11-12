"""Native preference/Remember/STOP-USE setup, never administrator seed data.

The one preparatory MESSAGE belongs to the root setup operation. Its original
RUN inventory therefore includes every preparatory model/Memory call. Choices
and STOP-USE use existing native zero-model actions and retained original inputs.
"""
from datetime import datetime,timezone

from cj_message.demo_dialogue import LIO_VERSION_V2
from cj_message.auth_boundary import AccessBlocked,IdentityChanged
from cj_message.domain import Unavailable as MessageUnavailable
from cj_memory.domain import Conflict,Unavailable as MemoryUnavailable
from cj_memory.operation import OperationWithheld
from cj_memory_jobs.codec import Conflict as CandidateConflict,Unavailable as CandidateUnavailable
from cj_memory_jobs.service import OperationWithheld as CandidateWithheld
from cj_message.travel_reference import MessageContextAuthority
from runtime_adapter.contract import decode,encode,Unavailable

from .lio_memory_routes import _decode_target
from .runtime_action_input import NativeActionInputs
from .runtime_memory_choice import NativeMemoryChoice
from .runtime_memory_stop import NativeMemoryStop
from .runtime_message_input import lio_input
from .runtime_preparation_input import MEMORY_TASK,MEMORY_SLOTS


class NativeMemorySetup:
    def __init__(self,claims,boundary,database,token_supplier,configuration,candidates,cards,wait_original):
        self.claims,self.boundary,self.database=claims,boundary,database
        self.token_supplier,self.configuration=token_supplier,configuration
        self.candidates,self.cards,self.wait_original=candidates,cards,wait_original
        self.choice=NativeMemoryChoice(claims,cards,token_supplier)
        self.inputs=NativeActionInputs(claims)

    @staticmethod
    def _operation(operation):
        try:return operation()
        except (AccessBlocked,IdentityChanged):
            raise Unavailable('ORIGINAL_AUTH_UNAVAILABLE') from None
        except (MessageUnavailable,Conflict,MemoryUnavailable,OperationWithheld,
                CandidateConflict,CandidateUnavailable,CandidateWithheld):
            raise Unavailable('NATIVE_MEMORY_ORIGINAL_UNAVAILABLE') from None

    def require_available(self):return self._operation(self._require_available)

    def _require_available(self):
        def original(context):
            if context.scope!=self.claims.binding.scope:raise Unavailable('NATIVE_MEMORY_ORIGINAL_OWNER_CHANGED')
            return context.principal
        principal=self.boundary.with_history_context(self.token_supplier(),original)
        profile=self.configuration.collection.profiles[principal.subject]
        if (profile.expires_at<=datetime.now(timezone.utc) or 'self' not in profile.subjects or
                'long_term' not in profile.extents or any(slot not in profile.slots or
                not profile.slots[slot].collection_allowed or profile.slots[slot].kind!='preference' for slot in MEMORY_SLOTS)):
            raise Unavailable('NATIVE_MEMORY_LEGAL_PROFILE_NOT_AVAILABLE')

    def _bind(self,token,operation):
        def current(context):
            if context.scope!=self.claims.binding.scope:raise Unavailable('NATIVE_MEMORY_ORIGINAL_OWNER_CHANGED')
            repository,principal,guard=self.cards.collection._binding(context,token)
            _,policy,_=self.cards.collection.resolve_collection(principal)
            profile=self.configuration.collection.profiles[principal.subject]
            def typed_guard(stage):
                guard(stage)
                if profile.expires_at<=datetime.now(timezone.utc):
                    raise Unavailable('NATIVE_MEMORY_LEGAL_PROFILE_EXPIRED')
                return principal,repository.scope
            authority=MessageContextAuthority(self.database.message_repository(context.scope),lambda:context.principal)
            return operation(context,repository,policy,typed_guard,authority)
        return self.boundary.with_history_context(token,current)

    def _item(self,token,item_id,*,active=False):
        def read(context,repository,policy,guard,authority):
            with repository.transaction() as tx:
                item=tx.detail(item_id)
                if item is None:raise Unavailable('NATIVE_MEMORY_ORIGINAL_ITEM_UNAVAILABLE')
                if active and (item.status!='active' or tx.source(item.command) is not True):
                    raise Unavailable('NATIVE_MEMORY_POSITIVE_CONTROL_UNAVAILABLE')
                guard('runtime_memory_original_item')
                return item
        return self._bind(token,read)

    def _target(self,request,slot):
        token=self.token_supplier();mid=request['step_id']
        def read(context):
            stored=self.claims.query(context,mid)
            if stored is None:raise Unavailable('NATIVE_MEMORY_PREPARATION_SOURCE_UNAVAILABLE')
            original=decode(self.candidates.current(context,token,mid,stored.receipt.run_id))
            selected=[item for item in original['candidates'] if item['slot']==slot]
            if len(selected)!=1:raise Unavailable('NATIVE_MEMORY_LEGAL_CANDIDATE_NOT_UNIQUE')
            projected=self.cards.project(context,token,mid,stored.receipt.run_id)
            selected_id=selected[0]['candidate_id']
            tags=[] if projected is None else [tag for tag in projected['tags'] if tag['id']==selected_id]
            if len(tags)!=1:raise Unavailable('NATIVE_MEMORY_NATIVE_TARGET_UNAVAILABLE')
            return tags[0]['target']
        return self.boundary.with_history_context(token,read)

    def dispatch(self,request,*,deadline):
        return self._operation(lambda:self._dispatch(request,deadline=deadline))

    def _dispatch(self,request,*,deadline):
        if request['kind']!='task_setup' or request['payload']['task_id']!=MEMORY_TASK:
            raise Unavailable('NATIVE_MEMORY_SETUP_ACTION_CHANGED')
        self.require_available()
        token=self.token_supplier()
        def provision(executor,scope):
            if scope!=self.claims.binding.scope:raise Unavailable('NATIVE_MEMORY_ORIGINAL_OWNER_CHANGED')
            self.database._provision_scope(executor,scope)
        admitted=self.boundary.receive_lio(token,lio_input(self.claims.binding.scope,request),
            prepare_scope=provision,version=LIO_VERSION_V2)
        stored=self.boundary.with_history_context(token,lambda context:self.claims.query(context,request['step_id']))
        if stored is None or (stored.receipt.run_id,stored.receipt.conversation_id)!=(admitted.run_id,admitted.conversation_id):
            raise Unavailable('NATIVE_MEMORY_PREPARATION_ADMISSION_CHANGED')
        self.wait_original(stored.receipt,deadline)
        for label,slot in zip(('stopped','control'),MEMORY_SLOTS):
            # A previous Remember changes the native epoch. Read a fresh target
            # for the second choice; do not replay a stale projected target.
            target=self._target(request,slot)
            self.choice.remember(request,label,target,deadline=deadline)
        native=self.inputs.read(request,deadline=deadline,label='stopped')
        item=self._item(token,_decode_target(native['target'])['candidate_id'])
        def stop(context,repository,policy,guard,authority):
            service=NativeMemoryStop(self.claims,repository,policy,guard,authority)
            return service.stop(request,'stop-use',item,deadline=deadline)
        self._bind(token,stop)

    def proof(self,request,*,deadline):
        return self._operation(lambda:self._proof(request,deadline=deadline))

    def _proof(self,request,*,deadline):
        token=self.token_supplier();choices={};items={}
        for label,slot in zip(('stopped','control'),MEMORY_SLOTS):
            native=self.inputs.read(request,deadline=deadline,label=label)
            choices[label]=self.choice.proof(request,label,deadline=deadline)
            target=_decode_target(native['target'])
            item=self._item(token,target['candidate_id'],active=label=='control')
            if item.command.slot!=slot:raise Unavailable('NATIVE_MEMORY_SETUP_SLOT_CHANGED')
            items[label]=dict(item_id=item.command.item_id,version=item.version,status=item.status,
                source_id=item.command.source_id,source_version=item.command.source_version,slot=slot)
        def stopped(context,repository,policy,guard,authority):
            return NativeMemoryStop(self.claims,repository,policy,guard,authority).proof(request,'stop-use',deadline=deadline)
        receipt=self._bind(token,stopped)
        complete=(all(value['status']=='remembered' for value in choices.values()) and receipt is not None
            and receipt['status']=='withdrawn' and receipt['item_id']==items['stopped']['item_id']
            and receipt['version']==items['stopped']['version'] and items['stopped']['status']=='withdrawn'
            and items['control']['status']=='active')
        return encode(dict(version='G2C-native-memory-setup-original.1',message_id=request['step_id'],
            status='PASS' if complete else 'UNKNOWN',choices=choices,stop_use=receipt,items=items))
