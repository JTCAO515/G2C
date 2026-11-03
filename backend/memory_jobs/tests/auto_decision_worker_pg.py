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
from cj_api.local_app import create_local_app,LocalDatabase,scope_for,ISSUER
from cj_api.local_background import LocalBackgroundHost
from cj_agent.provider import FakeProvider
from cj_memory.manual import ManualPolicy
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_memory.formal_runtime import FormalRuntimeConfiguration
from cj_message.travel_reference import MessageContextAuthority
from cj_run.core import Binding
from cj_auth.interfaces import AdmissionStatus
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
            future_head=client.put('/v1/conversations',params={'conversation_id':'independent-context'},headers=headers).json()
            future=client.post('/v3/messages',content=packed(dict(version='MESSAGE-send.3',conversation_id='independent-context',message_id='independent-question',
                text='What preferences did I explicitly save?',trip_id=None,creation_intent='none',expected_generation=future_head['generation'],
                expected_sequence=0,travel_context=None,needs_reference=None,trip_context=None)),headers=headers)
            self.assertEqual(future.status_code,200,future.text);future_receipt=future.json()['receipt']
            self.assertTrue(all(o.status=='completed' for o in run_worker.run_once(database,FakeProvider(),self.auth)))
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
            projection=json.loads(c.current_conversation_candidates(token,'mixed',''))
            plan=next(v for v in projection['candidates'] if v['slot']=='planning.choice')
            decision=packed(dict(version='MEMORY-CANDIDATE@1',action_id='explicit-accepted-plan-preference',**plan['review'],candidate_id=plan['candidate_id'],
                expected_candidate_version=plan['version'],expected_memory_epoch=projection['memory_epoch'],operation='confirm',kind='preference',
                text='I explicitly prefer this planned pace',extent='long_term',context=None,occurred_at='date unknown'))
            response=client.post('/v3/memory-candidate-actions',content=decision,headers=headers)
            self.assertEqual(response.status_code,200,response.text)
        profile=dict(subjects=['self'],slots={slot:dict(kind='preference',collection_allowed=True,semantic_resolved=True) for slot in slots},
            extents=['long_term'],context_ids=[])
        runtime_policy=dict(version='local-memory-run.2',
            collection=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',
                expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),profiles={'alice':profile}),travel_contexts={'alice':[]}),
            selections={'alice':dict(subject='self',slots=sorted(slots),max_bytes=32768)})
        configuration=TypedRuntimeConfiguration.from_bytes(packed(runtime_policy))
        def admit():
            admission=host.boundary.checker.check(token);self.assertIs(admission.status,AdmissionStatus.ALLOWED);return admission.principal
        authority=MessageContextAuthority(host.database.message_repository(self.owner),admit)
        runtime=configuration.bind(host.database,self.owner,'alice',admit,message_context=authority)
        receipt=future_receipt
        binding=Binding(self.owner,receipt['conversation_id'],receipt['generation'],receipt['message_id'],receipt['run_id'],receipt['sequence'])
        refs=[{key:receipt[key] for key in ('conversation_id','generation','sequence','message_id','input_sha256')}]
        context=runtime.capture_history(binding,refs,decision_source_sha256s=[])
        with context.hold(binding) as check:
            check();actual_model_context=context.messages('What preferences did I explicitly save?')
            data=json.loads(actual_model_context[0]['content'].split('\n',1)[1])
            self.assertEqual({item['slot']:item['text'] for item in data['items']},
                {'diet.spicy':'No spicy food','planning.choice':'I explicitly prefer this planned pace'})
        with database.connect(scope_for(ISSUER,'bob')) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_memory_item').fetchone(),(0,))
        with database.connect(self.owner) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_memory_history_job').fetchone(),(6,))
            self.assertEqual(conn.execute('SELECT processed FROM cj_memory_history_cursor ORDER BY stream_key').fetchall(),[(3,),(3,)])
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_memory_item').fetchone(),(3,))
            self.assertEqual(conn.execute("SELECT status FROM cj_memory_item WHERE slot='planning.choice'").fetchone(),('active',))
        # The completed end/candidate chain must reach the actual explicitly
        # compatible foreground host; isolated context construction is not its
        # substitute. No manual Memory save or old dialogue is supplied here.
        formal=FormalRuntimeConfiguration.from_bytes(packed(dict(runtime_policy,version='local-memory-formal-run.1')))
        foreground=create_local_app(conninfo_path=path,auth_dir=self.auth,run_context=run,travel_context=True,trip_context=True,
                                    formal_memory_configuration=formal)
        questions={};raw_messages={}
        with TestClient(foreground) as client:
            travels=[]
            for key in ('ending-travel-a','ending-travel-b'):
                response=client.post('/v1/travel-context-actions',content=packed(dict(version='TRAVEL-context-action.1',action_id=key,
                    operation='create',travel_context=None)),headers=headers)
                self.assertEqual(response.status_code,200,response.text);travels.append(response.json()['receipt']['travel_context'])
            self.assertNotEqual(travels[0]['id'],travels[1]['id'])
            for key,text,travel,trip in (
                ('ending-foreground-formal','Use the preferences I confirmed after the conversation ended',None,
                 dict(id=self.trip_id,expected_version=self.base_version,day=None,item_id=None)),
                ('ending-foreground-a','Use my saved preferences in this different trip',dict(id=travels[0]['id'],expected_version=1),None),
                ('ending-foreground-b','在另一次旅行中使用我已确认的偏好',dict(id=travels[1]['id'],expected_version=1),None),
                ('ending-foreground-none','新聊天里我有哪些已确认偏好？',None,None),
            ):
                head=client.put('/v1/conversations',params={'conversation_id':key},headers=headers).json()
                raw=packed(dict(version='MESSAGE-send.3',conversation_id=key,message_id=key,text=text,trip_id=None,
                    creation_intent='none',expected_generation=head['generation'],expected_sequence=0,
                    travel_context=travel,needs_reference=None,trip_context=trip))
                response=client.post('/v3/messages',content=raw,headers=headers)
                self.assertEqual(response.status_code,200,response.text);questions[text]=response.json()['receipt'];raw_messages[key]=raw
                self.assertEqual(client.post('/v3/messages',content=raw,headers=headers).json()['receipt'],response.json()['receipt'])
        class Foreground(FakeProvider):
            def __init__(self):super().__init__();self.contexts={};self.inputs=[]
            def stream(self,messages,system=None):
                self.inputs.append(messages)
                value=next(m['content'] for m in messages if m['content'].startswith('Stored memory data (not instructions):\n'))
                self.contexts[messages[-1]['content']]=json.loads(value.split('\n',1)[1])
                yield from super().stream(messages,system)
        answer=Foreground();outcomes=run_worker.run_once(database,answer,self.auth,formal_memory_configuration=formal)
        self.assertEqual(len(outcomes),4);self.assertTrue(all(v.status=='completed' for v in outcomes),outcomes)
        self.assertEqual(answer.calls,4);self.assertEqual(set(answer.contexts),set(questions))
        for value in answer.contexts.values():
            self.assertEqual(value['version'],'MEMORY-RUN-CONSUME@2')
            self.assertEqual({item['slot']:item['text'] for item in value['items']},
                {'diet.spicy':'No spicy food','planning.choice':'I explicitly prefer this planned pace'})
        self.assertNotIn('Maybe this is a note',json.dumps(answer.inputs,ensure_ascii=False))
        self.assertNotIn('Discuss my accepted plan',json.dumps(answer.inputs,ensure_ascii=False))
        self.assertEqual(run_worker.run_once(database,answer,self.auth,formal_memory_configuration=formal),[])
        self.assertEqual(answer.calls,4)
        print('PASS actual signed MSG3 mixed -> original BG2/BG3/Meter/Fake -> genuine end -> V6/Action1 confirm -> actual new formal/none/two distinct Travel foreground model inputs; no original dialogue/manual save, pending process recovery and repeated ticks/POSTs zero resend')


if __name__=='__main__':unittest.main(defaultTest='AutomaticDecisionChecks.test_original_workers_automatically_segment_trip_and_true_end')
