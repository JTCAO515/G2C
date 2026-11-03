"""Actual shared BG3/queued-copy erasure; requires fixed B public M45 hooks."""
from datetime import datetime,timedelta,timezone
import json,sys,unittest
from pathlib import Path
from unittest.mock import patch
import psycopg

from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend/trip/tests'),str(ROOT/'scripts')]
import manual_pg as manual
import dev_auth,message_trip_profile,local_run_context,run_worker
from cj_api.local_app import create_local_app,LocalDatabase
from cj_api.local_cleanup import Configuration
from cj_api.local_background import LocalBackgroundHost
from cj_agent.provider import FakeProvider
from cj_message.auth_boundary import HistoryReadContext
from cj_message.domain import Unavailable as MessageUnavailable
from cj_memory.manual import ManualPolicy
from cj_memory_jobs.extraction import CollectionPolicy
from cj_memory_jobs.collection_app import create_automatic_decision_collection_app
from cj_memory_jobs.decision_producer import DecisionConversationProducer
from cj_memory_jobs.decision_service import DecisionCollectionAdapter
from cj_memory_withdrawal.erasure_app import create_erasure_app_v2
from cj_memory_withdrawal.erasure_service import ORDER
from cj_cleanup.memory_payloads import hooks,hold_payloads
from cj_run.background_v3 import BackgroundJobsV3
from cj_run.background_store_v3 import JobRequestV3
from cj_run.step_usage import ledger_scope_for
from cj_trip.domain import packed


class TwoEntries(FakeProvider):
    def stream(self,messages,system=None):
        self.calls+=1;data=json.loads(messages[0]['content']);assert data['version']=='MEMORY-EXTRACT-DATA@3'
        decision=data['trip_decisions'][0];title=json.loads(decision['document'])['title']
        yield packed(dict(version='MEMORY-EXTRACT@3',entries=[dict(subject='self',slot=slot,kind='inference',
            text='Only an accepted planning decision: '+slot,extent='long_term',occurred_at='date unknown',
            evidence=[dict(ref=decision['ref'],quote=title)]) for slot in ('planning.first','planning.second')])).decode()


class SharedDecisionErasureChecks(manual.ManualChecks):
    def test_actual_shared_completed_and_queued_copies_delete_twice_without_revival(self):
        path=Path(manual.CONNINFO);run=self.run_context
        local_run_context.provision_budget(path,run,'alice');dev_auth.activate_travel(path,'alice',run,'MESSAGE-TRAVEL-CONSUMER@1')
        message_trip_profile.activate(path,'alice',run,'MESSAGE-TRIP-CONSUMER@1')
        ingress=create_local_app(conninfo_path=path,auth_dir=self.auth,run_context=run,travel_context=True,trip_context=True)
        database=LocalDatabase(path,run_context=run,travel_context=True,trip_context=True)
        headers={**self.headers('alice'),'Content-Type':'application/octet-stream'};token=headers['Authorization'][7:]
        heads={}
        with TestClient(ingress) as client:
            for cid in ('a-origin','b-copy','c-queued'):
                head=client.put('/v1/conversations',params={'conversation_id':cid},headers=headers).json();heads[cid]=head
                response=client.post('/v3/messages',content=packed(dict(version='MESSAGE-send.3',conversation_id=cid,message_id=cid,
                    text='Discuss an accepted plan, not a visit',trip_id=None,creation_intent='none',expected_generation=head['generation'],
                    expected_sequence=0,travel_context=None,needs_reference=None,
                    trip_context=dict(id=self.trip_id,expected_version=self.base_version,day=None,item_id=None))),headers=headers)
                self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(all(o.status=='completed' for o in run_worker.run_once(database,FakeProvider(),self.auth)))
        slots=frozenset({'planning.first','planning.second'})
        policy=CollectionPolicy(frozenset({'self'}),slots,5,4096,lambda e:True,lambda e,rows:False)
        memory=ManualPolicy(policy.subjects,slots,frozenset({'long_term'}),frozenset(),datetime.now(timezone.utc)+timedelta(hours=1),
                            lambda c,r:True,lambda c,r:True)
        resolve=lambda p:(policy,memory,lambda e:(None,None))
        app=create_automatic_decision_collection_app(conninfo_path=path,auth_dir=self.auth,run_context=run,resolve_collection=resolve)
        host=app.state.memory_history;c=host.service
        jobs=BackgroundJobsV3(database=host.database,boundary=host.boundary,collection=DecisionCollectionAdapter(c),max_payload_bytes=262144)
        originals=[]
        def no_legacy(*args):raise AssertionError('formal source was silently downgraded')
        def submit(token,jid,attempt,query,digest,data):
            result=jobs.prepare(token,JobRequestV3(jid,attempt,query,None,data,digest));originals.append(result);return result
        producer=DecisionConversationProducer(c,no_legacy,submit,max_payload_bytes=262144,max_conversations=100)
        for cid,head in heads.items():
            c.apply_consent(token,packed(dict(version='MEMORY-HISTORY@1',action_id='enable-'+cid,operation='enable',conversation_id=cid,
                expected_generation=head['generation'],expected_epoch=0,expected_source_version=0)))
        model=TwoEntries();background=LocalBackgroundHost(jobs,self.auth)
        for _ in range(2):
            self.assertEqual(len(producer.poll(token).submitted),1)
            self.assertEqual([o.status for o in run_worker.run_once(database,model,self.auth,background_jobs=background)],['completed'])
        self.assertEqual(model.calls,2)
        self.assertEqual(len(producer.poll(token).submitted),1)  # Actual B queued header, zero provider claim.
        self.assertEqual(len(originals),3)
        account=ledger_scope_for(self.owner,run.current.meter)
        with psycopg.connect(**json.loads(path.read_text())) as audit:
            original_ledger=audit.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()[0]
            self.assertNotIn(originals[-1]['meter_attempt_id'],original_ledger['attempts'])
        projection=json.loads(c.current_conversation_candidates(token,'a-origin',''))
        self.assertEqual(len(projection['candidates']),2)
        selected,other=sorted(projection['candidates'],key=lambda v:v['slot'])
        with host.database.connect(self.owner) as conn:
            formal=conn.execute('SELECT trip_id,version,content FROM cj_trip_record ORDER BY trip_id').fetchall()
            chat=conn.execute('SELECT message_id,raw_input,input_sha256 FROM cj_message_receipt ORDER BY message_id').fetchall()
        registry=Path(self.tmp.name)/'shared-memory-registry.json'
        registry.write_bytes(packed(dict(version='actual-shared-bg3-erasure-component',stores=[dict(id='memory-derived',cleanup_protocol='CLEANUP@1.1'),
            dict(id='checkpoints',objects=[dict(id='run',cleanup_protocol='CLEANUP@1.1')]),
            dict(id='business',objects=[dict(id=t.split('/')[1],cleanup_protocol='CLEANUP@1.1') for t in ORDER if t.startswith('business/')])])) )
        configuration=Configuration({'local':b'shared-bg3-synthetic-erasure-key'},'local',3600,ORDER,registry)
        erasure=create_erasure_app_v2(conninfo_path=path,auth_dir=self.auth,resolve_collection=resolve,run_context=run,
            cleanup_configuration=configuration,resolve_backend_hooks=hooks,hold_payloads=hold_payloads)
        def delete(client,item,aid):
            raw=packed(dict(version='MEMORY-ERASURE@1',action_id=aid,item_id=item['candidate_id'],expected_version=item['version'],
                            derived_range='owned_trip_derived_scope'))
            response=client.post('/v1/memory-erasures',content=raw,headers=headers)
            self.assertEqual(response.status_code,200,response.text);value=response.json()['result']
            self.assertEqual(value['online_status'],'complete',value);return raw,value
        with TestClient(erasure) as client:
            first_raw,first=delete(client,selected,'erase-first-shared')
            with psycopg.connect(**json.loads(path.read_text())) as audit:
                self.assertEqual(audit.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()[0],original_ledger)
            with host.database.connect(self.owner) as conn:
                self.assertEqual(conn.execute('SELECT count(*) FROM cj_memory_history_job').fetchone(),(0,))
                self.assertEqual(conn.execute('SELECT count(*) FROM cj_memory_erasure_manifest').fetchone(),(0,))
                self.assertEqual(conn.execute('SELECT trip_id,version,content FROM cj_trip_record ORDER BY trip_id').fetchall(),formal)
                self.assertEqual(conn.execute('SELECT message_id,raw_input,input_sha256 FROM cj_message_receipt ORDER BY message_id').fetchall(),chat)
            for original in originals:
                record=jobs.query_original(token,original['job_id'],original['attempt_id'])
                self.assertEqual(record['input_state'],'erased');self.assertEqual(record['meter_attempt_id'],original['meter_attempt_id'])
            self.assertEqual(run_worker.run_once(database,model,self.auth,background_jobs=background),[]);self.assertEqual(model.calls,2)
            current=json.loads(c.current_conversation_candidates(token,'a-origin',''))
            self.assertEqual([v['candidate_id'] for v in current['candidates']],[other['candidate_id']])
            other=current['candidates'][0]
            action=packed(dict(version='MEMORY-CANDIDATE@1',action_id='confirm-retained-shared',**other['review'],candidate_id=other['candidate_id'],
                expected_candidate_version=other['version'],expected_memory_epoch=current['memory_epoch'],operation='confirm',kind='preference',
                text='An explicit new reviewed preference',extent='long_term',context=None,occurred_at='date unknown'))
            confirmed=json.loads(c.apply_candidate(token,action));self.assertEqual(confirmed['receipt']['status'],'active')
            other['version']=confirmed['receipt']['version']
            second_raw,second=delete(client,other,'erase-retained-later')
            self.assertNotEqual(first['operation_id'],second['operation_id'])
            self.assertEqual(client.post('/v1/memory-erasures',content=second_raw,headers=headers).json()['result']['online_status'],'complete')
            self.assertEqual(client.post('/v1/memory-erasures',content=first_raw,headers=headers).json()['result']['online_status'],'complete')
        with psycopg.connect(**json.loads(path.read_text())) as audit:
            self.assertEqual(audit.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()[0],original_ledger)
        rebuilt=create_automatic_decision_collection_app(conninfo_path=path,auth_dir=self.auth,run_context=run,resolve_collection=resolve)
        restored=DecisionConversationProducer(rebuilt.state.memory_history.service,no_legacy,submit,
            max_payload_bytes=262144,max_conversations=100)
        for current_producer in (producer,restored):
            self.assertEqual(current_producer.poll(token).submitted,())
        for error in (MessageUnavailable('original erasure proof unavailable'),RuntimeError('proof reader failed')):
            with patch.object(HistoryReadContext,'history_reference_v5',side_effect=error):
                with self.assertRaises(type(error)):
                    restored.poll(token)
        self.assertEqual(len(originals),3)
        with host.database.connect(self.owner) as conn:
            for table in ('cj_memory_item','cj_memory_source','cj_memory_operation','cj_memory_history_origin',
                          'cj_memory_history_candidate_action','cj_memory_history_job','cj_memory_erasure_manifest'):
                self.assertEqual(conn.execute('SELECT count(*) FROM '+table).fetchone(),(0,),table)
            self.assertEqual(conn.execute('SELECT trip_id,version,content FROM cj_trip_record ORDER BY trip_id').fetchall(),formal)
        self.assertEqual(run_worker.run_once(database,model,self.auth,background_jobs=background),[]);self.assertEqual(model.calls,2)
        print('PASS real shared BG3 two candidates/cross-chat/queued header: signed erasure clears all old job copies with zero queued provider, retains other V6/Action1, subsequent erase uses original B/C hash proof, chat/formal Trip preserved, original repeat no redispatch')


if __name__=='__main__':unittest.main(defaultTest='SharedDecisionErasureChecks.test_actual_shared_completed_and_queued_copies_delete_twice_without_revival')
