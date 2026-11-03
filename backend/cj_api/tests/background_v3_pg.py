"""Actual BG3 writer/worker/Meter on a genuine accepted Trip discussion."""
from dataclasses import asdict,replace
from datetime import datetime,timedelta,timezone
from hashlib import sha256
from pathlib import Path
import json,os,sys,tempfile,subprocess,unittest
from unittest.mock import patch
import psycopg
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[3];sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'backend/trip/tests')]
import pg_suites,migrate,manual_pg as manual,local_run_context,dev_auth,message_trip_profile,run_worker
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
            return req,jobs.prepare(token,req)
        request,original=prepare(chats[0],'decision-job')
        # Real compatibility isolation: no BG2 preparation/outflow or default
        # runtime visibility of the new row; initializer sees its true header.
        wrong=BackgroundJobsV2(database=host.database,boundary=host.boundary,collection=DecisionCollectionAdapter(c),max_payload_bytes=262144)
        with self.assertRaises(TypeError):wrong.prepare(token,JobRequest(request.job_id,request.attempt_id,request.query,None,request.prepared_input))
        with database.connect(self.owner) as conn:self.assertEqual(conn.execute('SELECT count(*) FROM cj_run_background_job').fetchone(),(0,))
        with psycopg.connect(**json.loads(path.read_text())) as audit:
            self.assertEqual(audit.execute('SELECT protocol,decision_source_sha256 FROM cj_run_background_job WHERE run_id=%s',(original['run_id'],)).fetchone(),('RUN-BACKGROUND@3',request.decision_source_sha256))
        class Model(DecisionFake):
            def stream(model,messages,system=None):
                if case=='unknown':model.calls+=1;raise ProviderFailed('synthetic original outcome unknown')
                if case=='time':tick[0]+=10
                yield from super().stream(messages,system)
        model=Model();worker=LocalBackgroundHost(jobs,self.auth)
        if case=='cancel':
            self.assertEqual(jobs.cancel(token,request.job_id,request.attempt_id)['state'],'cancelled')
        if case=='stale':
            with TestClient(self.app) as client:
                prepared=self.prepare(client);saved=self.write(client,'/v1/trip-manual-saves',self.save(prepared))
                self.assertEqual(saved.status_code,200,saved.text)
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
                  'tail':'budget_exhausted','budget':'budget_exhausted','stale':'unknown','cancel':None}[case]
        if expected is None:self.assertEqual(results,[])
        else:self.assertEqual([r.status for r in results],[expected],results)
        self.assertEqual(model.calls,0 if case in ('budget','stale','cancel') else 1)
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
            if case in ('budget','stale','cancel'):self.assertIsNone(attempt)
            else:
                self.assertEqual(ledger['runs'][original['run_id']]['steps'],1);self.assertEqual(ledger['runs'][original['run_id']]['tools'],0)
                self.assertEqual(attempt['state'],'unknown' if case in ('unknown','output','time') else 'settled')
                if case in ('unknown','output','time'):self.assertIsNone(attempt['receipt'])
                else:self.assertEqual(attempt['receipt']['actual'],1)
            if case not in ('success','ack'):
                self.assertEqual(audit.execute('SELECT count(*) FROM cj_memory_item WHERE scope=%s',(self.owner,)).fetchone(),(0,))
        print('PASS BG3 actual '+case+': signed accepted/modified Trip + MSG3/C holder + original run_once/unique Meter/Fake, Pub3/digest and original financial outcome')


if __name__=='__main__':unittest.main(defaultTest='BackgroundV3Checks.test_actual_original_bg3',verbosity=2)
