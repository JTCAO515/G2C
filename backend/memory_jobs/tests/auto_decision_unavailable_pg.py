"""Real unavailable source actions must not starve an independent source."""
from datetime import datetime,timedelta,timezone
import json,sys,unittest
from pathlib import Path
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend/trip/tests'),str(ROOT/'scripts')]
import manual_pg as manual,needs_actions_pg as needs
import message_trip_profile,local_run_context,dev_auth,run_worker
from cj_api.local_app import create_local_app,LocalDatabase,scope_for,ISSUER
from cj_api.local_background import LocalBackgroundHost
from cj_agent.provider import FakeProvider
from cj_trip.domain import packed
from cj_trip.auth_boundary import Boundary as TripBoundary
from cj_memory.manual import ManualPolicy
from cj_memory_jobs.extraction import CollectionPolicy
from cj_memory_jobs.collection_app import create_automatic_decision_collection_app
from cj_memory_jobs.decision_producer import DecisionConversationProducer
from cj_memory_jobs.worker_adapter import MemoryCollectionAdapterV2
from cj_memory_jobs.decision_service import DecisionCollectionAdapter
from cj_run.background import BackgroundJobsV2
from cj_run.background_v3 import BackgroundJobsV3
from cj_run.background_store import JobRequest
from cj_run.background_store_v3 import JobRequestV3
from auto_decision_worker_pg import Model


def pipeline(path,auth,run):
    slots=frozenset({'planning.choice','diet.spicy','note'})
    extraction=CollectionPolicy(frozenset({'self'}),slots,5,4096,lambda e:True,lambda e,rows:True)
    memory=ManualPolicy(extraction.subjects,slots,frozenset({'long_term'}),frozenset(),
        datetime.now(timezone.utc)+timedelta(hours=1),lambda c,r:True,lambda c,r:True)
    app=create_automatic_decision_collection_app(conninfo_path=path,auth_dir=auth,run_context=run,
        resolve_collection=lambda p:(extraction,memory,lambda e:(None,None)))
    host=app.state.memory_history;c=host.service;records=[]
    bg2=BackgroundJobsV2(database=host.database,boundary=host.boundary,collection=MemoryCollectionAdapterV2(c),max_payload_bytes=262144)
    bg3=BackgroundJobsV3(database=host.database,boundary=host.boundary,collection=DecisionCollectionAdapter(c),max_payload_bytes=262144)
    def submit(token,jid,attempt,query,data):
        row=bg2.prepare(token,JobRequest(jid,attempt,query,None,data));records.append(row);return row
    def decision(token,jid,attempt,query,digest,data):
        row=bg3.prepare(token,JobRequestV3(jid,attempt,query,None,data,digest));records.append(row);return row
    producer=DecisionConversationProducer(c,submit,decision,max_payload_bytes=262144,max_conversations=100)
    class Both:
        def run_once(self,provider):return LocalBackgroundHost(bg2,auth).run_once(provider)+LocalBackgroundHost(bg3,auth).run_once(provider)
    return app,c,producer,Both(),records


def send(case,client,headers,cid,trip_id,version):
    head=client.put('/v1/conversations',params={'conversation_id':cid},headers=headers).json()
    response=client.post('/v3/messages',content=packed(dict(version='MESSAGE-send.3',conversation_id=cid,message_id=cid,text='No spicy food',
        trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=0,travel_context=None,needs_reference=None,
        trip_context=None if trip_id is None else dict(id=trip_id,expected_version=version,day=None,item_id=None))),headers=headers)
    case.assertEqual(response.status_code,200,response.text);return head


def enable(service,token,cid,head):
    service.apply_consent(token,packed(dict(version='MEMORY-HISTORY@1',action_id='enable-'+cid,operation='enable',conversation_id=cid,
        expected_generation=head['generation'],expected_epoch=0,expected_source_version=0)))


class AdvancedDecisionChecks(needs.NeedsActionChecks):
    def test_formal_version_advance_before_enqueue_reports_and_progresses(self):
        subject='manual';app,outcome,_=self.plan(subject);run=self.host.profiles[subject][1];auth=self.host.auth;path=Path(manual.CONNINFO)
        headers={**self.host.headers[subject],'Content-Type':'application/octet-stream'};token=headers['Authorization'][7:]
        with TestClient(app) as client:
            accepted=self.post(client,subject,self.action(subject,outcome,'accept'));self.assertEqual(accepted.status_code,200,accepted.text)
            trip_id=accepted.json()['receipt']['trip_id'];trip=client.get('/v4/trip-structured',params={'trip_id':trip_id},headers=headers).json()['trip']
        message_trip_profile.activate(path,subject,run,'MESSAGE-TRIP-CONSUMER@1')
        ingress=create_local_app(conninfo_path=path,auth_dir=auth,run_context=run,travel_context=True,trip_context=True,needs_profile='manual-v1')
        database=LocalDatabase(path,run_context=run,travel_context=True,trip_context=True,needs_context=True)
        with TestClient(ingress) as client:
            heads={cid:send(self,client,headers,cid,selected,trip['version']) for cid,selected in [('a-stale',trip_id),('z-independent',None)]}
        self.assertTrue(all(r.status=='completed' for r in run_worker.run_once(database,FakeProvider(),auth)))
        with TestClient(app) as client:
            prepared=self.prepare_request(client,subject,self.edit_request(subject,trip,'advance-before-enqueue'))
            saved=self.save_request(client,subject,prepared,'advance-before-enqueue')
            self.assertEqual(saved.status_code,200,saved.text);self.assertEqual(saved.json()['receipt']['committed_version'],trip['version']+1)
        _,service,producer,background,records=pipeline(path,auth,run)
        for cid,head in heads.items():enable(service,token,cid,head)
        result=producer.poll(token)
        self.assertEqual(result.unavailable,('a-stale',));self.assertEqual(len(result.submitted),1)
        model=Model();outcomes=run_worker.run_once(database,model,auth,background_jobs=background)
        self.assertEqual([r.status for r in outcomes],['completed']);self.assertEqual(model.calls,1)
        self.assertEqual(producer.poll(token).unavailable,('a-stale',));self.assertEqual(len(records),1)
        self.assertEqual(run_worker.run_once(database,model,auth,background_jobs=background),[]);self.assertEqual(model.calls,1)
        with database.connect(scope_for(ISSUER,subject)) as conn:
            rows=conn.execute('SELECT original_input FROM cj_memory_history_job').fetchall()
            self.assertEqual([json.loads(bytes(r[0]))['source']['conversation_id'] for r in rows],['z-independent'])
        # A failed metadata read is UNKNOWN, not proof of a version advance.
        with patch.object(TripBoundary,'with_operation',side_effect=psycopg.OperationalError('synthetic metadata unavailable')):
            with self.assertRaises(psycopg.OperationalError):producer.poll(token)
        self.assertEqual(len(records),1);self.assertEqual(model.calls,1)
        print('PASS real NEEDS accept + signed source-bound edit/save proves version advance: no stale job/cursor/fee write, independent source actually completes, next poll no resend; unknown read propagates')


class RejectedDecisionChecks(manual.ManualChecks):
    def test_rejected_decision_before_new_enqueue_reports_and_progresses(self):
        path=Path(manual.CONNINFO);run=self.run_context
        local_run_context.provision_budget(path,run,'alice');dev_auth.activate_travel(path,'alice',run,'MESSAGE-TRAVEL-CONSUMER@1')
        message_trip_profile.activate(path,'alice',run,'MESSAGE-TRIP-CONSUMER@1')
        ingress=create_local_app(conninfo_path=path,auth_dir=self.auth,run_context=run,travel_context=True,trip_context=True)
        database=LocalDatabase(path,run_context=run,travel_context=True,trip_context=True)
        headers={**self.headers('alice'),'Content-Type':'application/octet-stream'};token=headers['Authorization'][7:]
        with TestClient(ingress) as client:
            heads={cid:send(self,client,headers,cid,selected,self.base_version) for cid,selected in
                [('first-decision',self.trip_id),('a-repeat',self.trip_id),('b-pending',None),('z-independent',None)]}
        self.assertTrue(all(r.status=='completed' for r in run_worker.run_once(database,FakeProvider(),self.auth)))
        app,service,producer,background,records=pipeline(path,self.auth,run)
        enable(service,token,'first-decision',heads['first-decision'])
        model=Model();self.assertEqual(len(producer.poll(token).submitted),1)
        self.assertEqual([r.status for r in run_worker.run_once(database,model,self.auth,background_jobs=background)],['completed'])
        view=json.loads(service.current_conversation_candidates(token,'first-decision',''));candidate=view['candidates'][0]
        enable(service,token,'b-pending',heads['b-pending'])
        pending=packed(dict(version='MEMORY-JOBS@1',job_id='old-pending',attempt_id='old-pending-attempt',
            source=dict(conversation_id='b-pending',generation=heads['b-pending']['generation'],epoch=0,after=0,through=1,
                        source_version=1,withdrawal_epoch=1,mode='incremental')))
        with TestClient(app) as client:
            response=client.post('/internal/v1/memory-history/jobs',content=pending,headers=headers)
            self.assertEqual(response.status_code,200,response.text)
            response=client.post('/v3/memory-candidate-actions',content=packed(dict(version='MEMORY-CANDIDATE@1',action_id='explicit-reject',
                **candidate['review'],candidate_id=candidate['candidate_id'],expected_candidate_version=candidate['version'],
                expected_memory_epoch=view['memory_epoch'],operation='reject')),headers=headers)
            self.assertEqual(response.status_code,200,response.text)
        for cid in ('a-repeat','z-independent'):enable(service,token,cid,heads[cid])
        result=producer.poll(token);self.assertEqual(result.unavailable,('a-repeat','b-pending'));self.assertEqual(len(result.submitted),1)
        self.assertEqual([r.status for r in run_worker.run_once(database,model,self.auth,background_jobs=background)],['completed'])
        self.assertEqual(model.calls,2);self.assertEqual(len(records),2)
        self.assertEqual(producer.poll(token).unavailable,('a-repeat','b-pending'))
        self.assertEqual(run_worker.run_once(database,model,self.auth,background_jobs=background),[]);self.assertEqual(model.calls,2)
        with database.connect(self.owner) as conn:
            rows=conn.execute('SELECT original_input FROM cj_memory_history_job ORDER BY job_id').fetchall()
            self.assertEqual({json.loads(bytes(r[0]))['source']['conversation_id'] for r in rows},{'first-decision','b-pending','z-independent'})
            self.assertEqual(conn.execute('SELECT status FROM cj_memory_item WHERE item_id=%s',(candidate['candidate_id'],)).fetchone(),('withdrawn',))
            self.assertEqual(conn.execute("SELECT state,original_input FROM cj_memory_history_job WHERE job_id='old-pending'").fetchone(),('pending',pending))
        print('PASS genuine BG3 candidate + signed reject: repeated same decision reports NoEligible source, no new job/fee or resurrection; independent ordinary source actually completes and never resends')


class ErasedHistoryChecks(manual.ManualChecks):
    def test_erased_history_copy_reports_and_does_not_starve_other_source(self):
        path=Path(manual.CONNINFO);run=self.run_context
        local_run_context.provision_budget(path,run,'alice');dev_auth.activate_travel(path,'alice',run,'MESSAGE-TRAVEL-CONSUMER@1')
        message_trip_profile.activate(path,'alice',run,'MESSAGE-TRIP-CONSUMER@1')
        ingress=create_local_app(conninfo_path=path,auth_dir=self.auth,run_context=run,travel_context=True,trip_context=True)
        database=LocalDatabase(path,run_context=run,travel_context=True,trip_context=True)
        headers={**self.headers('alice'),'Content-Type':'application/octet-stream'};token=headers['Authorization'][7:]
        with TestClient(ingress) as client:
            heads={cid:send(self,client,headers,cid,None,self.base_version) for cid in ('a-erased','z-independent')}
        self.assertTrue(all(r.status=='completed' for r in run_worker.run_once(database,FakeProvider(),self.auth)))
        _,service,producer,background,records=pipeline(path,self.auth,run)
        enable(service,token,'a-erased',heads['a-erased'])
        model=Model();producer.poll(token)
        self.assertEqual([r.status for r in run_worker.run_once(database,model,self.auth,background_jobs=background)],['completed'])
        from cj_memory_withdrawal.erasure_store import freeze
        from cj_memory_withdrawal.erasure_command import ErasureCommand,VERSION
        from cj_api.local_account_admission_v2 import subject_digest
        def stop(context):
            repo,principal,guard=service._binding(context,token)
            with repo.transaction() as memory:
                memory.lock_scope();items=memory.effective('self',None);self.assertEqual(len(items),1)
                raw=packed(dict(version=VERSION,action_id='erase-history-source',item_id=items[0].command.item_id,
                    expected_version=items[0].version,derived_range='owned_trip_derived_scope'))
                result=freeze(memory,ErasureCommand.parse(raw),subject_digest(principal),max_sources=1000,max_jobs=1000,max_bytes=1_000_000)
                guard('automatic_erased_source_stop');return result
        service.boundary.with_history_context(token,stop)
        for aid,operation,version in (('disable-erased','disable',1),('enable-erased-again','enable',2)):
            service.apply_consent(token,packed(dict(version='MEMORY-HISTORY@1',action_id=aid,operation=operation,conversation_id='a-erased',
                expected_generation=heads['a-erased']['generation'],expected_epoch=0,expected_source_version=version)))
        enable(service,token,'z-independent',heads['z-independent'])
        result=producer.poll(token);self.assertEqual(result.unavailable,('a-erased',));self.assertEqual(len(result.submitted),1)
        # The new independent copy is admitted; the old erased source is never
        # recopied. No whole-B deletion or provider fee inference is claimed.
        self.assertEqual(len(records),2)
        with database.connect(self.owner) as conn:
            rows=conn.execute('SELECT original_input FROM cj_memory_history_job').fetchall()
            self.assertEqual(len(rows),2)
            self.assertEqual(sum(json.loads(bytes(r[0]))['source']['conversation_id']=='a-erased' for r in rows),1)
            self.assertEqual(conn.execute('SELECT processed FROM cj_memory_history_cursor').fetchall(),[(1,)])
        self.assertEqual(model.calls,1)
        print('PASS actual extracted source -> original erasure freeze -> signed off/on: re-extraction reports erased range, no old payload copy/cursor advancement or provider resend, independent BG preparation still progresses')


if __name__=='__main__':
    selected={'advanced':'AdvancedDecisionChecks.test_formal_version_advance_before_enqueue_reports_and_progresses',
              'rejected':'RejectedDecisionChecks.test_rejected_decision_before_new_enqueue_reports_and_progresses',
              'erased':'ErasedHistoryChecks.test_erased_history_copy_reports_and_does_not_starve_other_source'}[sys.argv[1]]
    unittest.main(argv=[sys.argv[0]],defaultTest=selected,verbosity=2)
