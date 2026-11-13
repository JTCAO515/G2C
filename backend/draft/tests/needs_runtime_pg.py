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
from cj_draft.lio_plan import INITIAL_SYSTEM
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
        if system not in (SYSTEM, INITIAL_SYSTEM):
            yield from super().stream(messages,system);return
        self.calls+=1;self.source_seen=True
        source=json.loads(messages[-1]['content']);items=[]
        for original in source['fields']['fixed_items']:
            schedule={edge:{key:deepcopy(original[edge][key]) for key in ('date','time','timezone')}
                      for edge in ('start','end')}
            for value in schedule.values():value['utc_offset']=dict(state='unknown')
            items.append(dict(id=original['item_id'],text=original['description'],verification='pending',evidence=[],
                schedule=schedule,fixed=original['locked'],source_category='user_provided',source_refs=[]))
        document=dict(version='TRIP-model-plan.1',title='原源结构化安排 / sourced plan',items=items,proposed_subjects={})
        if self.change:self.change(document)
        yield json.dumps(document,ensure_ascii=False,separators=(',',':'))


class NeedsPlanChecks(Harness):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.host=RegisteredHost(cls.auth/'plans',Path(CONNINFO),{s:(12,2,30000) for s in ('valid','overlap','locked','changed','publish-first','new-item','foreign','missing-context','bad-schema','one-item','no-authority')})
        cls.env=dict(CJ_LOCAL_NEEDS_PROFILE='manual-v1',CJ_LOCAL_TRAVEL_CONTEXT='message-travel.1')
        for subject in cls.host.subjects:
            dev_auth.activate_travel(Path(CONNINFO),subject,cls.host.profiles[subject][1],ABI)

    def setup_source(self,subject,items=None):
        host=self.host
        with patch.dict(os.environ,self.env),host.api(subject) as client:
            raw=json.dumps(dict(action_id='source-'+subject,needs_id='visit',expected_version=0,
                source=dict(kind='manual',text='用户明确来源 / checked'),changes=dict(fixed_items=items if items is not None else [
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
        from cj_draft import needs_publisher
        build_original=needs_publisher.build;reports=[]
        def observed(*args,**kwargs):
            value=build_original(*args,**kwargs);reports.append(value[2]);return value
        with patch.object(needs_publisher,'build',observed):outcome=worker.process()[0]
        self.assertEqual(outcome.status,'completed');self.assertIsNotNone(outcome.proposal_id)
        self.assertTrue(reports)
        self.assertTrue(all(c.zh and c.en for c in reports[0].checks))
        self.assertEqual(reports[0].status,'UNKNOWN')
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
            basis=conn.execute('SELECT scope,proposal_id,message_scope,run_id,needs_scope,needs_id,needs_version,source_input,source_sha256,proposed_input FROM cj_trip_needs_basis WHERE proposal_id=%s',(outcome.proposal_id,)).fetchone()
            for privilege in ('UPDATE','DELETE','TRUNCATE'):
                self.assertFalse(conn.execute('SELECT has_table_privilege(current_user,%s,%s)',('cj_trip_needs_basis',privilege)).fetchone()[0])
        with db.connect(scope_for(ISSUER,'foreign')) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_needs_basis WHERE scope=%s',(trip_scope_for(scope),)).fetchone()[0],0)
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            with db.connect(scope_for(ISSUER,'foreign')) as conn:
                conn.execute('INSERT INTO cj_trip_needs_basis VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',basis)
        with psycopg.connect(**json.loads(Path(CONNINFO).read_text()),autocommit=True) as observer:
            with self.assertRaises(psycopg.errors.RaiseException):
                with observer.transaction():observer.execute((ROOT/'backend/migrations/down/0024_trip_needs_basis.down.sql').read_text())
            self.assertEqual(observer.execute('SELECT count(*) FROM cj_trip_needs_basis WHERE proposal_id=%s',(outcome.proposal_id,)).fetchone()[0],1)
        from cj_needs.revision_lease import LeaseUnavailable
        capture=worker.drafts.source._captures[next(iter(worker.drafts.source._captures))]
        with self.assertRaises(LeaseUnavailable):worker.drafts.source.check(capture.binding,capture)

    def test_conflicting_or_locked_model_result_has_zero_candidate(self):
        for subject,change,diagnostic in [
            ('overlap',lambda d:d['items'][1]['schedule'].update(start=dict(date=known('2026-11-02'),time=known('09:30'),timezone=known('Asia/Shanghai'),utc_offset=dict(state='unknown'))), 'stage=source'),
            ('locked',lambda d:d['items'][0].update(text='changed locked source'), 'stage=source'),
            ('bad-schema',lambda d:d['items'][0]['schedule']['start'].update(time=known('secret-invalid-time')), 'field=items[0].schedule.start.time'),
        ]:
            with self.subTest(subject=subject):
                self.setup_source(subject);worker,db=self.worker(subject,PlanModel(change))
                with self.assertLogs('cj_draft.needs_publisher',level='WARNING') as captured:
                    outcome=worker.process()[0]
                self.assertEqual(len(captured.output),1)
                self.assertIn(diagnostic,captured.output[0])
                self.assertNotIn('secret-invalid-time',captured.output[0])
                self.assertNotIn('changed locked source',captured.output[0])
                self.assertEqual(outcome.status,'completed')
                self.assertIsNone(outcome.proposal_id)
                scope=scope_for(ISSUER,subject)
                with db.connect(scope) as conn:
                    self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_proposal').fetchone()[0],0)
                    self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_needs_basis').fetchone()[0],0)
                    self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_record').fetchone()[0],0)
                    self.assertEqual(conn.execute("SELECT count(*) FROM cj_run_event WHERE kind='effect_committed'").fetchone()[0],0)

    def test_single_locked_needs_candidate_publishes_without_formal_write(self):
        from cj_draft.needs_context import publisher as context_publisher
        subject='one-item'
        original=fixed('lobby-meeting','09:00','10:00',True)
        self.setup_source(subject,[original])
        worker,db=self.worker(subject,PlanModel())
        scope=scope_for(ISSUER,subject)
        worker.drafts=context_publisher(db,checker_for(self.host.auth),worker.message_context,
            lambda:self.host.headers[subject]['Authorization'][7:],scope)
        outcome=worker.process()[0]
        self.assertEqual(outcome.status,'completed')
        self.assertIsNotNone(outcome.proposal_id)
        repo=Repository(lambda:db.connect(scope),trip_scope_for(scope),structured=True)
        items=json.loads(repo.proposal_detail(outcome.proposal_id).proposal.content)['items']
        self.assertEqual([i['id'] for i in items],['lobby-meeting'])
        self.assertEqual(items[0]['fixed'],original['locked'])
        self.assertEqual(items[0]['schedule']['start']['time'],original['start']['time'])
        with db.connect(scope) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_record').fetchone()[0],0)

    def test_missing_final_guard_is_classified_and_does_not_publish(self):
        subject='no-authority'
        self.setup_source(subject)
        worker,db=self.worker(subject,PlanModel())
        publish=worker.drafts.publish_for_message
        def without_final_guard(*args,**kwargs):
            return publish(*args,before_publish=None)
        worker.drafts.publish_for_message=without_final_guard
        with self.assertLogs('cj_draft.needs_publisher',level='WARNING') as captured:
            outcome=worker.process()[0]
        self.assertEqual(len(captured.output),1)
        self.assertIn('stage=authority field=publication',captured.output[0])
        self.assertEqual(outcome.status,'completed')
        self.assertIsNone(outcome.proposal_id)
        with db.connect(scope_for(ISSUER,subject)) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_proposal').fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_needs_basis').fetchone()[0],0)
    def test_new_activity_is_proposed_not_user_confirmed_or_supplier_verified(self):
        self.setup_source('new-item')
        def add(document):
            item=deepcopy(document['items'][1]);item.update(id='new-intent',text='模型提出 / proposed only',
                source_category='unknown',fixed=dict(state='unknown'))
            item['schedule']['start']['time']=known('13:00');item['schedule']['end']['time']=known('14:00')
            document['items'].append(item);document['proposed_subjects']['new-intent']=['self']
        worker,db=self.worker('new-item',PlanModel(add));outcome=worker.process()[0]
        self.assertIsNotNone(outcome.proposal_id)
        with db.connect(scope_for(ISSUER,'new-item')) as conn:
            original=conn.execute('SELECT proposed_input FROM cj_trip_needs_basis WHERE proposal_id=%s',(outcome.proposal_id,)).fetchone()[0]
            item=json.loads(bytes(original))['fixed_items'][-1]
            self.assertEqual(item['kind'],'intent');self.assertEqual(item['booking_status'],dict(state='unknown'))
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_record').fetchone()[0],0)

    def test_wrong_owner_or_missing_source_context_cannot_publish(self):
        from cj_api.local_needs import protected_reader
        for subject in ('foreign','missing-context'):
            with self.subTest(subject=subject):
                self.setup_source(subject);worker,db=self.worker(subject,PlanModel())
                if subject=='foreign':
                    worker.drafts.source.token_supplier=lambda:self.host.headers['valid']['Authorization'][7:]
                else:
                    worker.drafts.source.reader=protected_reader(LocalDatabase(CONNINFO),checker_for(self.host.auth))
                outcome=worker.process()[0]
                self.assertIsNone(outcome.proposal_id)
                self.assertIn(outcome.status,('context_invalid','unknown'))
                with db.connect(scope_for(ISSUER,subject)) as conn:
                    self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_proposal').fetchone()[0],0)
                    self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_needs_basis').fetchone()[0],0)

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


class GroupedPlanChecks(unittest.TestCase):
    """Original worker/NEEDS leases/signer/act; fixture L admission, no real provider."""
    worker = NeedsPlanChecks.worker

    @classmethod
    def setUpClass(cls):
        Harness.setUpClass.__func__(cls)
        subjects = ('group-4-zh','group-4-en','group-5-zh','group-5-en','group-length','group-window','group-empty-party')
        cls.host = RegisteredHost(cls.auth/'grouped-plans',Path(CONNINFO),{s:(12,2,30000) for s in subjects})
        cls.env = dict(CJ_LOCAL_NEEDS_PROFILE='manual-v1',CJ_LOCAL_TRAVEL_CONTEXT='message-travel.1')
        from cj_trip.confirmation import ConfirmationSigner
        cls.signer = ConfirmationSigner(b'synthetic-grouped-plan-signer-1234567')
        cls.admitted = {}
        for subject in subjects:
            dev_auth.activate_travel(Path(CONNINFO),subject,cls.host.profiles[subject][1],ABI)

    tearDownClass = classmethod(Harness.tearDownClass.__func__)

    def send(self, subject, number, *, fields=None):
        with patch.dict(os.environ,self.env),self.host.api(subject) as client:
            if fields is not None:
                response=client.post('/v1/needs-actions',content=json.dumps(dict(action_id='source-'+subject,
                    needs_id='visit',expected_version=0,source=dict(kind='manual',text='Explicit synthetic source'),
                    changes=fields)).encode(),headers={**self.host.headers[subject],'Content-Type':'application/octet-stream'})
                self.assertEqual(response.status_code,200,response.text)
            conversation=client.put('/v1/conversations',params={'conversation_id':subject},headers=self.host.headers[subject]).json()
            value=dict(version='MESSAGE-send.2',conversation_id=subject,message_id=subject+'-'+str(number),
                text='北京多天，每天上午下午；保留酒店集合。' if number==1 else 'Keep every saved item; add one concise suggestion per period.',
                trip_id=None,creation_intent='consider_trip',expected_generation=conversation['generation'],
                expected_sequence=number-1,travel_context=None,needs_reference=dict(id='visit',expected_version=1))
            response=client.post('/v2/messages',content=json.dumps(value).encode(),headers={
                **self.host.headers[subject],'Content-Type':'application/octet-stream'})
            self.assertEqual(response.status_code,200,response.text)
            return response.json()['receipt']

    def configured(self, subject, value, *, truncated=False):
        from cj_agent.provider import ProviderUnknown
        from cj_draft.grouped_plan import LioGroupedPlanPublisher, DATED_FIRST, DATED_DELTA
        from cj_draft.needs_context import publisher as context_publisher
        class Model(FakeProvider):
            def stream(self,messages,system=None):
                if system is None or not any(v in system for v in (DATED_FIRST,DATED_DELTA)):
                    yield from super().stream(messages,system);return
                self.calls+=1
                raw=json.dumps(value,ensure_ascii=False,separators=(',',':'))
                if truncated:
                    yield raw[:120]
                    raise ProviderUnknown('synthetic finish_reason=length')
                yield raw
        def original_needs(cursor,binding):
            cursor.execute('SELECT needs_id,needs_version,content_sha256 FROM cj_message_needs_binding '
                'WHERE message_scope=%s AND message_id=%s AND run_id=%s',
                (binding.scope,binding.message_id,binding.run_id))
            return cursor.fetchone()
        class FixturePublisher(LioGroupedPlanPublisher):
            def publish_for_message(self,*args,before_publish):
                def final(*,check_trip):
                    check_trip()
                    before_publish()
                return super().publish_for_message(*args,before_publish=final)
        worker,database=self.worker(subject,Model())
        owner=scope_for(ISSUER,subject)
        base=context_publisher(database,checker_for(self.host.auth),worker.message_context,
            lambda:self.host.headers[subject]['Authorization'][7:],owner)
        worker.drafts=FixturePublisher(base,self.signer,original_needs,
            lambda binding,original,expected: binding.message_id in self.admitted
                and self.admitted[binding.message_id]==expected and original.receipt.run_id==binding.run_id)
        return worker,database

    def test_four_five_days_bilingual_signed_first_and_same_window_replan(self):
        from cj_trip.lio_history import plan_action_id, TripHead
        from grouped_draft_fixtures import source, reply
        for days in (4,5):
            for language in ('zh','en'):
                with self.subTest(days=days,language=language):
                    subject=f'group-{days}-{language}'
                    snapshot,_=source(days,language)
                    message=self.send(subject,1,fields=snapshot.fields)
                    self.admitted[message['message_id']]=None
                    value=reply(days,language)
                    self.assertLess(len(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()),1024)
                    worker,_=self.configured(subject,value)
                    self.assertEqual(worker.process()[0].status,'completed')
                    repository=worker.drafts.repository
                    receipt=repository.query_action(plan_action_id(message['run_id']))
                    self.assertEqual(receipt.committed_version,1)
                    before=repository.detail(receipt.trip_id)
                    initial=json.loads(before.content)
                    self.assertEqual(len(initial['items']),1+days*2)
                    self.assertEqual([i['text'] for i in initial['items'][1:]],
                                     [r[1] for _,rows in value['days'] for r in rows])
                    second=self.send(subject,2)
                    self.admitted[second['message_id']]=TripHead.from_trip(before)
                    worker,_=self.configured(subject,reply(days,language,delta=True))
                    self.assertEqual(worker.process()[0].status,'completed')
                    after=worker.drafts.repository.detail(before.trip_id)
                    self.assertEqual(after.version,2)
                    self.assertEqual(json.loads(after.content)['items'][:len(initial['items'])],initial['items'])
                    self.assertEqual(json.loads(after.content)['title'],initial['title'])
                    self.assertEqual([t.content for t in worker.drafts.repository.lio_revisions(before.trip_id,None,10)],
                                     [after.content,before.content])

    def test_length_still_withholds_all_formal_writes(self):
        from grouped_draft_fixtures import source, reply
        from cj_trip.lio_history import plan_action_id
        subject='group-length';snapshot,_=source(5,'en')
        message=self.send(subject,1,fields=snapshot.fields);self.admitted[message['message_id']]=None
        worker,database=self.configured(subject,reply(5,'en'),truncated=True)
        self.assertEqual(worker.process()[0].status,'completed')
        binding=worker._binding(worker.messages.query(message['message_id']).receipt)
        state=database.run_repository(binding.scope).snapshot_optional(binding)
        self.assertEqual(state.draft_outcome,'provider_unknown')
        self.assertEqual(worker.drafts.repository.list_trips(),[])
        self.assertIsNone(worker.drafts.repository.query_action(plan_action_id(message['run_id'])))

    def test_empty_fixed_items_three_people_and_all_fifteen_periods_save_without_defaults(self):
        from grouped_draft_fixtures import source, reply
        from cj_trip.lio_history import plan_action_id
        subject='group-empty-party';snapshot,_=source(5,'en',party=3,with_fixed=False)
        message=self.send(subject,1,fields=snapshot.fields);self.admitted[message['message_id']]=None
        value=reply(5,'en',party=3,periods=3)
        self.assertLess(len(json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()),1024)
        worker,_=self.configured(subject,value)
        self.assertEqual(worker.process()[0].status,'completed')
        receipt=worker.drafts.repository.query_action(plan_action_id(message['run_id']))
        self.assertEqual(receipt.committed_version,1)
        content=json.loads(worker.drafts.repository.detail(receipt.trip_id).content)
        self.assertEqual(len(content['items']),15)
        self.assertTrue(all(i['fixed']==known(False) for i in content['items']))

    def test_original_source_window_rejection_is_not_relaxed(self):
        from grouped_draft_fixtures import source, reply
        from cj_trip.lio_history import plan_action_id
        subject='group-window';snapshot,_=source(4,'en')
        message=self.send(subject,1,fields=snapshot.fields);self.admitted[message['message_id']]=None
        value=reply(4,'en');value['days'][-1][0]='2026-12-31'
        worker,_=self.configured(subject,value)
        self.assertEqual(worker.process()[0].status,'completed')
        self.assertEqual(worker.drafts.repository.list_trips(),[])
        self.assertIsNone(worker.drafts.repository.query_action(plan_action_id(message['run_id'])))


if __name__=='__main__':unittest.main(verbosity=2)
