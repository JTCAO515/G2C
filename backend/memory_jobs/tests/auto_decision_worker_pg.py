"""Automatic mixed history/accepted Trip/end on original BG2/3 workers."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
import base64,json,sys,unittest,subprocess
from pathlib import Path

import psycopg
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend/trip/tests'),str(ROOT/'scripts')]
import manual_pg as manual
import dev_auth,local_run_context,message_trip_profile,run_worker
from cj_api.local_app import create_local_app,LocalDatabase
from cj_api.local_background import LocalBackgroundHost
from cj_agent.provider import FakeProvider
from cj_memory.manual import ManualPolicy
from cj_memory_jobs.extraction import CollectionPolicy
from cj_memory_jobs.collection_app import create_automatic_decision_collection_app
from cj_memory_jobs.decision_producer import DecisionConversationProducer
from cj_memory_jobs.producer import ProducerHost
from cj_memory_jobs.worker_adapter import MemoryCollectionAdapterV2
from cj_memory_jobs.decision_service import DecisionCollectionAdapter
from cj_memory_jobs.decision_command import DecisionCommand
from cj_run.background import BackgroundJobsV2
from cj_run.background_v3 import BackgroundJobsV3
from cj_run.background_store import JobRequest
from cj_run.background_store_v3 import JobRequestV3
from cj_trip.domain import packed


class Model(FakeProvider):
    def __init__(self):super().__init__();self.data=[]
    def stream(self,messages,system=None):
        self.calls+=1;data=json.loads(messages[0]['content']);self.data.append(data)
        if data['version']=='MEMORY-EXTRACT-DATA@3':
            ref=data['trip_decisions'][0];kind='experience';slot='planning.choice';text='An accepted plan, never a visit'
            evidence=[dict(ref=ref['ref'],quote=json.loads(ref['document'])['title'])];version='MEMORY-EXTRACT@3'
        else:
            assert data['version']=='MEMORY-EXTRACT-DATA@2'
            message=data['messages'][0];text=message['text']
            kind,slot=('preference','diet.spicy') if text=='No spicy food' else ('inference','note')
            evidence=[dict(ref=message['ref'],quote=text)];version='MEMORY-EXTRACT@2'
        yield packed(dict(version=version,entries=[dict(subject='self',slot=slot,kind=kind,text=text,extent='long_term',
            occurred_at='date unknown',evidence=evidence)])).decode()


class AutomaticDecisionChecks(manual.ManualChecks):
    def test_original_workers_automatically_segment_trip_and_true_end(self):
        path=Path(manual.CONNINFO);run=self.run_context
        local_run_context.provision_budget(path,run,'alice')
        dev_auth.activate_travel(path,'alice',run,'MESSAGE-TRAVEL-CONSUMER@1')
        message_trip_profile.activate(path,'alice',run,'MESSAGE-TRIP-CONSUMER@1')
        app=create_local_app(conninfo_path=path,auth_dir=self.auth,run_context=run,travel_context=True,trip_context=True)
        database=LocalDatabase(path,run_context=run,travel_context=True,trip_context=True)
        headers={**self.headers('alice'),'Content-Type':'application/octet-stream'};token=headers['Authorization'][7:]
        with TestClient(app) as client:
            head=client.put('/v1/conversations',params={'conversation_id':'mixed'},headers=headers).json()
            for index,text in enumerate(('No spicy food','Discuss my accepted plan','Maybe this is a note')):
                selection=None if index!=1 else dict(id=self.trip_id,expected_version=self.base_version,day=None,item_id=None)
                response=client.post('/v3/messages',content=packed(dict(version='MESSAGE-send.3',conversation_id='mixed',message_id='mixed-'+str(index),
                    text=text,trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=index,
                    travel_context=None,needs_reference=None,trip_context=selection)),headers=headers)
                self.assertEqual(response.status_code,200,response.text)
                outcomes=run_worker.run_once(database,FakeProvider(),self.auth)
                self.assertTrue(all(o.status=='completed' for o in outcomes),outcomes)
        slots=frozenset({'diet.spicy','planning.choice','note'})
        extraction=CollectionPolicy(frozenset({'self'}),slots,5,4096,lambda e:True,lambda e,rows:e.kind=='preference')
        memory=ManualPolicy(extraction.subjects,slots,frozenset({'long_term'}),frozenset(),
            datetime.now(timezone.utc)+timedelta(hours=1),lambda c,r:True,lambda c,r:True)
        resolver=lambda p:(extraction,memory,lambda e:(None,None))
        c_app=create_automatic_decision_collection_app(conninfo_path=path,auth_dir=self.auth,run_context=run,resolve_collection=resolver)
        host=c_app.state.memory_history;c=host.service
        bg2=BackgroundJobsV2(database=host.database,boundary=host.boundary,collection=MemoryCollectionAdapterV2(c),max_payload_bytes=262144)
        bg3=BackgroundJobsV3(database=host.database,boundary=host.boundary,collection=DecisionCollectionAdapter(c),max_payload_bytes=262144)
        originals=[]
        def submit(token,jid,attempt,query,data):
            result=bg2.prepare(token,JobRequest(jid,attempt,query,None,data));originals.append(result);return result
        def submit_decision(token,jid,attempt,query,digest,data):
            result=bg3.prepare(token,JobRequestV3(jid,attempt,query,None,data,digest));originals.append(result);return result
        class Both:
            def run_once(self,provider):
                return LocalBackgroundHost(bg2,self.auth).run_once(provider)+LocalBackgroundHost(bg3,self.auth).run_once(provider)
        both=Both();both.auth=self.auth
        producer=DecisionConversationProducer(c,submit,submit_decision,max_payload_bytes=262144,max_conversations=100)
        combined=ProducerHost(producer,lambda:[dev_auth.token(self.auth,'alice',5)],both)
        model=Model()
        self.assertEqual(run_worker.run_once(database,model,self.auth,background_jobs=combined),[])
        self.assertEqual(model.calls,0)
        with TestClient(c_app) as client:
            response=client.post('/v3/memory-history-actions',content=packed(dict(version='MEMORY-HISTORY@1',action_id='enable-mixed',operation='enable',
                conversation_id='mixed',expected_generation=head['generation'],expected_epoch=0,expected_source_version=0)),headers=headers)
            self.assertEqual(response.status_code,200,response.text)
            for _ in range(3):
                results=run_worker.run_once(database,model,self.auth,background_jobs=combined)
                self.assertEqual(len(results),1);self.assertEqual(results[0].status,'completed',results)
            self.assertEqual([d['version'] for d in model.data],['MEMORY-EXTRACT-DATA@2','MEMORY-EXTRACT-DATA@3','MEMORY-EXTRACT-DATA@2'])
            self.assertEqual([len(d['messages']) for d in model.data],[1,1,1])
            self.assertEqual(producer.ending._plan(token),[])
            response=client.post('/internal/v1/conversation-end',content=packed(dict(version='MESSAGE-SOURCE@1',conversation_id='mixed',
                generation=head['generation'],epoch=0,through=3,conversation_type='travel')),headers=headers)
            self.assertEqual(response.status_code,200,response.text);end=response.json()['end']
            results=run_worker.run_once(database,model,self.auth,background_jobs=combined)
            self.assertEqual(results[0].status,'completed',results)
            pending=producer.ending._plan(token);self.assertEqual(len(pending),1)
            raw=base64.b64decode(pending[0]);command=DecisionCommand.parse(raw)
            c.enqueue_decision_serialized(token,raw)
            rebuilt=DecisionConversationProducer(c,submit,submit_decision,max_payload_bytes=262144,max_conversations=100)
            self.assertEqual(rebuilt.ending._plan(token),pending)
            new_process=subprocess.run([sys.executable,'-B',str(ROOT/'backend/memory_jobs/tests/auto_decision_plan_probe.py'),
                str(path),str(self.auth)],capture_output=True,text=True)
            self.assertEqual(new_process.returncode,0,new_process.stdout+new_process.stderr)
            self.assertEqual(json.loads(new_process.stdout),pending)
            combined=ProducerHost(rebuilt,lambda:[dev_auth.token(self.auth,'alice',5)],both)
            for _ in range(2):
                results=run_worker.run_once(database,model,self.auth,background_jobs=combined)
                self.assertEqual(results[0].status,'completed',results)
            self.assertEqual([d['purpose'] for d in model.data],['incremental']*3+['conversation_end']*3)
            self.assertEqual([d['end_ref'] for d in model.data[3:]],[end['end_id']]*3)
            self.assertEqual(run_worker.run_once(database,model,self.auth,background_jobs=combined),[])
            self.assertEqual(model.calls,6);self.assertEqual(len(originals),6)
            self.assertEqual(len({r['run_id'] for r in originals}),6)
            self.assertEqual(len({r['meter_attempt_id'] for r in originals}),6)
        with database.connect(self.owner) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_memory_history_job').fetchone(),(6,))
            self.assertEqual(conn.execute('SELECT processed FROM cj_memory_history_cursor ORDER BY stream_key').fetchall(),[(3,),(3,)])
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_memory_item').fetchone(),(3,))
            self.assertEqual(conn.execute("SELECT status FROM cj_memory_item WHERE slot='planning.choice'").fetchone(),('candidate',))
        print('PASS actual signed MSG3 mixed range -> automatic BG2/BG3 original workers/Meter/Fake -> true end segments; pending D3 restart exact bytes/IDs, six unique original attempts, repeat tick zero resend; foreground new MSG+Memory still separate')


if __name__=='__main__':unittest.main(defaultTest='AutomaticDecisionChecks.test_original_workers_automatically_segment_trip_and_true_end')
