"""Fresh signed send.4 fixture with an actually generated/accepted formal Trip."""
import json,sys
from pathlib import Path
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend/trip/tests'),str(ROOT/'backend/draft/tests'),str(ROOT/'backend/agent/tests'),str(ROOT/'backend/cj_api/tests'),str(ROOT/'scripts')]
import needs_actions_pg as original
from e2e_local import Harness,CONNINFO
from registered_host_support import RegisteredHost
from cj_api.local_app import LocalDatabase,create_local_app,scope_for,ISSUER,load_history_configuration
from cj_api.local_worker_context import checker_for
from cj_trip.confirmation import ConfirmationSigner
from cj_trip.domain import packed,Trip
from cj_memory.edit_runtime import EditRuntimeConfiguration
from cj_memory.typed_api import create_local_typed_app
from cj_memory.typed_local import TypedConfiguration
from cj_message.edit_protocol import EditConfiguration
from cj_message.travel import ABI,Selection
from cj_run.core import Binding
import dev_auth,message_edit_profile,run_worker


class Fixture:
    setup_source=original.NeedsActionChecks.setup_source;worker=original.NeedsActionChecks.worker
    plan=original.NeedsActionChecks.plan;action=original.NeedsActionChecks.action;post=original.NeedsActionChecks.post
    def __init__(self,case,subject,publisher,*,legacy=False):
        self.case=case
        self.assertEqual=case.assertEqual;self.assertIsNotNone=case.assertIsNotNone
        self.host=RegisteredHost(case.auth/subject,Path(CONNINFO),{s:(30,2,30000) for s in (subject,'other-'+subject)})
        self.env=dict(CJ_LOCAL_NEEDS_PROFILE='manual-v1',CJ_LOCAL_TRAVEL_CONTEXT='message-travel.1')
        self.signer=ConfirmationSigner(b'synthetic-memory-edit-fixture-key-123456789')
        for identity in self.host.subjects:dev_auth.activate_travel(Path(CONNINFO),identity,self.host.profiles[identity][1],ABI)
        self.subject=subject;self.scope=scope_for(ISSUER,subject);self.auth=self.host.auth
        self.headers=self.host.headers[subject];self.context=self.host.profiles[subject][1]
        if legacy:self.trip=self.legacy_source()
        else:
            app,outcome,db=self.plan(subject)
            with TestClient(app) as client:
                response=self.post(client,subject,self.action(subject,outcome,'accept'))
                case.assertEqual(response.status_code,200,response.text)
                self.trip_id=response.json()['receipt']['trip_id']
                value=client.get('/v4/trip-structured',params=dict(trip_id=self.trip_id),headers=self.headers).json()['trip']
                self.trip=Trip(self.trip_id,value['version'],packed(value['content']))
        with patch.dict(__import__('os').environ,self.env),self.host.api(subject) as client:
            def create(label):
                response=client.post('/v1/travel-context-actions',content=packed(dict(version='TRAVEL-context-action.1',action_id=label,
                    operation='create',travel_context=None)),headers={**self.headers,'Content-Type':'application/octet-stream'})
                case.assertEqual(response.status_code,200,response.text);return response.json()['receipt']['travel_context']
            self.namespace=create('explicit-namespace');self.other_namespace=create('independent-namespace')
        identities=self.host.subjects
        profile=dict(subjects=['self'],slots={slot:dict(kind='preference',collection_allowed=True,semantic_resolved=True) for slot in ('food','pace')},
                     extents=['long_term','current'],context_ids=[])
        collection=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',
            expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),profiles={s:profile for s in identities}),
            travel_contexts={s:[self.namespace['id'],self.other_namespace['id']] if s==subject else [] for s in identities})
        self.collection=TypedConfiguration.from_bytes(packed(collection))
        self.policy=dict(version='local-memory-edit-run.1',collection=collection,
                        selections={s:dict(subject='self',slots=['food','pace'],max_bytes=8000) for s in identities})
        self.memory=EditRuntimeConfiguration.from_bytes(packed(self.policy))
        self.memory_app=create_local_typed_app(conninfo_path=CONNINFO,auth_dir=self.auth,configuration=self.collection)
        with TestClient(self.memory_app) as client:
            for item,slot,text,context in [('long','food','Vegetarian / 素食',None),('temp','pace','Slow / 慢行',self.namespace),
                                           ('other','pace','Do not leak other trip',self.other_namespace)]:
                raw=packed(dict(version='MEMORY-manual.2',operation_id='memory-'+item,item_id='mem-'+item,subject='self',slot=slot,kind='preference',
                    text=text,extent='long_term' if context is None else 'current',context=None if context is None else dict(kind='travel',
                        id=context['id'],expected_version=context['version']),occurred_at='date unknown'))
                response=client.post('/v2/memories',content=raw,headers={**self.headers,'Content-Type':'application/octet-stream'})
                case.assertEqual(response.status_code,200,response.text)
        self.publisher=publisher
        self.configuration=EditConfiguration(self.memory,publisher)
        self.database=LocalDatabase(CONNINFO,run_context=self.context,travel_context=True,edit_configuration=self.configuration)
        publisher.database=self.database;publisher.auth=self.auth
        for identity in identities:
            if identity==subject:message_edit_profile.activate(CONNINFO,identity,self.host.profiles[identity][1],self.configuration,Selection(self.namespace['id'],1))
        self.app=create_local_app(conninfo_path=CONNINFO,auth_dir=self.auth,run_context=self.context,travel_context=True,
            edit_configuration=self.configuration,history_configuration=load_history_configuration(self.auth))

    def legacy_source(self):
        from cj_trip.postgres import Repository as TripRepository
        from cj_trip.domain import Proposal
        from cj_agent.draft import trip_scope_for
        from trip_message_pg import document
        import time
        db=LocalDatabase(CONNINFO,run_context=self.context,travel_context=True)
        db.provision(self.scope)
        repository=TripRepository(lambda:db.connect(self.scope),trip_scope_for(self.scope),self.signer,structured=True)
        content=document();content['items'][0]['fixed']=dict(state='known',value=False)
        # This fixture source uses the actual sole Proposal/Signer/act writer,
        # never a raw Trip INSERT. Scoped generation itself uses the real worker.
        p=Proposal('fixture-structured-one','formal-one',0,'fixture-explicit.1',int(time.time())+600,packed(content))
        repository.publish(p);detail=repository.proposal_detail(p.proposal_id)
        action=self.signer.issue(repository.scope,detail,action_id='accept-fixture-source',kind='accept',candidate_hash=detail.candidate_hash).action
        repository.act(action);self.trip_id=p.trip_id
        self.setup_source(self.subject)
        self.worker(self.subject,original.source_fixture.PlanModel())[0].process()
        return repository.detail(self.trip_id)

    def send(self,key,*,intent='propose_scoped_edit',namespace=None,trip=None,code=200):
        import hashlib
        with TestClient(self.app) as client:
            response=client.put('/v1/conversations',params=dict(conversation_id=key),headers=self.headers)
            self.case.assertEqual(response.status_code,200,response.text);head=response.json()
            raw=packed(dict(version='MESSAGE-send.4',conversation_id=key,message_id=key,text='Make selected item lighter / 本次轻松一点',trip_id=None,
                creation_intent='none',expected_generation=head['generation'],expected_sequence=0,modification_intent=intent,
                trip_context=trip or dict(id=self.trip.trip_id,expected_version=self.trip.version,content_sha256=hashlib.sha256(self.trip.content).hexdigest(),day=None,item_ids=[json.loads(self.trip.content)['items'][-1]['id']]),
                travel_context=namespace or dict(id=self.namespace['id'],expected_version=1),needs_reference=None if intent=='none' else dict(id='visit',expected_version=1)))
            response=client.post('/v4/messages',content=raw,headers={**self.headers,'Content-Type':'application/octet-stream'})
            self.case.assertEqual(response.status_code,code,response.text)
            if code!=200:return response
            value=response.json();r=value['receipt']
            return Binding(self.scope,r['conversation_id'],r['generation'],r['message_id'],r['run_id'],r['sequence'])

    def host_worker(self,model):return run_worker._worker_for_scope(self.database,model,self.auth,self.scope,checker_for(self.auth))
    def run(self,model):return run_worker.run_once(self.database,model,self.auth)
    def manage(self,operation,version,*,text=None,key=None,source_version=1):
        value=dict(version='MEMORY-management.2',action_id=key or operation,operation=operation,item_id='mem-long',
                   expected_version=version,expected_source_version=source_version)
        if operation=='edit':value.update(context=None,text=text)
        with TestClient(self.memory_app) as client:
            response=client.post('/v2/memory-management-actions',content=packed(value),headers={**self.headers,'Content-Type':'application/octet-stream'})
            self.case.assertEqual(response.status_code,200,response.text);return response.json()['receipt']


from cj_api.local_worker_context import needs_lease_for
from cj_message.edit_protocol import PreparedEdit,PUBLISHER_ABI
from cj_manual_edit.scoped import Request,resolve,preview
from cj_trip.postgres import Repository as TripRepository
from cj_trip.domain import Proposal
from cj_agent.draft import trip_scope_for
from cj_agent.provider import FakeProvider
from contextlib import contextmanager
import time


class ProbePublisher:
    """C344 test bridge only; C336 production publisher is delivered separately."""
    abi=PUBLISHER_ABI
    def __init__(self):self.after_sources=None;self.before_writer=None
    def prepare(self,binding,source):
        r=source.reference;trip=Trip(r.command.trip_context.id,r.command.trip_context.expected_version,source.trip_content)
        req=Request.parse(packed(dict(version='TRIP-scoped-request.1',request_id='request-'+binding.run_id,
            trip_id=trip.trip_id,expected_version=trip.version,original_hash=r.command.trip_context.content_sha256,
            text=json.loads(source.original_utf8)['text'],language='en',selection=dict(kind='items',item_ids=list(source.selected_item_ids)))))
        prompt=packed(dict(request_id=req.request_id,trip_id=trip.trip_id,expected_version=trip.version,
            original_hash=req.original_hash,item_id=source.selected_item_ids[0],content_version=r.content_version)).decode()
        return PreparedEdit(prompt,resolve(trip,req))
    @contextmanager
    def hold_sources(self,publication,prepared):
        binding=publication.binding
        holder=needs_lease_for(self.database,checker_for(self.auth),lambda:dev_auth.token(self.auth,binding.scope.rsplit(':',1)[1],5))
        with holder(binding) as check:
            check()
            if self.after_sources is not None:self.after_sources()
            yield check
    def publish_in_transaction(self,publication,prepared,reply):
        publication.lock_trip()
        if self.before_writer is not None:self.before_writer(publication)
        candidate=preview(prepared.state,reply.encode()).candidate
        if candidate is None:raise ValueError('probe candidate outside selection')
        r=publication.reference
        proposal=Proposal('memory-probe-'+r.run_id,r.command.trip_context.id,r.command.trip_context.expected_version,
            'memory-probe.1',int(time.time())+300,candidate.content)
        publication.before_write()
        TripRepository(lambda:self.database.connect(r.owner_scope),trip_scope_for(r.owner_scope),structured=True)._publish_in_tx(publication.cursor,proposal)
        return proposal.proposal_id


class Model(FakeProvider):
    def __init__(self):super().__init__();self.hook=None;self.inputs=[]
    def stream(self,messages,system=None):
        self.calls+=1;self.inputs.append(messages);yield ''
        if self.hook is not None:self.hook()
        if system is None:yield 'discussion';return
        v=json.loads(system)
        yield packed(dict(version='TRIP-manual-edit.2' if v['content_version']=='structured.2' else 'TRIP-manual-edit.1',
            request_id=v['request_id'],trip_id=v['trip_id'],expected_version=v['expected_version'],original_hash=v['original_hash'],
            title=None,order=None,changes=[dict(item_id=v['item_id'],field='text',value='Lighter this time / 本次轻松一点')])).decode()
