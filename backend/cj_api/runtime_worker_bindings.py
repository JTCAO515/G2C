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
from .runtime_run_requests import RunRequests
from .runtime_message_input import lio_input
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
                 wall_clock=lambda:datetime.now(timezone.utc),release=None):
        data=decode(read_private(path,131072))
        fields={'version','baseline','resource_root','runtime_card','evidence_manifest','lines'}
        require(type(data)is dict and type(data.get('version'))is str
            and data['version']in('G2C-runtime-host.1','G2C-runtime-host.2')
            and set(data)==fields|({'fixture_preparation'}if data['version']=='G2C-runtime-host.2'else set())
            and data['baseline']=='national.2','RUNTIME_WORKER_MANIFEST')
        self.fixture_preparation=data['fixture_preparation']if data['version']=='G2C-runtime-host.2'else None
        self.fixture_preparation_status='NOT_CONFIGURED'
        if data['version']=='G2C-runtime-host.2':require(type(self.fixture_preparation)is dict,'FIXTURE_PREPARATION_HOST_REQUIRED')
        require(type(data['lines']) is list and 1<=len(data['lines'])<=4,'RUNTIME_WORKER_LINE_BOUND')
        require(type(data['resource_root']) is str and Path(data['resource_root']).is_absolute() and
            type(data['evidence_manifest']) is str and Path(data['evidence_manifest']).is_absolute(),'RUNTIME_WORKER_PATHS')
        self.public_root=Path(data['resource_root'])
        self.pins=freeze_national_v2(data['runtime_card'],resource_root=self.public_root)
        require(self.pins.value['model']==configured_model(services.model,M4_NATIVE_TURN_BUFFERED),
            'RUNTIME_ACTUAL_MODEL_CONFIGURATION_CHANGED')
        self.runtime,self.services,self.tools,self.clock=runtime,services,tools,clock
        self.wall_clock=wall_clock
        self.release=release
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
        # Only canonical controlled-start admission creates a Pause. Ordinary
        # runtime operations are no-ops in completed(); source rejection stays
        # on registrations/reflection's existing UNKNOWN path before dispatch.
        return None if session is None else session['controls']

    def _memory_services(self,session):
        from .lio_memory_routes import LioMemoryCards
        from .local_lio_memory import lio_candidates
        configuration=self.runtime.memory_configuration_for_scope(session['binding'].scope)
        if configuration is None:return None
        candidates=lio_candidates(self.database,session['boundary'],self.runtime.demo_subjects,configuration.collection)
        return configuration.collection,candidates,LioMemoryCards(candidates.collection,candidates.current)

    def _state_reader(self,session):
        from .lio_dialogue_routes import _timeline
        from .lio_trip_cards import LioTripCards
        from .lio_trip_routes import LioTripBoundary,_head,_history
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
            memory_services=session['memory_services']
            if memory_services is None:raise Unavailable('RUNTIME_TYPED_MEMORY_NOT_CONFIGURED')
            _,_,memory_cards=memory_services
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

            from .runtime_weather_fault import NativeWeatherFault
            weather_fault=NativeWeatherFault(claims,session['routing'],self.database,self.services.model.authorization,
                evidence.directory,self.pins)
            session['routing'].registry_transformer=weather_fault.wrap
            def wait(receipt,deadline,reader=originals,supplier=token):
                while self.clock()<deadline:
                    try:value=decode(reader.inventory(supplier(),receipt.message_id))
                    except Unavailable as error:
                        if str(error) not in ('ORIGINAL_RUN_UNAVAILABLE','ORIGINAL_SNAPSHOT_CHANGED'):raise
                    else:
                        if value['status'] not in ('queued','running'):return
                    sleep(min(.1,max(0,deadline-self.clock())))
                raise TimeoutError('original runtime deadline reached')
            session['memory_services']=self._memory_services(session)
            memory_setup=None
            if session['memory_services'] is not None:
                from .runtime_memory_setup import NativeMemorySetup
                configuration,candidates,memory_cards=session['memory_services']
                memory_setup=NativeMemorySetup(claims,boundary,self.database,token,configuration,candidates,memory_cards,wait)
            dialogue=NativeDialogue(claims,boundary,self.database,token,wait,
                dataset_path=self.public_root/'eval/optimization/cases.v2.json',
                trip_boundary=self._trip_boundary(session),cancellation=cancellation,memory_setup=memory_setup,weather_fault=weather_fault)
            collector=RuntimeCollector(originals,claims,session['routing'],token,self.pins,session['references_directory'],
                guard=guard,state_reader=self._state_reader(session),model_reader=RuntimeModel(originals,self.services.model,
                    native_turn_profile=M4_NATIVE_TURN_BUFFERED),dialogue=dialogue,clock=self.clock)
            def require_worker(binding,pins,deadline,expected=session['binding']):
                require(binding==expected and pins.raw==self.pins.raw and self.artifact_directory is not None,
                    'RUNTIME_WORKER_BINDING_CHANGED')
                if self.clock()>=deadline:raise Unavailable('DEADLINE_REACHED')
            def admit_reflection(mid,original=boundary,supplier=token,source=claims):
                request=decode(source.read(mid,deadline=self.clock()+30))
                return original.receive_lio(supplier(),lio_input(source.binding.scope,request),
                    prepare_scope=self.database._provision_scope,version=LIO_VERSION_V2)
            backend=NativeRuntimeBackend(authority,claims,collector,boundary,token,
                require_worker=require_worker,wait_original=wait,admit_reflection=admit_reflection,dialogue=dialogue)
            session['backend']=backend
            session['collector']=collector
            session['originals']=originals
            session['dialogue']=dialogue
            session['adapter']=RuntimeAdapter(backend,session['binding'],self.pins,session['mapping_directory'],
                dataset_path=self.public_root/'eval/optimization/cases.v2.json')
        if self.fixture_preparation is not None:
            self._attach_fixture_preparation(self.fixture_preparation)

    def _attach_fixture_preparation(self,data):
        """B's fixed preparation readers, never an E-selected source/path.

        No begin/close/issue, preparation dispatch or use reservation occurs
        during startup. Missing originals stay unavailable. The final use
        publisher remains a separate required dependency.
        """
        from .runtime_fixture_registry import FixtureUseRegistry
        from .runtime_fixture_boundary import FixtureSourceBoundary
        from .runtime_release_witness import NativeReleaseWitness
        from .runtime_preparation_cost import PreparationCostInventory,FrozenPreparationCost
        from .runtime_preparation_lifecycle import PreparationLifecycle
        from .runtime_fixture_originals import FixtureOriginalReferences
        fields={'version','purpose_approval_sha256','producer_binding_sha256','consumer_binding_sha256',
            'preparation_message_ids','preparation_message_id','policy_file','reservations_directory',
            'references_directory','cost_directory','lifecycle_directory','release_control_directory','source_state_file'}
        require(type(data)is dict and set(data)==fields
            and data['version']=='G2C-fixture-preparation-host.1'
            and data['purpose_approval_sha256']=='32dd0d098fde23b93b2625fc341afc34e561588ffb9f1e1128577648e08f194c',
            'FIXTURE_PREPARATION_HOST_FIELDS')
        sessions={s['line']:s for s in self.by_scope.values()}
        if not {'C','E'}<=sessions.keys():
            # Preserve startup's existing revoked-identity isolation: no
            # fixture metadata reader is attached, while ordinary A/L traffic
            # keeps its original worker and registration path.
            self.fixture_preparation_status='FIXTURE_ORIGINAL_SESSIONS_NOT_CONNECTED'
            return
        if self.release is None:raise Unavailable('FIXTURE_NATIVE_RELEASE_NOT_CONNECTED')
        producer,consumer=sessions['C'],sessions['E']
        require(data['producer_binding_sha256']==producer['binding'].key
            and data['consumer_binding_sha256']==consumer['binding'].key,'FIXTURE_PREPARATION_HOST_BINDINGS')
        mids=data['preparation_message_ids']
        require(type(mids)is list and 0<len(mids)<=3 and data['preparation_message_id']in mids,
            'FIXTURE_PREPARATION_APPROVED_MESSAGES')
        require(type(data['policy_file'])is str and Path(data['policy_file']).is_absolute(),
            'FIXTURE_PREPARATION_POLICY_PATH')
        require(type(data['release_control_directory'])is str and Path(data['release_control_directory']).is_absolute(),
            'FIXTURE_PREPARATION_RELEASE_PATH')
        require(type(data['source_state_file'])is str and Path(data['source_state_file']).is_absolute(),
            'FIXTURE_PREPARATION_STATE_PATH')
        expected=read_private(data['source_state_file'],1048576)
        frame=decode(expected)
        require(type(frame)is dict and frame['binding_sha256']==producer['binding'].key
            and frame['preparation']['message_id']==data['preparation_message_id'],'FIXTURE_PREPARATION_STATE_BINDING')
        directories={key:pinned_directory(data[key])for key in (
            'reservations_directory','references_directory','cost_directory','lifecycle_directory')}
        def guard(*,read_only,deadline=None):
            deadline=self.clock()+30 if deadline is None else deadline
            for session in (producer,consumer):
                session['authority'].require(binding=session['binding'],pins_sha256=self.pins.key,
                    purpose='query',deadline=deadline,read_only=True)
                if session['authority'].pins()!=self.pins.raw:
                    raise Unavailable('FIXTURE_CURRENT_SOURCE_CHANGED')
            if not read_only:
                consumer['authority'].require(binding=consumer['binding'],pins_sha256=self.pins.key,
                    purpose='query',deadline=deadline,read_only=False)
        release=NativeReleaseWitness(self.database,producer['binding'].scope,Path(data['release_control_directory']),
            guard=lambda:guard(read_only=True),release=self.release)
        source=FixtureSourceBoundary(producer['authority'],producer['binding'],self.pins,
            producer['boundary'],self._trip_boundary(producer),producer['token'],data['preparation_message_id'],
            release,qualification_guard=lambda deadline:guard(read_only=True,deadline=deadline))
        def definition():raise Unavailable('FIXTURE_DEFINITION_PUBLISHER_NOT_CONNECTED')
        def admission():return consumer['claims']._admission()
        def preparation_guard():
            if read_private(data['source_state_file'],1048576)!=expected:
                raise Unavailable('FIXTURE_PREPARATION_STATE_CHANGED')
            source.with_current(expected,lambda state,private:b'qualified',deadline=self.clock()+30)
        registry=FixtureUseRegistry(directories['reservations_directory'],data['policy_file'],
            producer['binding'],producer['binding'],consumer['binding'],self.pins,
            guard=guard,source_guard=definition,admission_lock=admission,clock=self.wall_clock,
            preparation_guard=preparation_guard)
        baseline=registry.policy['baseline']
        require(frame['trip']==dict(trip_id_sha256=baseline['trip_id_sha256'],version=baseline['trip_version'],
            content_sha256=baseline['content_sha256']),'FIXTURE_PREPARATION_BASELINE_CHANGED')
        costs=PreparationCostInventory(producer['originals'],producer['authority'],producer['binding'],
            self.pins,producer['token'],tuple(mids))
        lifecycle=PreparationLifecycle(directories['lifecycle_directory'],costs)
        frozen=FrozenPreparationCost(directories['cost_directory'],costs)
        reader=FixtureOriginalReferences(directories['references_directory'],registry,
            preparation_cost=frozen,preparation_lifecycle=lifecycle,clock=self.clock)
        consumer['collector'].fixture_originals=reader
        consumer['fixture_preparation']=dict(registry=registry,source=source,cost=frozen,lifecycle=lifecycle,originals=reader)
        self.fixture_preparation_status='PREPARATION_READERS_ONLY_USE_PUBLISHER_UNRUN'

    def _trip_boundary(self,session):
        from .lio_trip_routes import LioTripBoundary
        return LioTripBoundary(self.database,session['authority'].checker,self.confirmation_signer)
