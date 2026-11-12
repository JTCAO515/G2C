"""B-issued private worker composition; never load a card/identity from a task.

The manifest is written only by B after actual source/image verification. It
pins the non-restored canonical directory identity and original authenticated
subjects; missing files are not initialized or replaced here.
"""
from datetime import datetime,timezone
import os
from pathlib import Path
import re
import stat
from time import monotonic,sleep
import uuid

from cj_agent.provider import M4_NATIVE_TURN_BUFFERED
from cj_message.auth_boundary import Boundary
from cj_message.demo_dialogue import LIO_VERSION_V2
from cj_run.display_snapshot import DisplaySnapshotConfiguration,DisplaySnapshotReader
from runtime_adapter import RuntimeAdapter
from runtime_adapter.contract import decode,encode,require,Unavailable

from .local_account_admission_v2 import account_checker_for,retired_in_transaction
from .local_app import ISSUER,scope_for
from .local_worker_context import checker_factory_for
from .runtime_authority import RuntimeAuthority
from .runtime_collector import RuntimeCollector
from .runtime_dialogue import NativeDialogue
from .runtime_message_claims import MessageClaims
from .runtime_model import configured_model,RuntimeModel
from .runtime_native_backend import NativeRuntimeBackend
from .runtime_originals import RuntimeOriginals
from .runtime_private import read_private
from .runtime_run_requests import RunRequests,REFLECTION_MESSAGE
from .runtime_text_slots import freeze_national_v2


def pinned_directory(value):
    require(type(value) is dict and set(value)=={'path','device','inode'},'RUNTIME_CANONICAL_DIRECTORY_PIN')
    require(type(value['path']) is str and Path(value['path']).is_absolute() and
        type(value['device']) is int and value['device']>=0 and type(value['inode']) is int and value['inode']>0,
        'RUNTIME_CANONICAL_DIRECTORY_PIN')
    path=Path(value['path'])
    descriptor=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        info=os.fstat(descriptor)
        require(info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700 and
            (info.st_dev,info.st_ino)==(value['device'],value['inode']),'RUNTIME_CANONICAL_DIRECTORY_CHANGED')
    finally:os.close(descriptor)
    return path


class RuntimeWorkerBindings:
    def __init__(self,path,runtime,services,tools,*,confirmation_signer,clock=monotonic,
                 wall_clock=lambda:datetime.now(timezone.utc)):
        data=decode(read_private(path,131072))
        require(type(data) is dict and set(data)=={'version','baseline','resource_root','runtime_card','evidence_manifest','lines'}
            and data['version']=='G2C-runtime-host.1' and data['baseline']=='national.2','RUNTIME_WORKER_MANIFEST')
        require(type(data['lines']) is list and 1<=len(data['lines'])<=4,'RUNTIME_WORKER_LINE_BOUND')
        require(type(data['resource_root']) is str and Path(data['resource_root']).is_absolute() and
            type(data['evidence_manifest']) is str and Path(data['evidence_manifest']).is_absolute(),'RUNTIME_WORKER_PATHS')
        self.public_root=Path(data['resource_root'])
        self.pins=freeze_national_v2(data['runtime_card'],resource_root=self.public_root)
        require(self.pins.value['model']==configured_model(services.model,M4_NATIVE_TURN_BUFFERED),
            'RUNTIME_ACTUAL_MODEL_CONFIGURATION_CHANGED')
        self.runtime,self.services,self.tools,self.clock=runtime,services,tools,clock
        self.database=runtime.database();self.by_scope={};self.inactive_scopes={};self.evidence_manifest=Path(data['evidence_manifest'])
        self.artifact_directory=None
        lines=set()
        for entry in data['lines']:
            require(type(entry) is dict and set(entry)=={'line','subject','token_file','canonical_directory','references_directory','mapping_directory'}
                and type(entry['line']) is str and entry['line'] in ('L','C','E','F') and entry['line'] not in lines,
                'RUNTIME_WORKER_LINE')
            lines.add(entry['line'])
            require(type(entry['subject']) is str and entry['subject'] in runtime.demo_subjects,
                'RUNTIME_EXISTING_DEMO_SUBJECT_REQUIRED')
            configured_scope=scope_for(ISSUER,entry['subject'])
            require(configured_scope not in self.by_scope and configured_scope not in self.inactive_scopes,
                'RUNTIME_DUPLICATE_ORIGINAL_SUBJECT')
            require(type(entry['token_file']) is str and Path(entry['token_file']).is_absolute(),'RUNTIME_ORIGINAL_TOKEN_PATH')
            token_path=Path(entry['token_file'])
            def token(path=token_path):
                raw=read_private(path,4096).decode('ascii').strip()
                require(raw and all(0x21<=ord(char)<=0x7e for char in raw),'RUNTIME_ORIGINAL_TOKEN_FILE')
                return raw
            checker=account_checker_for(runtime.auth,self.database,selected_subjects=runtime.demo_subjects)
            authority=RuntimeAuthority(checker,token,services.model.authorization,self.pins,lambda:self.pins.raw,
                line=entry['line'],wall_clock=wall_clock,clock=clock)
            try:binding=authority.binding()
            except (Unavailable,OSError,ValueError):
                # An expired/revoked/missing experiment credential never turns
                # into a new identity or an outage for ordinary A/L/C traffic.
                # Its native runtime IDs remain closed, not a C0 fallback.
                self.inactive_scopes[configured_scope]='ORIGINAL_AUTH_UNAVAILABLE'
                continue
            require(binding.scope==configured_scope,'RUNTIME_VERIFIED_SUBJECT_CHANGED')
            require(binding.scope not in self.by_scope and binding.scope in tools.buffered_streaming_scopes,
                'RUNTIME_OWNED_BUFFERED_SCOPE_REQUIRED')
            try:authority.require(binding=binding,pins_sha256=self.pins.key,purpose='query',deadline=clock()+30,read_only=True)
            except Unavailable as error:
                self.inactive_scopes[configured_scope]=str(error)
                continue
            checker_builder=checker_factory_for(runtime.auth,selected_subjects=runtime.demo_subjects)
            def transaction_checker(transaction,scope,builder=checker_builder):
                return builder(retired_in_transaction(transaction.cur,scope))
            boundary=Boundary(checker,lambda principal:self.database.message_repository(scope_for(principal.issuer,principal.subject)),
                lambda:str(uuid.uuid4()),checker_in_transaction=transaction_checker)
            claims=MessageClaims(pinned_directory(entry['canonical_directory']),boundary,token,authority,self.pins,history_profile='lio.2')
            routing=RunRequests(claims,boundary,token,tools,profile='national.2',clock=clock)
            session=dict(line=entry['line'],authority=authority,binding=binding,token=token,boundary=boundary,claims=claims,routing=routing,
                references_directory=pinned_directory(entry['references_directory']),mapping_directory=pinned_directory(entry['mapping_directory']))
            self.by_scope[binding.scope]=session
        self.confirmation_signer=confirmation_signer

    def _session(self,binding):
        if re.fullmatch(r'runtime-[a-f0-9]{64}',binding.message_id) is None:return None
        return self.by_scope.get(binding.scope)

    def registrations(self,binding):
        session=self._session(binding)
        if session is None:
            if binding.scope in self.inactive_scopes and re.fullmatch(r'runtime-[a-f0-9]{64}',binding.message_id) is not None:return {}
            return self.tools.registrations
        return session['routing'].registrations(binding)

    def reflection(self,binding):
        session=self._session(binding)
        if session is None:
            if binding.scope in self.inactive_scopes and re.fullmatch(r'runtime-[a-f0-9]{64}',binding.message_id) is not None:
                from cj_usage.metered_exit import BudgetUnknown
                raise BudgetUnknown('runtime original scope is not configured')
            return None
        return session['routing'].reflection(binding)

    def selects(self,binding):
        session=self._session(binding)
        return False if session is None else session['routing'].selects(binding)

    def exit_observer(self,binding):
        session=self._session(binding)
        if session is None:return None
        request=session['routing'].request(binding)
        return session['controls'] if request is not None and request['kind']=='start_controlled_generation' else None

    def _state_reader(self,session):
        from .lio_dialogue_routes import _timeline
        from .lio_memory_routes import LioMemoryCards
        from .lio_trip_cards import LioTripCards
        from .lio_trip_routes import LioTripBoundary,_head,_history
        from .local_lio_memory import lio_candidates
        boundary=session['boundary'];checker=session['authority'].checker
        display=DisplaySnapshotReader(boundary,lambda principal,scope:self.database.run_repository(scope),
            configuration=DisplaySnapshotConfiguration(512000,1_048_576))
        cards=LioTripCards(self.database,checker)
        trips=LioTripBoundary(self.database,checker,self.confirmation_signer)
        def read(token,mid):
            snapshot=decode(display.read_travel_events(token,mid))
            request=decode(session['claims'].read(mid,deadline=self.clock()+30))
            if request['kind']=='reflection':return encode(snapshot)
            cid=snapshot['conversation_id']
            if re.fullmatch(r'lio-dialogue-[a-f0-9]{32}',cid) is None:return encode(snapshot)
            memory_configuration=self.runtime.memory_configuration_for_scope(session['binding'].scope)
            if memory_configuration is None:raise Unavailable('RUNTIME_TYPED_MEMORY_NOT_CONFIGURED')
            candidates=lio_candidates(self.database,boundary,self.runtime.demo_subjects,memory_configuration.collection)
            memory_cards=LioMemoryCards(candidates.collection,candidates.current)
            timeline=_timeline(boundary,self.database.run_repository,cards,memory_cards,token,cid,None,True)
            require(timeline.status_code==200,'RUNTIME_NATIVE_TIMELINE_UNAVAILABLE')
            def history(context):
                head=_head(context,cid);rows=[]
                if head is not None:
                    before=None
                    while True:
                        page=context.lio_revisions(head.trip_id,before=before)
                        rows.extend(dict(trip_id=v.trip_id,version=v.version,content=decode(v.content)) for v in page)
                        if not page or page[-1].version==1:break
                        if len(rows)>=128:raise Unavailable('RUNTIME_TRIP_HISTORY_BOUND')
                        before=page[-1].version
                    if _head(context,cid)!=head:raise Unavailable('RUNTIME_TRIP_HISTORY_CHANGED')
                return encode(dict(public=decode(_history(context,None,cid)),revisions=rows))
            body=encode(dict(run=snapshot,visible=decode(timeline.body),trip_history=decode(trips.with_operation(token,history))))
            if len(body)>1_048_576:raise Unavailable('RUNTIME_STATE_EVIDENCE_BOUND')
            return body
        return read

    def attach_evidence(self,evidence):
        """Called once during startup, before any worker dispatch/socket opens."""
        require(evidence.runtime_scopes==frozenset(self.by_scope.keys()|self.inactive_scopes.keys()) and evidence.source_commit==self.pins.value['code_sha'],
            'RUNTIME_EVIDENCE_BINDING_CHANGED')
        self.artifact_directory=evidence.directory
        self.tools.tool_evidence=evidence
        for session in self.by_scope.values():
            claims=session['claims'];authority=session['authority'];token=session['token'];boundary=session['boundary']
            def guard(*,read_only,original=authority,binding=session['binding']):
                original.require(binding=binding,pins_sha256=self.pins.key,purpose='query',deadline=self.clock()+30,read_only=read_only)
            originals=RuntimeOriginals(boundary,self.database,self.services.model.authorization,evidence.directory,query_original=claims.query)
            from .runtime_controlled_generation import ControlledGeneration
            from .runtime_cancel import NativeCancellation
            controls=ControlledGeneration(clock=self.clock);session['controls']=controls
            cancellation=NativeCancellation(claims,boundary,self.database,token,controls,originals)
            def wait(receipt,deadline,reader=originals,supplier=token):
                while self.clock()<deadline:
                    try:value=decode(reader.inventory(supplier(),receipt.message_id))
                    except Unavailable as error:
                        if str(error) not in ('ORIGINAL_RUN_UNAVAILABLE','ORIGINAL_SNAPSHOT_CHANGED'):raise
                    else:
                        if value['status'] not in ('queued','running'):return
                    sleep(min(.1,max(0,deadline-self.clock())))
                raise TimeoutError('original runtime deadline reached')
            dialogue=NativeDialogue(claims,boundary,self.database,token,wait,
                dataset_path=self.public_root/'eval/optimization/cases.v2.json',
                trip_boundary=self._trip_boundary(session),cancellation=cancellation)
            collector=RuntimeCollector(originals,claims,session['routing'],token,self.pins,session['references_directory'],
                guard=guard,state_reader=self._state_reader(session),model_reader=RuntimeModel(originals,self.services.model,
                    native_turn_profile=M4_NATIVE_TURN_BUFFERED),dialogue=dialogue,clock=self.clock)
            def require_worker(binding,pins,deadline,expected=session['binding']):
                require(binding==expected and pins.raw==self.pins.raw and self.artifact_directory is not None,
                    'RUNTIME_WORKER_BINDING_CHANGED')
                if self.clock()>=deadline:raise Unavailable('DEADLINE_REACHED')
            def admit_reflection(mid,original=boundary,supplier=token):
                return original.receive_lio(supplier(),encode(dict(version=LIO_VERSION_V2,message_id=mid,
                    text=REFLECTION_MESSAGE,locale='en',new_conversation=True)),
                    prepare_scope=self.database._provision_scope,version=LIO_VERSION_V2)
            backend=NativeRuntimeBackend(authority,claims,collector,boundary,token,
                require_worker=require_worker,wait_original=wait,admit_reflection=admit_reflection,dialogue=dialogue)
            session['backend']=backend
            session['dialogue']=dialogue
            session['adapter']=RuntimeAdapter(backend,session['binding'],self.pins,session['mapping_directory'],
                dataset_path=self.public_root/'eval/optimization/cases.v2.json')

    def _trip_boundary(self,session):
        from .lio_trip_routes import LioTripBoundary
        return LioTripBoundary(self.database,session['authority'].checker,self.confirmation_signer)
