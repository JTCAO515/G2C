"""Real B signed source/RUN/worker and C structured publication, private PG only."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
import unittest
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import psycopg
from unittest.mock import patch
from datetime import datetime

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend/agent/tests'),str(ROOT/'backend/cj_api/tests'),str(ROOT/'scripts')]
from fastapi.testclient import TestClient
from e2e_local import Harness,CONNINFO
from registered_host_support import RegisteredHost
from cj_api.local_app import LocalDatabase,scope_for,ISSUER
from cj_api.local_worker_context import checker_for
from cj_agent.provider import FakeProvider
from cj_message.travel import ABI
from cj_trip.postgres import Repository
from cj_agent.draft import trip_scope_for
from cj_draft.needs_local import publisher
from cj_draft.needs_publisher import SYSTEM
import dev_auth


def known(value):return dict(state='known',value=value)
def event(clock):return dict(date=known('2026-11-02'),time=known(clock),timezone=known('Asia/Shanghai'),place=dict(state='unknown'))
def fixed(key,start,end,locked):return dict(item_id=key,kind='appointment',description='原安排 / original '+key,
    applies_to=['self'],locked=known(locked),booking_status=known('booked'),start=event(start),end=event(end))


class PlanModel(FakeProvider):
    def __init__(self,change=None):super().__init__();self.change=change;self.source_seen=False
    def stream(self,messages,system=None):
        if system!=SYSTEM:
            yield from super().stream(messages,system);return
        self.calls+=1;self.source_seen=True
        source=json.loads(messages[-1]['content']);items=[]
        for original in source['fields']['fixed_items']:
            schedule={edge:{key:deepcopy(original[edge][key]) for key in ('date','time','timezone')}
                      for edge in ('start','end')}
            for value in schedule.values():value['utc_offset']=dict(state='unknown')
            items.append(dict(id=original['item_id'],text=original['description'],verification='pending',evidence=[],
                schedule=schedule,fixed=original['locked'],source_category='user_provided',source_refs=[]))
        document=dict(version='TRIP-model-plan.1',title='原源结构化安排 / sourced plan',items=items)
        if self.change:self.change(document)
        yield json.dumps(document,ensure_ascii=False,separators=(',',':'))


class NeedsPlanChecks(Harness):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.host=RegisteredHost(cls.auth/'plans',Path(CONNINFO),{s:(12,2,30000) for s in ('valid','overlap','locked','changed','publish-first')})
        cls.env=dict(CJ_LOCAL_NEEDS_PROFILE='manual-v1',CJ_LOCAL_TRAVEL_CONTEXT='message-travel.1')
        for subject in cls.host.subjects:
            dev_auth.activate_travel(Path(CONNINFO),subject,cls.host.profiles[subject][1],ABI)

    def setup_source(self,subject):
        host=self.host
        with patch.dict(os.environ,self.env),host.api(subject) as client:
            raw=json.dumps(dict(action_id='source-'+subject,needs_id='visit',expected_version=0,
                source=dict(kind='manual',text='用户明确来源 / checked'),changes=dict(fixed_items=[
                    fixed('a','09:00','10:00',True),fixed('b','11:00','12:00',False)]))).encode()
            saved=client.post('/v1/needs-actions',content=raw,headers={**host.headers[subject],'Content-Type':'application/octet-stream'})
            self.assertEqual(saved.status_code,200,saved.text)
            chat=client.put('/v1/conversations',params={'conversation_id':subject},headers=host.headers[subject]).json()
            raw=json.dumps(dict(version='MESSAGE-send.2',conversation_id=subject,message_id='message-'+subject,
                text='按原始条件安排 / plan using original constraints',trip_id=None,creation_intent='consider_trip',
                expected_generation=chat['generation'],expected_sequence=0,travel_context=None,
                needs_reference=dict(id='visit',expected_version=1))).encode()
            result=client.post('/v2/messages',content=raw,headers={**host.headers[subject],'Content-Type':'application/octet-stream'})
            self.assertEqual(result.status_code,200,result.text)
            return result.json()['receipt']

    def worker(self,subject,model):
        import run_worker
        host=self.host;scope=scope_for(ISSUER,subject)
        db=LocalDatabase(CONNINFO,run_context=host.profiles[subject][1],travel_context=True,needs_context=True)
        checker=checker_for(host.auth)
        worker=run_worker._worker_for_scope(db,model,host.auth,scope,checker)
        worker.drafts=publisher(db,checker,worker.message_context,lambda:host.headers[subject]['Authorization'][7:],scope)
        return worker,db

    def test_real_bound_source_prompt_and_original_structured_proposal(self):
        receipt=self.setup_source('valid');model=PlanModel();worker,db=self.worker('valid',model)
        outcome=worker.process()[0]
        self.assertEqual(outcome.status,'completed');self.assertIsNotNone(outcome.proposal_id)
        self.assertTrue(model.source_seen);self.assertEqual(model.calls,2)
        scope=scope_for(ISSUER,'valid');repository=Repository(lambda:db.connect(scope),trip_scope_for(scope),structured=True)
        detail=repository.proposal_detail(outcome.proposal_id);doc=json.loads(detail.proposal.content)
        self.assertEqual(doc['content_version'],'structured.2')
        self.assertEqual(doc['items'][0]['schedule']['start']['time'],known('09:00'))
        self.assertEqual(doc['items'][0]['fixed'],known(True))
        with db.connect(scope) as conn:
            row=conn.execute('SELECT needs_id,needs_version,source_input FROM cj_trip_needs_basis WHERE scope=%s AND proposal_id=%s',
                (trip_scope_for(scope),outcome.proposal_id)).fetchone()
            self.assertEqual(row[:2],('visit',1))
            self.assertEqual(json.loads(bytes(row[2]))['reference']['message_id'],receipt['message_id'])
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_record').fetchone()[0],0)

    def test_conflicting_or_locked_model_result_has_zero_candidate(self):
        for subject,change in [('overlap',lambda d:d['items'][1]['schedule'].update(start=dict(date=known('2026-11-02'),time=known('09:30'),timezone=known('Asia/Shanghai'),utc_offset=dict(state='unknown')))),
                               ('locked',lambda d:d['items'][0].update(text='changed locked source'))]:
            with self.subTest(subject=subject):
                self.setup_source(subject);worker,db=self.worker(subject,PlanModel(change))
                outcome=worker.process()[0]
                self.assertIsNone(outcome.proposal_id)
                scope=scope_for(ISSUER,subject)
                with db.connect(scope) as conn:
                    self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_proposal').fetchone()[0],0)
                    self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_needs_basis').fetchone()[0],0)
                    self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_record').fetchone()[0],0)
                    self.assertEqual(conn.execute("SELECT count(*) FROM cj_run_event WHERE kind='effect_committed'").fetchone()[0],0)
    def test_real_writer_first_rejects_captured_old_result(self):
        self.setup_source('changed')
        host=self.host
        def change(document):
            with patch.dict(os.environ,self.env),host.api('changed') as client:
                raw=json.dumps(dict(action_id='actual-correction',needs_id='visit',expected_version=1,
                    source=dict(kind='manual',text='new explicit input'),changes=dict(party_size=known(3)))).encode()
                response=client.post('/v1/needs-actions',content=raw,headers={**host.headers['changed'],'Content-Type':'application/octet-stream'})
                self.assertEqual(response.status_code,200,response.text)
        worker,db=self.worker('changed',PlanModel(change))
        outcome=worker.process()[0]
        self.assertEqual(outcome.status,'context_invalid');self.assertIsNone(outcome.proposal_id)
        with db.connect(scope_for(ISSUER,'changed')) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_proposal').fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_needs_basis').fetchone()[0],0)

    def test_real_publication_first_holds_writer_through_run_commit(self):
        subject='publish-first';self.setup_source(subject);host=self.host
        worker,db=self.worker(subject,PlanModel())
        published=threading.Event();release=threading.Event()
        original=worker.drafts.publish_for_message
        def hold_after_original(*args,**kwargs):
            result=original(*args,**kwargs)
            published.set()
            self.assertTrue(release.wait(8))
            return result
        worker.drafts.publish_for_message=hold_after_original
        with patch.dict(os.environ,self.env),host.api(subject) as client,ThreadPoolExecutor(max_workers=2) as pool:
            running=pool.submit(worker.process)
            self.assertTrue(published.wait(10))
            raw=json.dumps(dict(action_id='after-commit-correction',needs_id='visit',expected_version=1,
                source=dict(kind='manual',text='new explicit input'),changes=dict(party_size=known(4)))).encode()
            correction=pool.submit(client.post,'/v1/needs-actions',content=raw,
                headers={**host.headers[subject],'Content-Type':'application/octet-stream'})
            try:
                waiting=0;deadline=time.monotonic()+4
                with psycopg.connect(**json.loads(Path(CONNINFO).read_text()),autocommit=True) as observer:
                    while time.monotonic()<deadline:
                        waiting=observer.execute("SELECT count(*) FROM pg_stat_activity WHERE usename='cj_m1_runtime' AND wait_event='advisory' AND query LIKE '%cj_needs_fence_key%'").fetchone()[0]
                        if waiting:break
                        time.sleep(.01)
                self.assertGreater(waiting,0);self.assertFalse(correction.done())
            finally:release.set()
            result=running.result(timeout=15)[0];response=correction.result(timeout=15)
            self.assertIsNotNone(result.proposal_id)
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['receipt']['version'],2)
        scope=scope_for(ISSUER,subject)
        with db.connect(scope) as conn:
            self.assertEqual(conn.execute("SELECT count(*) FROM cj_run_event WHERE run_id=%s AND kind='effect_committed'",(result.run_id,)).fetchone()[0],1)
            self.assertEqual(conn.execute('SELECT needs_version FROM cj_trip_needs_basis WHERE proposal_id=%s',(result.proposal_id,)).fetchone()[0],1)
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_record').fetchone()[0],0)


if __name__=='__main__':unittest.main(verbosity=2)
