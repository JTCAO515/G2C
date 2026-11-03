"""Actual BG3 writer/worker/Meter on a genuine accepted Trip discussion."""
from dataclasses import asdict,replace
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from pathlib import Path
import json,os,sys,tempfile,subprocess,unittest,threading
from unittest.mock import patch
import psycopg
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[3];sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'backend/trip/tests')]
import pg_suites,migrate,manual_pg as manual,local_run_context,dev_auth,message_trip_profile,run_worker
import needs_actions_pg as needs
from cj_api.local_app import create_local_app,LocalDatabase,scope_for,ISSUER
from cj_api.local_run_context import RunProfile
from cj_api.local_background import LocalBackgroundHost,GuardedCollectionAdapterV3
from cj_agent.provider import FakeProvider,ProviderFailed
from cj_memory.manual import ManualPolicy
from cj_memory_jobs.collection_app import create_decision_collection_app
from cj_memory_jobs.decision_service import DecisionCollectionAdapter
from cj_memory_jobs.decision_command import DecisionCommand
from cj_memory_jobs.extraction import CollectionPolicy
from cj_message.source import SourceQuery
from cj_run.background import BackgroundJobsV2
from cj_run.background_store import JobRequest,JobStore
from cj_run.background_store_v3 import JobRequestV3
from cj_run.background_v3 import BackgroundJobsV3
from cj_run.core import Denied
from cj_message.auth_boundary import AccessBlocked
from cj_cleanup.core import encode,digest
from cj_api.local_cleanup import Configuration,Runtime
from cj_api.local_worker_context import checker_for
from cj_trip.domain import packed


class DecisionFake(FakeProvider):
    def stream(self,messages,system=None):
        self.calls+=1;data=json.loads(messages[0]['content'])
        assert data['version']=='MEMORY-EXTRACT-DATA@3' and 'never that a visit happened' in system
        decision=data['trip_decisions'][0]
        yield packed(dict(version='MEMORY-EXTRACT@3',entries=[dict(subject='self',slot='planning.choice',kind='experience',
            text='An accepted plan, not a visited experience',extent='long_term',occurred_at='date unknown',
            evidence=[dict(ref=decision['ref'],quote=json.loads(decision['document'])['title'])])])).decode()


class BackgroundV3Checks(manual.ManualChecks):
    def test_actual_original_bg3(self):
        case=os.environ['BG3_CASE']
        migrations=migrate.load();m43=next(entry for entry in migrations if entry['version']==43)
        meter=replace(self.run_context.current.meter,budget=1 if case=='budget' else 20,
                      max_steps=1,max_tools=1,max_seconds=10)
        limits=dict(self.run_context.current.output_limits)
        if case=='output':limits['memory']=1
        self.run_context=replace(self.run_context,current=RunProfile(meter,limits))
        path=Path(manual.CONNINFO);local_run_context.provision_budget(path,self.run_context,'alice')
        dev_auth.activate_travel(path,'alice',self.run_context,'MESSAGE-TRAVEL-CONSUMER@1')
        message_trip_profile.activate(path,'alice',self.run_context,'MESSAGE-TRIP-CONSUMER@1')
        app=create_local_app(conninfo_path=path,auth_dir=self.auth,run_context=self.run_context,travel_context=True,trip_context=True)
        headers={**self.headers('alice'),'Content-Type':'application/octet-stream'};token=headers['Authorization'][7:]
        chats=['decision-one','decision-copy'] if case=='success' else ['decision-one'];heads={}
        with TestClient(app) as client:
            for cid in chats:
                head=client.put('/v1/conversations',params={'conversation_id':cid},headers=headers).json();heads[cid]=head
                response=client.post('/v3/messages',content=packed(dict(version='MESSAGE-send.3',conversation_id=cid,message_id=cid,
                    text='Discuss the accepted plan as a decision, not a visit',trip_id=None,creation_intent='none',
                    expected_generation=head['generation'],expected_sequence=0,travel_context=None,needs_reference=None,
                    trip_context=dict(id=self.trip_id,expected_version=self.base_version,day=None,item_id=None))),headers=headers)
                self.assertEqual(response.status_code,200,response.text)
        database=LocalDatabase(path,run_context=self.run_context,travel_context=True,trip_context=True)
        normal=FakeProvider();outcomes=run_worker.run_once(database,normal,self.auth)
        self.assertEqual(normal.calls,len(chats));self.assertTrue(all(o.status=='completed' for o in outcomes),outcomes)
        slots=frozenset({'planning.choice'});extraction=CollectionPolicy(frozenset({'self'}),slots,5,4096,lambda e:True,lambda e,rows:True)
        memory=ManualPolicy(extraction.subjects,slots,frozenset({'long_term'}),frozenset(),datetime.now(timezone.utc)+timedelta(hours=1),lambda c,r:True,lambda c,r:True)
        c_app=create_decision_collection_app(conninfo_path=path,auth_dir=self.auth,run_context=self.run_context,
            resolve_collection=lambda p:(extraction,memory,lambda e:(None,None)))
        host=c_app.state.memory_history;c=host.service;tick=[__import__('time').time()]
        jobs=BackgroundJobsV3(database=host.database,boundary=host.boundary,collection=DecisionCollectionAdapter(c),max_payload_bytes=262144,clock=lambda:tick[0])
        def enable(cid,action='enable',operation='enable',version=0):
            return c.apply_consent(token,packed(dict(version='MEMORY-HISTORY@1',action_id=action+cid,operation=operation,
                conversation_id=cid,expected_generation=heads[cid]['generation'],expected_epoch=0,expected_source_version=version)))
        def prepare(cid,jid):
            enable(cid)
            raw=packed(dict(version='MEMORY-DECISION-JOBS@1',job_id=jid,attempt_id=jid+'-attempt',source=asdict(SourceQuery(cid,heads[cid]['generation'],0,0,1,1,1)),
                decision=dict(trip_id=self.trip_id,expected_version=self.base_version,content_sha256=sha256(self.content).hexdigest()),end=None))
            command=DecisionCommand.parse(raw)
            with TestClient(c_app) as client:
                response=client.post('/internal/v1/memory-decision/jobs',content=raw,headers=headers)
                self.assertEqual(response.status_code,200,response.text)
            c.begin_decision(token,jid,jid+'-attempt');data=c.prepare_decision_input(token,jid,jid+'-attempt',max_payload_bytes=262144)
            digest=json.loads(json.loads(data)['messages'][0]['content'])['decision_source_sha256']
            req=JobRequestV3(jid,jid+'-attempt',command.reader_query,None,data,digest)
            if case=='success' and jid=='decision-job':
                # Store-level inherited-BG2 fixture, never a C producer or claim.
                old=JobStore(database.run_repository(self.owner))
                legacy=old.prepare(JobRequest('inherited-v2','original-v2',req.query,None,data),meter,limits['memory'])
                with psycopg.connect(**json.loads(path.read_text()),autocommit=True) as audit:
                    versions=migrate.applied(audit)
                    before=audit.execute('SELECT to_jsonb(j)-\'protocol\'-\'decision_source_sha256\' FROM cj_run_background_job j').fetchall()
                    # Probe only registered M43, preserving later schema and its
                    # ledger; this is not a whole-chain downgrade to M42.
                    with audit.transaction():
                        audit.execute((ROOT/m43['down']).read_text())
                        self.assertEqual(audit.execute('SELECT to_jsonb(j) FROM cj_run_background_job j').fetchall(),before)
                        audit.execute((ROOT/m43['file']).read_text())
                    self.assertEqual(migrate.applied(audit),versions)
                    migrate.up(audit,migrations,migrations[-1]['version'])
                self.assertEqual(old.read('inherited-v2','original-v2'),legacy)
                old.transition(legacy,('queued',),'cancelled')
            return req,jobs.prepare(token,req)
        request,original=prepare(chats[0],'decision-job')
        # Real compatibility isolation: no BG2 preparation/outflow or default
        # runtime visibility of the new row; initializer sees its true header.
        wrong=BackgroundJobsV2(database=host.database,boundary=host.boundary,collection=DecisionCollectionAdapter(c),max_payload_bytes=262144)
        with self.assertRaises(TypeError):wrong.prepare(token,JobRequest(request.job_id,request.attempt_id,request.query,None,request.prepared_input))
        with database.connect(self.owner) as conn:self.assertEqual(conn.execute('SELECT count(*) FROM cj_run_background_job').fetchone(),(1 if case=='success' else 0,))
        with database.connect(scope_for(ISSUER,'bob')) as conn:
            conn.execute("SELECT set_config('cj.background_protocol','RUN-BACKGROUND@3',true)")
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_run_background_job').fetchone(),(0,))
            self.assertEqual(conn.execute("UPDATE cj_run_background_job SET state='cancelled' WHERE run_id=%s",(original['run_id'],)).rowcount,0)
        with self.assertRaises((Denied,AccessBlocked)):jobs.prepare(self.headers('bob')['Authorization'][7:],request)
        with database.connect(self.owner) as conn:
            self.assertEqual(conn.execute("SELECT has_table_privilege(current_user,'cj_run_background_job','DELETE'),has_table_privilege(current_user,'cj_run_background_job','TRUNCATE'),pg_has_role(current_user,'cj_local_cleanup','MEMBER')").fetchone(),(False,False,False))
            for field in ('protocol','decision_source_sha256'):
                self.assertFalse(conn.execute("SELECT has_column_privilege(current_user,'cj_run_background_job',%s,'UPDATE')",(field,)).fetchone()[0])
        with psycopg.connect(**json.loads(path.read_text())) as audit:
            self.assertEqual(audit.execute('SELECT protocol,decision_source_sha256 FROM cj_run_background_job WHERE run_id=%s',(original['run_id'],)).fetchone(),('RUN-BACKGROUND@3',request.decision_source_sha256))
            versions=migrate.applied(audit)
            with self.assertRaisesRegex(psycopg.Error,'original BG3 decision evidence retained'),audit.transaction():
                audit.execute((ROOT/m43['down']).read_text())
            self.assertEqual(migrate.applied(audit),versions)
            self.assertIn(43,migrate.applied(audit))
            with self.assertRaisesRegex(psycopg.Error,'immutable original background protocol/decision header'),audit.transaction():
                audit.execute("UPDATE cj_run_background_job SET decision_source_sha256=%s WHERE run_id=%s",('b'*64,original['run_id']))
        class Model(DecisionFake):
            def stream(model,messages,system=None):
                if case=='unknown':model.calls+=1;raise ProviderFailed('synthetic original outcome unknown')
                if case=='time':tick[0]+=10
                if case=='account':
                    raw=next(super().stream(messages,system));half=len(raw)//2
                    yield raw[:half];entered.set()
                    if not release.wait(30):raise AssertionError('BG3 account provider gate timed out')
                    yield raw[half:];return
                yield from super().stream(messages,system)
        model=Model();worker=LocalBackgroundHost(jobs,self.auth)
        if case=='account':
            entered,release=threading.Event(),threading.Event();errors=[];outcomes=[]
            with tempfile.TemporaryDirectory(prefix='bg3-retirement-') as folder:
                registry=Path(folder)/'registry.json'
                targets=('checkpoints/run','business/message','business/usage')
                registry.write_bytes(encode(dict(version='BG3-account-component',stores=[
                    dict(id='checkpoints',objects=[dict(id='run',cleanup_protocol='CLEANUP@1.1')]),
                    dict(id='business',objects=[dict(id=n,cleanup_protocol='CLEANUP@1.1') for n in ('message','usage')])])))
                options=Configuration({'bg3':b'explicit-synthetic-bg3-retirement-key'},'bg3',3600,targets,registry)
                retirement=create_local_app(conninfo_path=path,auth_dir=self.auth,run_context=self.run_context,
                    travel_context=True,trip_context=True,cleanup_configuration=options)
                def run():
                    try:outcomes.extend(run_worker.run_once(database,model,self.auth,background_jobs=worker))
                    except BaseException as error:errors.append(error)
                with TestClient(retirement) as client:
                    def post(url,value,scheme='Bearer',credential=token):
                        response=client.post(url,content=encode(value),headers={'Authorization':scheme+' '+credential,'Content-Type':'application/octet-stream'})
                        self.assertEqual(response.status_code,200,response.text);return response.json()
                    device=post('/v1/cleanup-devices',dict(version='CLEANUP-DEVICE@1',action_id='register',device_id='bg3-device',state_ref=digest(b'bg3-device')))
                    operation=post('/v1/account-cleanup-operations',dict(version='CLEANUP-API@1',action_id='prepare',binding_id=device['binding_id']))
                    thread=threading.Thread(target=run);thread.start()
                    try:
                        self.assertTrue(entered.wait(20),errors)
                        confirmation=post('/v1/account-cleanup-operations/'+operation['operation_id']+'/confirmation',dict(
                            version='CLEANUP-API@1',registry_digest=operation['registry_digest'],confirmation='DELETE_ACCOUNT'))
                        self.assertEqual(confirmation['reason'],'original_tasks_not_yet_stopped');self.assertTrue(thread.is_alive())
                        call=post('/v1/cleanup-device-calls',dict(version='CLEANUP-DEVICE@1',binding_id=device['binding_id'],reason='session_invalid'),'Device',device['device_token'])
                        post('/v1/cleanup-device-receipts',dict(version='CLEANUP-DEVICE@1',action_id='report',operation_id=operation['operation_id'],
                            invocation_id=call['call']['invocation_id'],binding_id=device['binding_id'],request_digest=call['request_digest'],outcome='confirmed'),'Cleanup',call['receipt_token'])
                        with self.assertRaises(AccessBlocked):jobs.query_original(token,request.job_id,request.attempt_id)
                        release.set();thread.join(20);self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
                        self.assertEqual([o.status for o in outcomes],['unknown']);self.assertEqual(model.calls,1)
                        runtime=Runtime(database,options,scope_for)
                        claims=runtime.issuer.verify(operation['progress_token'],purpose='progress',operation_id=operation['operation_id'])
                        progress=runtime.host_gateway(checker_for(self.auth)).resume(claims.subject_digest,operation['operation_id'])
                        self.assertEqual(progress['reason'],'original_usage_outcome_unresolved')
                        response=client.get('/v1/account-cleanup-operations/'+operation['operation_id'],headers={'Authorization':'Cleanup '+operation['progress_token']})
                        self.assertEqual(response.status_code,200);self.assertEqual(response.json()['reason'],'original_usage_outcome_unresolved')
                        with psycopg.connect(**json.loads(path.read_text())) as audit:
                            self.assertEqual(audit.execute('SELECT count(*) FROM cj_run_background_job WHERE run_id=%s',(original['run_id'],)).fetchone(),(1,))
                            self.assertEqual(audit.execute('SELECT count(*) FROM cj_memory_item WHERE scope=%s',(self.owner,)).fetchone(),(0,))
                            ledger=audit.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=(SELECT ledger_scope FROM cj_run_background_job WHERE run_id=%s)',(original['run_id'],)).fetchone()[0]
                            self.assertEqual(ledger['attempts'][original['meter_attempt_id']]['state'],'unknown')
                        print('PASS actual BG3 account component: physical worker blocks erase/device bypass; retirement rejects late publication and sensitive query; restricted original progress and UNKNOWN billing retained')
                    finally:release.set();thread.join(20);self.assertFalse(thread.is_alive())
            return
        if case=='cancel':
            self.assertEqual(jobs.cancel(token,request.job_id,request.attempt_id)['state'],'cancelled')
        if case=='corrupt-trip':
            # Persisted-data fault only: this is not a successful user edit.
            # The private initializer corrupts the version, without fabricating
            # a new canonical action/receipt. C must reject it before outflow.
            with psycopg.connect(**json.loads(path.read_text())) as audit:
                audit.execute('UPDATE cj_trip_record SET version=version+1 WHERE scope=%s AND trip_id=%s',
                              (self.scope,self.trip_id))
        if case=='tail':
            actual_factory=jobs.collection.publication_policy
            def delayed(*args,**kwargs):
                policy=actual_factory(*args,**kwargs);render=policy._render;count=[0]
                def slow(*args,**kwargs):
                    result=render(*args,**kwargs);count[0]+=1
                    if count[0]==2:tick[0]+=10
                    return result
                policy._render=slow;return policy
            jobs.collection.publication_policy=delayed
        armed={'publication':False,'lost':False}
        if case=='ack':
            actual_factory=jobs.collection.publication_policy
            def ack_factory(*args,**kwargs):
                policy=actual_factory(*args,**kwargs);apply=policy.apply_original_result
                def applied(*args,**kwargs):
                    result=apply(*args,**kwargs);armed['publication']=True;return result
                policy.apply_original_result=applied;return policy
            jobs.collection.publication_policy=ack_factory
        resolve=c.resolve_repository
        class LostAck:
            def __init__(self,base):self.base=base
            def __getattr__(self,name):return getattr(self.base,name)
            def commit(self):
                self.base.commit()
                if armed['publication'] and not armed['lost']:armed['lost']=True;raise OSError('actual C COMMIT / lost ACK')
        def repository(*args):
            repo=resolve(*args);connect=repo.connect
            if case=='ack':repo.connect=lambda:LostAck(connect())
            return repo
        with patch.object(c,'resolve_repository',repository):results=run_worker.run_once(database,model,self.auth,background_jobs=worker)
        expected={'success':'completed','unknown':'unknown','ack':'unknown','output':'budget_exhausted','time':'budget_exhausted',
                  'tail':'budget_exhausted','budget':'budget_exhausted','corrupt-trip':'unknown','cancel':None}[case]
        if expected is None:self.assertEqual(results,[])
        else:self.assertEqual([r.status for r in results],[expected],results)
        self.assertEqual(model.calls,0 if case in ('budget','corrupt-trip','cancel') else 1)
        if case in ('ack','unknown'):
            enable(chats[0],'disable','disable',1)
            value=jobs.reconcile(token,request.job_id,request.attempt_id) if case=='ack' else jobs.cancel(token,request.job_id,request.attempt_id)
            self.assertEqual(value['state'],'completed' if case=='ack' else 'cancelled')
        if case=='success':
            first=json.loads(c.query_decision_publication(token,request.job_id,request.attempt_id))
            self.assertEqual(first['decision_source_sha256'],request.decision_source_sha256)
            self.assertEqual(first['receipts'][0]['status'],'candidate')
            second_req,second=prepare(chats[1],'copy-job')
            copied=DecisionFake();again=run_worker.run_once(database,copied,self.auth,background_jobs=worker)
            self.assertEqual([o.status for o in again],['completed']);self.assertEqual(copied.calls,1)
            self.assertEqual(json.loads(c.query_decision_publication(token,second_req.job_id,second_req.attempt_id))['receipts'],first['receipts'])
        self.assertEqual(run_worker.run_once(database,model,self.auth,background_jobs=worker),[])
        with psycopg.connect(**json.loads(path.read_text())) as audit:
            ledger=audit.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=(SELECT ledger_scope FROM cj_run_background_job WHERE run_id=%s)',(original['run_id'],)).fetchone()[0]
            attempt=ledger['attempts'].get(original['meter_attempt_id'])
            if case in ('budget','corrupt-trip','cancel'):self.assertIsNone(attempt)
            else:
                self.assertEqual(ledger['runs'][original['run_id']]['steps'],1);self.assertEqual(ledger['runs'][original['run_id']]['tools'],0)
                self.assertEqual(attempt['state'],'unknown' if case in ('unknown','output','time') else 'settled')
                if case in ('unknown','output','time'):self.assertIsNone(attempt['receipt'])
                else:self.assertEqual(attempt['receipt']['actual'],1)
            if case not in ('success','ack'):
                self.assertEqual(audit.execute('SELECT count(*) FROM cj_memory_item WHERE scope=%s',(self.owner,)).fetchone(),(0,))
        print('PASS BG3 actual '+case+': signed accepted Trip + MSG3/C holder + original run_once/unique Meter/Fake, Pub3/digest and original financial outcome; corrupt-trip is initializer fault injection')


class ProtectedDecisionChecks(needs.NeedsActionChecks):
    def test_real_trip_update_refuses_original_bg3(self):
        subject='manual';app,outcome,database=self.plan(subject)
        context=self.host.profiles[subject][1];auth=self.host.auth;path=Path(manual.CONNINFO)
        headers={**self.host.headers[subject],'Content-Type':'application/octet-stream'};token=headers['Authorization'][7:]
        with TestClient(app) as client:
            accepted=self.post(client,subject,self.action(subject,outcome,'accept'))
            self.assertEqual(accepted.status_code,200,accepted.text);trip_id=accepted.json()['receipt']['trip_id']
            trip=client.get('/v4/trip-structured',params={'trip_id':trip_id},headers=headers).json()['trip']
        message_trip_profile.activate(path,subject,context,'MESSAGE-TRIP-CONSUMER@1')
        foreground=create_local_app(conninfo_path=path,auth_dir=auth,run_context=context,
                                    travel_context=True,trip_context=True,needs_profile='manual-v1')
        with TestClient(foreground) as client:
            head=client.put('/v1/conversations',params={'conversation_id':'protected-decision'},headers=headers).json()
            response=client.post('/v3/messages',content=packed(dict(version='MESSAGE-send.3',conversation_id='protected-decision',
                message_id='protected-decision',text='Discuss our accepted choice',trip_id=None,creation_intent='none',
                expected_generation=head['generation'],expected_sequence=0,travel_context=None,
                needs_reference=None,trip_context=dict(id=trip_id,expected_version=trip['version'],day=None,item_id=None))),headers=headers)
            self.assertEqual(response.status_code,200,response.text)
        current=LocalDatabase(path,run_context=context,travel_context=True,trip_context=True,needs_context=True)
        normal=FakeProvider();outcomes=run_worker.run_once(current,normal,auth)
        self.assertEqual([o.status for o in outcomes],['completed']);self.assertEqual(normal.calls,1)
        slots=frozenset({'planning.choice'});extraction=CollectionPolicy(frozenset({'self'}),slots,5,4096,lambda e:True,lambda e,r:True)
        memory=ManualPolicy(extraction.subjects,slots,frozenset({'long_term'}),frozenset(),datetime.now(timezone.utc)+timedelta(hours=1),lambda c,r:True,lambda c,r:True)
        c_app=create_decision_collection_app(conninfo_path=path,auth_dir=auth,run_context=context,resolve_collection=lambda p:(extraction,memory,lambda e:(None,None)))
        host=c_app.state.memory_history;c=host.service
        c.apply_consent(token,packed(dict(version='MEMORY-HISTORY@1',action_id='enable-protected',operation='enable',conversation_id='protected-decision',expected_generation=head['generation'],expected_epoch=0,expected_source_version=0)))
        source=SourceQuery('protected-decision',head['generation'],0,0,1,1,1)
        raw=packed(dict(version='MEMORY-DECISION-JOBS@1',job_id='stale-protected',attempt_id='original-protected',source=asdict(source),
            decision=dict(trip_id=trip_id,expected_version=trip['version'],content_sha256=sha256(packed(trip['content'])).hexdigest()),end=None))
        with TestClient(c_app) as client:self.assertEqual(client.post('/internal/v1/memory-decision/jobs',content=raw,headers=headers).status_code,200)
        c.begin_decision(token,'stale-protected','original-protected')
        data=c.prepare_decision_input(token,'stale-protected','original-protected',max_payload_bytes=262144)
        digest=json.loads(json.loads(data)['messages'][0]['content'])['decision_source_sha256']
        jobs=BackgroundJobsV3(database=host.database,boundary=host.boundary,collection=DecisionCollectionAdapter(c),max_payload_bytes=262144)
        original=jobs.prepare(token,JobRequestV3('stale-protected','original-protected',source,None,data,digest))
        with TestClient(app) as client:
            prepared=self.prepare_request(client,subject,self.edit_request(subject,trip,'after-bg3-prepare'))
            saved=self.save_request(client,subject,prepared,'advance-protected-trip')
            self.assertEqual(saved.status_code,200,saved.text)
            self.assertEqual(saved.json()['receipt']['committed_version'],trip['version']+1)
        provider=DecisionFake();outcomes=run_worker.run_once(current,provider,auth,background_jobs=LocalBackgroundHost(jobs,auth))
        self.assertEqual([o.status for o in outcomes],['unknown']);self.assertEqual(provider.calls,0)
        self.assertEqual(jobs.query_original(token,'stale-protected','original-protected')['meter_attempt_id'],original['meter_attempt_id'])
        with psycopg.connect(**json.loads(path.read_text())) as audit:
            ledger=audit.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=(SELECT ledger_scope FROM cj_run_background_job WHERE run_id=%s)',(original['run_id'],)).fetchone()[0]
            self.assertNotIn(original['meter_attempt_id'],ledger['attempts'])
        self.assertEqual(run_worker.run_once(current,provider,auth,background_jobs=LocalBackgroundHost(jobs,auth)),[])
        print('PASS genuine NEEDS producer→signed Trip accept→MSG3→BG3 prepare→signed source-bound Trip edit/save: old BG3 has zero claim/provider and cannot redispatch')


if __name__=='__main__':unittest.main(defaultTest='ProtectedDecisionChecks.test_real_trip_update_refuses_original_bg3' if os.environ['BG3_CASE']=='stale' else 'BackgroundV3Checks.test_actual_original_bg3',verbosity=2)
