"""B343 contract integration with actual C engines and a test-only C adapter.

No production C344/C336 delivery is claimed. All services/roles/leases/Meter/API
are actual local implementations; only model output and C adapter wiring are controlled.
"""
import base64,json,os,sys,time,hashlib
from pathlib import Path
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from fastapi.testclient import TestClient
import psycopg,jsonschema
import local_history_pg as harness
from trip_message_pg import document
from cj_api.local_app import LocalDatabase,create_local_app,load_history_configuration,scope_for,ISSUER
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import checker_for,needs_lease_for
from cj_auth.interfaces import AdmissionStatus
from cj_agent.provider import FakeProvider,ProviderUnknown
from cj_message.edit_protocol import EditConfiguration,PreparedEdit,MEMORY_ABI,PUBLISHER_ABI
from cj_message.travel import Selection
from cj_message.travel_reference import MessageContextAuthority
from cj_memory.domain import Service as MemoryService
from cj_memory.postgres import Repository as MemoryRepository
from cj_memory.runtime import Selection as MemorySelection
from cj_memory.typed_runtime import TypedRuntimeMemory
from cj_memory.typed import ContextRef
from cj_memory.manual import ManualPolicy
from cj_trip.domain import Trip,Proposal,packed
from cj_trip.postgres import Repository as TripRepository
from cj_manual_edit.scoped import Request,resolve,preview
from cj_needs.revision_lease import LeaseUnavailable
from cj_run.core import Binding,Denied
sys.path.insert(0,str(harness.ROOT/'scripts'))
import dev_auth,local_run_context as operator,run_worker,message_edit_profile


class MemoryAdapter:
    abi=MEMORY_ABI
    def __init__(self,services):self.services=services
    def bind(self,database,scope,identity,admit,*,message_context):
        class Adapter(TypedRuntimeMemory):
            def context_for(self,binding,lease):
                namespace=lease.memory_namespace;namespace.check(binding)
                return ContextRef(namespace.kind,namespace.id)
        return Adapter(self.services[identity],lambda stage:(admit(),scope),
                       MemorySelection('self',frozenset({'food','pace'}),8000),message_context)


class Publisher:
    abi=PUBLISHER_ABI
    def __init__(self,database,auth):self.database,self.auth=database,auth;self.after_sources=None;self.before_writer=None;self.after_writer=None
    def prepare(self,binding,source):
        trip=Trip(source.reference.command.trip_context.id,source.reference.command.trip_context.expected_version,source.trip_content)
        request=Request.parse(packed(dict(version='TRIP-scoped-request.1',request_id='request-'+binding.run_id,
            trip_id=trip.trip_id,expected_version=trip.version,original_hash=hashlib.sha256(trip.content).hexdigest(),
            text=json.loads(source.original_utf8)['text'],language='zh-Hans',selection=dict(kind='items',item_ids=list(source.selected_item_ids)))))
        resolved=resolve(trip,request)
        return PreparedEdit(packed(dict(version='B343-TEST-MODEL',request_id=request.request_id,trip_id=trip.trip_id,
            expected_version=trip.version,original_hash=request.original_hash,item_id=source.selected_item_ids[0])).decode(),resolved)
    @contextmanager
    def hold_sources(self,publication,prepared):
        # Real canonical original NEEDS lease, not a data-only callback permission.
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
        assert candidate is not None
        r=publication.reference
        proposal=Proposal('p-'+r.run_id,r.command.trip_context.id,r.command.trip_context.expected_version,
                          'manual-structured.1',int(time.time())+600,candidate.content)
        publication.before_write()
        repository=self.database.trip_repository(r.owner_scope)
        repository._publish_in_tx(publication.cursor,proposal) # C's sole writer, same physical transaction.
        if self.after_writer is not None:self.after_writer()
        return proposal.proposal_id


class Model(FakeProvider):
    def __init__(self):super().__init__();self.hook=None;self.inputs=[]
    def stream(self,messages,system=None):
        self.calls+=1;self.inputs.append(messages)
        yield ''  # Network continuation occurs after the canonical first-advance RUN fence.
        if self.hook is not None:self.hook()
        if system is None:yield 'explicit discussion';return
        v=json.loads(system)
        yield packed(dict(version='TRIP-manual-edit.1',request_id=v['request_id'],trip_id=v['trip_id'],
            expected_version=v['expected_version'],original_hash=v['original_hash'],title=None,order=None,
            changes=[dict(item_id=v['item_id'],field='text',value='本次轻松一点 / lighter this time')])).decode()


def exercise(auth,conninfo):
    subjects=['alice','bob'];dev_auth.init(auth,subjects+['history'])
    cfg=json.loads(conninfo.read_text());now=int(time.time());path=auth.parent/'edit-run.json'
    path.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(unit='provider_call',budget=50,
        period_start=now-60,period_end=now+3600,max_steps=50,max_tools=10,max_output=100000,max_seconds=600),
        output_limits=dict(model=12000,tool=2000,memory=8000)),history=[])))
    context=load_run_context(path)
    for subject in subjects:
        operator.provision_budget(conninfo,context,subject);dev_auth.activate_travel(conninfo,subject,context,'MESSAGE-TRAVEL-CONSUMER@1')
        operator.put_needs(conninfo,auth,subject,packed(dict(action_id='n1',needs_id='needs',expected_version=0,source=dict(kind='manual',text='explicit fixture'),changes=dict(party_size=dict(state='known',value=1)))))
    olddb=LocalDatabase(conninfo,run_context=context,travel_context=True)
    headers={s:{'Authorization':'Bearer '+dev_auth.token(auth,s,30)} for s in subjects}
    services={};travels={};authorities={};admissions={}
    checker=checker_for(auth)
    with TestClient(create_local_app(conninfo_path=conninfo,auth_dir=auth,run_context=context,travel_context=True)) as old:
        for subject in subjects:
            travels[subject]=harness.expect(old.post('/v1/travel-context-actions',content=packed(dict(version='TRAVEL-context-action.1',action_id='namespace',operation='create',travel_context=None)),headers={**headers[subject],'Content-Type':'application/octet-stream'}))['receipt']['travel_context']
            scope=scope_for(ISSUER,subject);olddb.provision(scope)
            with olddb.connect(scope) as connection:connection.execute('INSERT INTO cj_memory_scope(scope) VALUES(%s)',(scope,))
            def admit(s=subject):
                decision=checker.check(headers[s]['Authorization'][7:])
                assert decision.status is AdmissionStatus.ALLOWED
                return decision.principal
            authority=MessageContextAuthority(olddb.message_repository(scope),admit)
            authorities[subject]=authority;admissions[subject]=admit
            policy=ManualPolicy(frozenset({'self'}),frozenset({'food','pace'}),frozenset({'long_term','current'}),frozenset({travels[subject]['id']}),datetime.now(timezone.utc)+timedelta(hours=1),lambda c,r:True,lambda c,r:True)
            service=MemoryService(MemoryRepository(lambda s=scope:olddb.connect(s),scope,typed_context=True,transaction_binder=lambda conn,cur:conn.bind_scope(cur)),manual_policy=policy)
            for slot,current in [('food',False),('pace',True)]:
                original=packed(dict(version='MEMORY-manual.2',operation_id='op-'+slot,item_id='mem-'+slot,subject='self',slot=slot,kind='preference',text='素食' if not current else '临时慢行',extent='current' if current else 'long_term',context=None if not current else dict(kind='travel',id=travels[subject]['id'],expected_version=1),occurred_at='date unknown'))
                service.with_operation(lambda stage:(admit(),scope),lambda operation,raw=original:packed(operation.save_manual_typed(raw,authority).__dict__))
            services[subject]=service
    publisher=Publisher(None,auth);configuration=EditConfiguration(MemoryAdapter(services),publisher)
    database=LocalDatabase(conninfo,run_context=context,travel_context=True,edit_configuration=configuration);publisher.database=database
    import migrate
    migration=next(v for v in migrate.load() if v['name']=='message_edit_context')
    with psycopg.connect(**cfg) as admin:
        admin.execute((harness.ROOT/migration['down']).read_text());admin.execute((harness.ROOT/migration['file']).read_text())
    for subject in subjects:assert message_edit_profile.activate(conninfo,subject,context,configuration,Selection(travels[subject]['id'],1))=='activated'
    source=document();source['items'][0]['fixed']=dict(state='known',value=False);source=packed(source);scope=scope_for(ISSUER,'alice')
    from cj_agent.draft import trip_scope_for
    with psycopg.connect(**cfg) as admin:admin.execute('INSERT INTO cj_trip_record(scope,trip_id,version,content) VALUES(%s,%s,1,%s)',(trip_scope_for(scope),'trip-a',source))
    schema=json.loads((harness.ROOT/'contracts/message/edit-schema.1.json').read_text())
    def expect(response,code=200):
        value=harness.expect(response,code)
        if code==200 and value.get('version') in ('MESSAGE-accept.4','MESSAGE-send-status.4','MESSAGE-history.3','RUN-display.4','RUN-cancel.4','RUN-draft-status.5'):jsonschema.validate(value,schema)
        return value
    versions=[1];namespace_versions=[1]
    with TestClient(create_local_app(conninfo_path=conninfo,auth_dir=auth,run_context=context,travel_context=True,edit_configuration=configuration,history_configuration=load_history_configuration(auth))) as client:
        def send(mid,*,subject='alice',cid=None,selection=None,code=200,intent='propose_scoped_edit',namespace=None):
            cid=mid if cid is None else cid
            head=expect(client.put('/v1/conversations',params=dict(conversation_id=cid),headers=headers[subject]))
            selection=selection or dict(id='trip-a',expected_version=versions[0],content_sha256=hashlib.sha256(source).hexdigest(),day=None,item_ids=['item-a'])
            raw=json.dumps(dict(version='MESSAGE-send.4',conversation_id=cid,message_id=mid,text='这个条目轻松一点',trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=head['last_sequence'],modification_intent=intent,trip_context=selection,travel_context=namespace or dict(id=travels[subject]['id'],expected_version=namespace_versions[0]),needs_reference=dict(id='needs',expected_version=1) if intent!='none' else None),ensure_ascii=False,indent=2).encode()+b'\n'
            return expect(client.post('/v4/messages',content=raw,headers={**headers[subject],'Content-Type':'application/octet-stream'}),code),raw
        def state(mid):return expect(client.get('/v4/run-display',params=dict(message_id=mid),headers=headers['alice']))
        accepted,raw=send('first')
        model=Model();outcomes=run_worker.run_once(database,model,auth)
        assert len(outcomes)==1 and outcomes[0].status=='completed' and model.calls==1,outcomes
        text=json.dumps(model.inputs,ensure_ascii=False);assert '素食' in text and '临时慢行' in text
        result=state('first');assert result['reference']==accepted['reference'] and result['snapshot']['status']=='completed'
        r=accepted['receipt'];binding=Binding(scope,r['conversation_id'],r['generation'],r['message_id'],r['run_id'],r['sequence'])
        assert database.run_repository(scope).recover(binding).state.effects==('trip_proposal:p-'+r['run_id'],)
        status=expect(client.get('/v5/run-draft-status',params=dict(message_id='first'),headers=headers['alice']));assert status['draft_outcome']=='published'
        history=expect(client.get('/v3/message-history',params=dict(conversation_id='first',limit=10),headers=headers['alice']));assert base64.b64decode(history['messages'][0]['original_utf8_base64'])==raw
        assert expect(client.post('/v4/messages',content=raw,headers={**headers['alice'],'Content-Type':'application/octet-stream'}))['reference']==accepted['reference']
        assert run_worker.run_once(database,Model(),auth)==[]
        def binding_for(value):
            r=value['receipt'];return Binding(scope,r['conversation_id'],r['generation'],r['message_id'],r['run_id'],r['sequence'])
        def saved(value):return database.run_repository(scope).recover(binding_for(value)).state
        def cancel(mid,subject='alice',code=200):
            return expect(client.post('/v4/run-cancellations',json=dict(version='RUN-cancel.4',message_id=mid),headers=headers[subject]),code)
        def no_effect(value,status,model):
            outcomes=run_worker.run_once(database,model,auth)
            assert outcomes[0].status==status,outcomes
            assert not saved(value).effects and not saved(value).text
            with psycopg.connect(**cfg) as admin:assert admin.execute('SELECT count(*) FROM cj_trip_proposal WHERE proposal_id=%s',('p-'+value['receipt']['run_id'],)).fetchone()[0]==0
        # #327: accepted send.2 uses supported history.2, never stripped by v1.
        operator.provision_budget(conninfo,context,'history');dev_auth.activate_travel(conninfo,'history',context,'MESSAGE-TRAVEL-CONSUMER@1')
        history_headers={'Authorization':'Bearer '+dev_auth.token(auth,'history',30)}
        old_app=create_local_app(conninfo_path=conninfo,auth_dir=auth,run_context=context,travel_context=True,history_configuration=load_history_configuration(auth))
        with TestClient(old_app) as legacy:
            travel=harness.expect(legacy.post('/v1/travel-context-actions',content=packed(dict(version='TRAVEL-context-action.1',action_id='h-ns',operation='create',travel_context=None)),headers={**history_headers,'Content-Type':'application/octet-stream'}))['receipt']['travel_context']
            head=harness.expect(legacy.put('/v1/conversations',params=dict(conversation_id='typed-history'),headers=history_headers))
            legacy_raw=json.dumps(dict(version='MESSAGE-send.2',conversation_id='typed-history',message_id='typed-history',text='原文本 e\u0301/中文',trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=0,travel_context=dict(id=travel['id'],expected_version=1),needs_reference=None),ensure_ascii=False,indent=2).encode()+b'\n'
            original=harness.expect(legacy.post('/v2/messages',content=legacy_raw,headers={**history_headers,'Content-Type':'application/octet-stream'}))
            historical_model=FakeProvider();assert run_worker.run_once(olddb,historical_model,auth)[0].status=='completed' and historical_model.calls==1
            page=harness.expect(legacy.get('/v2/message-history',params=dict(conversation_id='typed-history',limit=1),headers=history_headers))
            assert base64.b64decode(page['messages'][0]['original_utf8_base64'])==legacy_raw and page['messages'][0]['reference']==original['reference']
            assert page['messages'][0]['receipt']['input_sha256']==hashlib.sha256(legacy_raw).hexdigest() and page['messages'][0]['text']=='原文本 e\u0301/中文'
            harness.expect(legacy.get('/v1/message-history',params=dict(conversation_id='typed-history',limit=1),headers=history_headers),503)
            harness.expect(legacy.get('/v2/message-history',params=dict(conversation_id='typed-history',limit=1),headers=headers['bob']),503)
            harness.expect(legacy.get('/v2/message-history',params=dict(conversation_id='typed-history',limit=1),headers={'Authorization':'Bearer invalid'}),401)
        print('PASS327 supported history.2 exact original send.2 bytes/hash/text/reference via signed API/runtime PG/formal worker; v1 refusal and owner/auth preserved')
        # Boundary refusals do not issue receipts or create a second exit.
        send('foreign',subject='bob',code=503)
        send('foreign-namespace',namespace=dict(id=travels['bob']['id'],expected_version=1),code=503)
        for label,changes,code in [('stale',dict(expected_version=99),409),('hash',dict(content_sha256='0'*64),409),('item',dict(item_ids=['not-owned']),503),('empty',dict(item_ids=[]),400)]:
            selection=dict(id='trip-a',expected_version=versions[0],content_sha256=hashlib.sha256(source).hexdigest(),day=None,item_ids=['item-a']);selection.update(changes)
            send(label,selection=selection,code=code)
        expect(client.post('/v4/messages',content=raw,headers={'Authorization':'Bearer invalid','Content-Type':'application/octet-stream'}),401)
        expect(client.post('/v4/messages',content=raw+b' ',headers={**headers['alice'],'Content-Type':'application/octet-stream'}),409)
        for route in ('/v1/message-receipts','/v2/run-display','/v3/run-display'):
            expect(client.get(route,params=dict(message_id='first'),headers=headers['alice']),503)
        # No actual C capability/configuration: no new accepted input, never memory-off.
        with TestClient(create_local_app(conninfo_path=conninfo,auth_dir=auth,run_context=context,travel_context=True)) as unconfigured:
            v=json.loads(raw);v['message_id']='unsupported'
            expect(unconfigured.post('/v4/messages',content=packed(v),headers={**headers['alice'],'Content-Type':'application/octet-stream'}),503)
        old_profile=__import__('message_trip_profile')
        try:old_profile.activate(conninfo,'alice',context,'MESSAGE-TRIP-CONSUMER@1')
        except psycopg.errors.RaiseException:pass
        else:raise AssertionError('old profile MEMORY refusal was removed')
        discussion,_=send('discussion-gate',intent='none')
        discussion_host=run_worker._worker_for_scope(database,Model(),auth,scope,checker_for(auth))
        discussion_binding=binding_for(discussion);discussion_queued=discussion_host.runs.accept(discussion_binding)
        discussion_exit=discussion_host.budget_exit.for_run(discussion_binding,discussion_queued)
        from cj_run.core import Event as RunEvent
        discussion_host.runs.apply(RunEvent(discussion_binding,1,'discussion-start','started'))
        discussion_exit.prepare(discussion_host.runs,discussion_binding,'draft',[dict(role='user',content='explicit discussion')],'discussion source',Model())
        discussion_source=discussion_host.message_context.capture(discussion_binding)
        try:
            with discussion_host.message_context.publication(discussion_binding,discussion_source,deadline=lambda:None):raise AssertionError('discussion gained write authority')
        except Denied:pass
        assert cancel('discussion-gate')['status']=='cancelled'
        discussion_model=Model();assert run_worker.run_once(database,discussion_model,auth)[0].status=='cancelled' and discussion_model.calls==0
        # Same selector continues, but A→B→A invalidates old work even when IDs return.
        selection=dict(id='trip-a',expected_version=1,content_sha256=hashlib.sha256(source).hexdigest(),day=dict(date='2026-10-31',timezone='Asia/Shanghai'),item_ids=[])
        a,_=send('aba-a',cid='aba');b,_=send('aba-b',cid='aba',selection=selection);c,_=send('aba-c',cid='aba')
        assert [v['reference']['selection_epoch'] for v in (a,b,c)]==[1,2,3]
        model=Model();outcomes=run_worker.run_once(database,model,auth)
        assert [v.status for v in outcomes]==['context_invalid','context_invalid','completed'] and model.calls==1,outcomes
        # Formal Trip writer first invalidates original source before model/charge.
        stale,_=send('version-before')
        with psycopg.connect(**cfg) as admin:
            admin.execute('SELECT scope FROM cj_trip_scope WHERE scope=%s FOR UPDATE',(trip_scope_for(scope),))
            admin.execute('UPDATE cj_trip_record SET version=2 WHERE scope=%s',(trip_scope_for(scope),))
        versions[0]=2;model=Model();no_effect(stale,'context_invalid',model);assert model.calls==0
        # The original accepted bytes/reference recover without latest-version substitution.
        assert expect(client.post('/v4/messages',content=raw,headers={**headers['alice'],'Content-Type':'application/octet-stream'}))['reference']==accepted['reference']
        assert cancel('first')['reference']==accepted['reference']
        queued,_=send('cancel-before');cancel('cancel-before',subject='bob',code=503);assert cancel('cancel-before')['status']=='cancelled'
        model=Model();assert run_worker.run_once(database,model,auth)[0].status=='cancelled' and model.calls==0
        unknown,_=send('unknown')
        class Unknown(Model):
            def stream(self,messages,system=None):self.calls+=1;raise ProviderUnknown('controlled');yield
        model=Unknown();outcomes=run_worker.run_once(database,model,auth)
        assert model.calls==1 and outcomes[0].status=='unknown'
        # Persistent interrupted RUN becomes UNKNOWN without another model call.
        interrupted,_=send('interrupted');host=run_worker._worker_for_scope(database,Model(),auth,scope,checker_for(auth))
        bind=binding_for(interrupted);state0=host.runs.accept(bind)
        from cj_run.core import Event as RunEvent
        original_exit=host.budget_exit.for_run(bind,state0)
        host.runs.apply(RunEvent(bind,1,'started','started'))
        original_exit.prepare(host.runs,bind,'draft',[dict(role='user',content='original interrupted input')],'original draft',Model())
        model=Model();assert run_worker.run_once(database,model,auth)[0].status=='unknown' and model.calls==0
        assert cancel('interrupted')['status']=='unknown'
        assert run_worker.run_once(database,Model(),auth)==[]
        # Memory correction in model IO uses original C save/current_context/fence.
        memory_changed,_=send('memory-change')
        def correct_memory():
            from cj_memory.typed_api import create_local_typed_app
            from cj_memory.typed_local import TypedConfiguration
            policy=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),profiles={s:dict(subjects=['self'],slots={slot:dict(kind='preference',collection_allowed=True,semantic_resolved=True) for slot in ('food','pace')},extents=['long_term','current'],context_ids=[]) for s in subjects}),travel_contexts={s:[travels[s]['id']] for s in subjects})
            memory_config=TypedConfiguration.from_bytes(packed(policy))
            with TestClient(create_local_typed_app(conninfo_path=conninfo,auth_dir=auth,configuration=memory_config)) as memory_api:
                response=memory_api.post('/v2/memory-management-actions',content=packed(dict(version='MEMORY-management.2',action_id='food-update',operation='edit',item_id='mem-food',expected_version=1,expected_source_version=1,context=None,text='新的素食要求')),headers={**headers['alice'],'Content-Type':'application/octet-stream'})
                expect(response)
        model=Model();model.hook=correct_memory;no_effect(memory_changed,'context_invalid',model);assert model.calls==1
        # Fresh account revocation during model IO cannot publish old source bytes.
        revoked,_=send('revoked');invitations=(auth/'invited.json').read_bytes()
        model=Model();model.hook=lambda:(auth/'invited.json').write_text(json.dumps(['bob']))
        try:no_effect(revoked,'context_invalid',model)
        finally:(auth/'invited.json').write_bytes(invitations)
        assert model.calls==1
        inflight,_=send('cancel-inflight');model=Model();model.hook=lambda:cancel('cancel-inflight')
        no_effect(inflight,'cancelled',model);assert model.calls==1
        # Namespace version/currentness is not inferred from the Trip or from memory.
        moved,_=send('namespace-before')
        expect(client.post('/v1/travel-context-actions',content=packed(dict(version='TRAVEL-context-action.1',action_id='advance',operation='advance',travel_context=dict(id=travels['alice']['id'],expected_version=1))),headers={**headers['alice'],'Content-Type':'application/octet-stream'}))
        namespace_versions[0]=2;model=Model();no_effect(moved,'context_invalid',model);assert model.calls==0
        # Source SQL finishes before final original deadline; no Proposal/effect if expired.
        deadline_case,_=send('deadline')
        import cj_api.local_worker_context as routing
        from types import SimpleNamespace
        clock=[time.time()];publisher.after_sources=lambda:clock.__setitem__(0,clock[0]+601)
        try:
            with patch.object(routing,'time',SimpleNamespace(time=lambda:clock[0])):
                model=Model();no_effect(deadline_case,'completed',model)
        finally:publisher.after_sources=None
        assert saved(deadline_case).budget_exhausted_stage=='draft' and model.calls==1
        # Actual C insert followed by failure rolls back C Proposal AND RUN effect.
        rolled,_=send('rollback')
        from cj_memory.runtime import RuntimeUnknown
        def fail_after():raise RuntimeUnknown('controlled after writer')
        publisher.after_writer=fail_after
        try:model=Model();no_effect(rolled,'unknown',model)
        finally:publisher.after_writer=None
        assert model.calls==1
        # Physical commit ACK loss: both rows persist; original result never re-executes.
        ack,_=send('ack-loss');model=Model();ack_host=run_worker._worker_for_scope(database,model,auth,scope,checker_for(auth))
        real_connect=ack_host.runs.repository.connect
        class AckCursor:
            def __init__(self,cur,owner):self.cur,self.owner=cur,owner
            def __getattr__(self,name):return getattr(self.cur,name)
            def execute(self,sql,*args,**kw):
                result=self.cur.execute(sql,*args,**kw)
                if str(sql).startswith('INSERT INTO cj_trip_proposal'):self.owner.wrote=True
                return result
        class LostAck:
            def __init__(self,connection):self.connection=connection;self.wrote=False
            def __getattr__(self,name):return getattr(self.connection,name)
            def cursor(self):return AckCursor(self.connection.cursor(),self)
            def commit(self):
                self.connection.commit()
                if self.wrote:raise OSError('controlled committed acknowledgement loss')
        ack_host.runs.repository.connect=lambda:LostAck(real_connect())
        assert ack_host.process()[0].status=='unknown' and model.calls==1
        assert saved(ack).effects==('trip_proposal:p-'+ack['receipt']['run_id'],)
        with psycopg.connect(**cfg) as admin:assert admin.execute('SELECT count(*) FROM cj_trip_proposal WHERE proposal_id=%s',('p-'+ack['receipt']['run_id'],)).fetchone()[0]==1
        assert run_worker.run_once(database,Model(),auth)==[]
        # Both real lock orders, on the one actual RUN/Trip connection.
        held,_=send('held');holder=run_worker._worker_for_scope(database,Model(),auth,scope,checker_for(auth));bind=binding_for(held)
        queued_state=holder.runs.accept(bind);original_exit=holder.budget_exit.for_run(bind,queued_state)
        holder.runs.apply(RunEvent(bind,1,'held-start','started'))
        original_exit.prepare(holder.runs,bind,'draft',[dict(role='user',content='original held input')],'original draft',Model())
        capture=holder.message_context.capture(bind)
        attempted=Event();finished=Event()
        def writer():
            with psycopg.connect(**cfg) as admin:
                attempted.set();admin.execute('SELECT scope FROM cj_trip_scope WHERE scope=%s FOR UPDATE',(trip_scope_for(scope),))
                admin.execute('UPDATE cj_trip_record SET version=3 WHERE scope=%s',(trip_scope_for(scope),))
            finished.set()
        with ThreadPoolExecutor(max_workers=1) as pool:
            with holder.message_context.publication(bind,capture,phase='proposal',deadline=lambda:None) as publication:
                publication.lock_trip();future=pool.submit(writer)
                assert attempted.wait(5) and not finished.wait(.1)
                prepared=publisher.prepare(bind,capture)
                v=json.loads(prepared.system)
                reply=packed(dict(version='TRIP-manual-edit.1',request_id=v['request_id'],trip_id=v['trip_id'],expected_version=v['expected_version'],original_hash=v['original_hash'],title=None,order=None,changes=[dict(item_id=v['item_id'],field='text',value='controlled held-writer candidate')]))
                proposal=publisher.publish_in_transaction(publication,prepared,reply.decode())
                publication.record_effect(proposal)
            future.result(timeout=5)
        versions[0]=3
        model=Model();assert run_worker.run_once(database,model,auth)[0].status=='unknown' and model.calls==0
        try:publication.check(bind)
        except LeaseUnavailable:pass
        else:raise AssertionError('publication lease survived lifetime')
        # Privilege/owner/ABI and nonempty-down boundaries use the real runtime role.
        with psycopg.connect(**dict(cfg,user='cj_m1_runtime')) as runtime:
            runtime.execute("SELECT set_config('cj.message_scope',%s,true),set_config('cj.message_context_abi',%s,true)",(scope,'MESSAGE-TRAVEL-CONSUMER@1'))
            assert runtime.execute('SELECT count(*) FROM cj_message_receipt').fetchone()[0]==0
            runtime.execute("SELECT set_config('cj.message_edit_abi',%s,true)",('CJ-MESSAGE-EDIT@1',))
            assert runtime.execute('SELECT count(*) FROM cj_message_edit_reference WHERE scope=%s',(scope_for(ISSUER,'bob'),)).fetchone()[0]==0
        with psycopg.connect(**cfg) as admin:
            try:
                with admin.transaction():admin.execute((harness.ROOT/migration['down']).read_text())
            except psycopg.errors.RaiseException:pass
            else:raise AssertionError('populated edit down accepted')
        print('PASS B343 real signed API/PG/run_once/Meter, C typed long-term+temporary memory and scoped preview/sole writer on common RUN cursor; original bytes/status/history/receipt and lifecycle negatives')

if __name__=='__main__':
    harness.exercise=exercise;harness.main()
