"""Actual source-bound proposal accept/reject with original confirmation/act."""
import sys,json
from pathlib import Path
import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend/draft/tests'),str(ROOT/'backend/agent/tests'),str(ROOT/'backend/cj_api/tests'),str(ROOT/'scripts')]
from e2e_local import Harness,CONNINFO
from registered_host_support import RegisteredHost
import needs_runtime_pg as source_fixture
from cj_message.travel import ABI
from cj_api.local_app import scope_for,ISSUER
from cj_trip.confirmation import ConfirmationSigner
from cj_trip.local_needs_app import create_local_needs_app
from cj_trip.domain import packed
import dev_auth


class NeedsActionChecks(unittest.TestCase):
    headers=Harness.headers
    setup_source=source_fixture.NeedsPlanChecks.setup_source
    worker=source_fixture.NeedsPlanChecks.worker
    @classmethod
    def setUpClass(cls):
        Harness.setUpClass.__func__(cls)
        cls.host=RegisteredHost(cls.auth/'needs-actions',Path(CONNINFO),{s:(12,2,30000) for s in ('accept','reject','stale','manual','fault-rollback','fault-ack','adopted','switch','manual-writer','manual-save','save-rollback','save-ack','schema','publish-replay','saved-offset','new-offset','malformed-model','edit-during-model','scoped-preview','lio-history','lio-plan','lio-edit')})
        cls.env=dict(CJ_LOCAL_NEEDS_PROFILE='manual-v1',CJ_LOCAL_TRAVEL_CONTEXT='message-travel.1')
        cls.signer=ConfirmationSigner(b'synthetic-source-action-key-1234567890')
        for subject in cls.host.subjects:
            dev_auth.activate_travel(Path(CONNINFO),subject,cls.host.profiles[subject][1],ABI)
    tearDownClass=classmethod(Harness.tearDownClass.__func__)

    def plan(self,subject,change=None):
        self.setup_source(subject)
        worker,db=self.worker(subject,source_fixture.PlanModel(change))
        outcome=worker.process()[0];self.assertIsNotNone(outcome.proposal_id)
        app=create_local_needs_app(conninfo_path=CONNINFO,auth_dir=self.host.auth,
            run_context=self.host.profiles[subject][1],confirmation_signer=self.signer)
        return app,outcome,db
    def action(self,subject,outcome,kind):
        with TestClient(create_local_needs_app(conninfo_path=CONNINFO,auth_dir=self.host.auth,
            run_context=self.host.profiles[subject][1],confirmation_signer=self.signer)) as client:
            response=client.get('/v2/trip-needs-proposals',params={'proposal_id':outcome.proposal_id},headers=self.host.headers[subject])
            self.assertEqual(response.status_code,200,response.text)
            return packed(dict(version='TRIP-needs-action.1',action_id=kind+'-'+subject,
                kind=kind,proposal_id=outcome.proposal_id,candidate_hash=response.json()['proposal']['candidate_hash']))
    def post(self,client,subject,raw):
        return client.post('/v1/trip-needs-actions',content=raw,
            headers={**self.host.headers[subject],'Content-Type':'application/octet-stream'})

    def edit_request(self,subject,trip,request_id,title='explicit edited title'):
        from hashlib import sha256
        return packed(dict(version='TRIP-needs-edit.1',needs_reference=dict(id='visit',expected_version=1),
            edit=dict(version='TRIP-manual-edit.2',request_id=request_id,trip_id=trip['trip_id'],
                expected_version=trip['version'],original_hash=sha256(packed(trip['content'])).hexdigest(),
                title=title,changes=[],order=None)))

    def prepare_request(self,client,subject,raw):
        response=client.post('/v1/trip-needs-edits',content=raw,
            headers={**self.host.headers[subject],'Content-Type':'application/octet-stream'})
        self.assertEqual(response.status_code,200,response.text)
        return response.json()['preparation']

    def save_request(self,client,subject,preparation,action_id):
        raw=packed(dict(version='TRIP-needs-save.1',action_id=action_id,
            proposal_id=preparation['proposal_id'],candidate_hash=preparation['candidate_hash']))
        return client.post('/v1/trip-needs-saves',content=raw,
            headers={**self.host.headers[subject],'Content-Type':'application/octet-stream'})

    def replan(self,subject,key,change=None,expect_proposal=True,wrap_publisher=None,needs_version=1,
               text='continue original trip', *, legacy_delta=False):
        with patch.dict(__import__('os').environ,self.env),self.host.api(subject) as client:
            chat=client.put('/v1/conversations',params={'conversation_id':key},headers=self.host.headers[subject]).json()
            raw=json.dumps(dict(version='MESSAGE-send.2',conversation_id=key,message_id=key,text=text,trip_id=None,
                creation_intent='consider_trip',expected_generation=chat['generation'],expected_sequence=0,travel_context=None,
                needs_reference=dict(id='visit',expected_version=needs_version))).encode()
            response=client.post('/v2/messages',content=raw,headers={**self.host.headers[subject],'Content-Type':'application/octet-stream'})
            self.assertEqual(response.status_code,200,response.text)
        from cj_agent.provider import FakeProvider
        from cj_draft.lio_plan import LIO_REPLAN_DELTA, LIO_REPLAN_DELTA_V2, REPLAN_SYSTEM
        from cj_draft.needs_context import publisher
        from cj_draft.needs_publisher import SYSTEM
        from cj_api.local_worker_context import checker_for
        class OriginalContextModel(FakeProvider):
            def stream(self,messages,system=None):
                if system not in (SYSTEM, REPLAN_SYSTEM):
                    yield from super().stream(messages,system);return
                self.calls+=1;source=json.loads(messages[-1]['content']);content=source['current_trip']['content']
                if system==REPLAN_SYSTEM:
                    value=dict(version=LIO_REPLAN_DELTA_V2,items=[],proposed_subjects={})
                    if legacy_delta:
                        value.update(version=LIO_REPLAN_DELTA,title=content['title'])
                else:
                    value=dict(version='TRIP-model-plan.1',title=content['title'],
                               items=content['items'],proposed_subjects={})
                if change:change(value)
                yield json.dumps(value,ensure_ascii=False)
        worker,db=self.worker(subject,OriginalContextModel())
        worker.drafts=publisher(db,checker_for(self.host.auth),worker.message_context,
            lambda:self.host.headers[subject]['Authorization'][7:],scope_for(ISSUER,subject))
        if wrap_publisher is not None:
            worker.drafts=wrap_publisher(worker.drafts)
        result=worker.process()[0]
        if expect_proposal:self.assertIsNotNone(result.proposal_id)
        else:self.assertIsNone(result.proposal_id)
        return result

    def test_selected_trip_switch_refuses_old_prepare_and_pending_save(self):
        subject='switch';app,outcome,db=self.plan(subject)
        with TestClient(app) as client:
            response=self.post(client,subject,self.action(subject,outcome,'accept'));self.assertEqual(response.status_code,200,response.text)
            old_id=response.json()['receipt']['trip_id']
            old=client.get('/v4/trip-structured',params={'trip_id':old_id},headers=self.host.headers[subject]).json()['trip']
            prepared=self.prepare_request(client,subject,self.edit_request(subject,old,'before-switch'))
            replacement=self.replan(subject,'switch-plan')
            action=json.loads(self.action(subject,replacement,'accept'));action['action_id']='select-new-trip'
            response=self.post(client,subject,packed(action));self.assertEqual(response.status_code,200,response.text)
            new_id=response.json()['receipt']['trip_id'];self.assertNotEqual(old_id,new_id)
            denied=client.post('/v1/trip-needs-edits',content=self.edit_request(subject,old,'after-switch'),
                headers={**self.host.headers[subject],'Content-Type':'application/octet-stream'})
            self.assertEqual(denied.status_code,409,denied.text)
            denied=self.save_request(client,subject,prepared,'save-old-selected')
            self.assertEqual(denied.status_code,409,denied.text)
            current=client.get('/v4/trip-structured',params={'trip_id':old_id},headers=self.host.headers[subject]).json()['trip']
            self.assertEqual(current,old)
            self.assertIsNone(client.get('/v1/trip-needs-action-receipts',params={'action_id':'save-old-selected'},headers=self.host.headers[subject]).json()['receipt'])
        with db.connect(scope_for(ISSUER,subject)) as conn:
            self.assertEqual(conn.execute('SELECT trip_id,trip_version FROM cj_trip_needs_current').fetchone(),(new_id,1))

    def test_actual_needs_writer_and_manual_save_both_orders(self):
        import threading,time,os,psycopg
        from concurrent.futures import ThreadPoolExecutor
        from cj_trip.postgres import Repository
        for subject in ('manual-writer','manual-save'):
            with self.subTest(subject=subject):
                app,outcome,db=self.plan(subject)
                with TestClient(app) as client:
                    accepted=self.post(client,subject,self.action(subject,outcome,'accept'));self.assertEqual(accepted.status_code,200,accepted.text)
                    trip_id=accepted.json()['receipt']['trip_id']
                    trip=client.get('/v4/trip-structured',params={'trip_id':trip_id},headers=self.host.headers[subject]).json()['trip']
                    p=self.prepare_request(client,subject,self.edit_request(subject,trip,'fenced-edit'))
                    correction=json.dumps(dict(action_id='actual-new-source',needs_id='visit',expected_version=1,
                        source=dict(kind='manual',text='explicit source correction'),changes=dict(party_size=dict(state='known',value=3)))).encode()
                    with patch.dict(os.environ,self.env),self.host.api(subject) as writer:
                        def correct():return writer.post('/v1/needs-actions',content=correction,
                            headers={**self.host.headers[subject],'Content-Type':'application/octet-stream'})
                        if subject=='manual-writer':
                            result=correct();self.assertEqual(result.status_code,200,result.text)
                            denied=self.save_request(client,subject,p,'manual-save-action')
                            self.assertEqual(denied.status_code,503,denied.text)
                            self.assertEqual(client.get('/v4/trip-structured',params={'trip_id':trip_id},headers=self.host.headers[subject]).json()['trip'],trip)
                            self.assertIsNone(client.get('/v1/trip-needs-action-receipts',params={'action_id':'manual-save-action'},headers=self.host.headers[subject]).json()['receipt'])
                        else:
                            published=threading.Event();release=threading.Event();original=Repository._act_in_tx
                            def held(repository,*args):
                                result=original(repository,*args);published.set();self.assertTrue(release.wait(8));return result
                            with patch.object(Repository,'_act_in_tx',held),ThreadPoolExecutor(max_workers=2) as pool:
                                saving=pool.submit(self.save_request,client,subject,p,'manual-save-action')
                                self.assertTrue(published.wait(10));writing=pool.submit(correct)
                                try:
                                    waiting=0;deadline=time.monotonic()+4
                                    with psycopg.connect(**json.loads(Path(CONNINFO).read_text()),autocommit=True) as observer:
                                        while time.monotonic()<deadline:
                                            waiting=observer.execute("SELECT count(*) FROM pg_stat_activity WHERE usename='cj_m1_runtime' AND wait_event='advisory' AND query LIKE '%cj_needs_fence_key%'").fetchone()[0]
                                            if waiting:break
                                            time.sleep(.01)
                                    self.assertGreater(waiting,0);self.assertFalse(writing.done())
                                finally:release.set()
                                saved=saving.result(timeout=15);revised=writing.result(timeout=15)
                                self.assertEqual(saved.status_code,200,saved.text);self.assertEqual(revised.status_code,200,revised.text)
                                self.assertEqual(saved.json()['receipt']['committed_version'],2)
                                self.assertEqual(revised.json()['receipt']['version'],2)
                    if subject=='manual-save':
                        # Reconcile the original action even after the source is now newer.
                        replay=self.save_request(client,subject,p,'manual-save-action')
                        self.assertEqual(replay.status_code,200,replay.text)
                        self.assertEqual(replay.json()['receipt'],saved.json()['receipt'])

    def test_manual_save_rolls_back_or_reconciles_exact_original_after_ack_loss(self):
        from cj_api.local_app import LocalDatabase
        for subject in ('save-rollback','save-ack'):
            with self.subTest(subject=subject):
                app,outcome,db=self.plan(subject)
                with TestClient(app) as client:
                    accepted=self.post(client,subject,self.action(subject,outcome,'accept'));self.assertEqual(accepted.status_code,200,accepted.text)
                    trip_id=accepted.json()['receipt']['trip_id']
                    trip=client.get('/v4/trip-structured',params={'trip_id':trip_id},headers=self.host.headers[subject]).json()['trip']
                    p=self.prepare_request(client,subject,self.edit_request(subject,trip,'save-fault'))
                    connect=LocalDatabase.connect
                    class Cursor:
                        def __init__(self,base,owner):self.base,self.owner=base,owner
                        def __getattr__(self,name):return getattr(self.base,name)
                        def execute(self,query,*args,**kwargs):
                            if query.startswith('INSERT INTO cj_trip_needs_action'):
                                self.owner.saved=True
                                if subject=='save-rollback':raise OSError('synthetic rollback after original act')
                            self.base.execute(query,*args,**kwargs);return self
                    class Connection:
                        def __init__(self,base):self.base,self.saved=base,False
                        def __getattr__(self,name):return getattr(self.base,name)
                        def __enter__(self):return self.base.__enter__()
                        def __exit__(self,*args):return self.base.__exit__(*args)
                        def cursor(self,*args,**kwargs):return Cursor(self.base.cursor(*args,**kwargs),self)
                        def commit(self):
                            self.base.commit()
                            if self.saved and subject=='save-ack':raise OSError('synthetic ACK lost')
                    def wrapped(database,*args,**kwargs):return Connection(connect(database,*args,**kwargs))
                    with patch.object(LocalDatabase,'connect',wrapped):
                        response=self.save_request(client,subject,p,'original-save')
                    self.assertEqual(response.status_code,503,response.text)
                    self.assertEqual(response.json()['error']['recovery'],'reconcile_original')
                rebuilt=create_local_needs_app(conninfo_path=CONNINFO,auth_dir=self.host.auth,
                    run_context=self.host.profiles[subject][1],confirmation_signer=self.signer)
                with TestClient(rebuilt) as client:
                    found=client.get('/v1/trip-needs-action-receipts',params={'action_id':'original-save'},headers=self.host.headers[subject])
                    self.assertEqual(found.status_code,200,found.text)
                    value=client.get('/v4/trip-structured',params={'trip_id':trip_id},headers=self.host.headers[subject]).json()['trip']
                    original=client.get('/v1/trip-needs-edits',params={'request_id':'save-fault'},headers=self.host.headers[subject]).json()['preparation']
                    self.assertEqual(original['proposal_id'],p['proposal_id'])
                    if subject=='save-rollback':
                        self.assertIsNone(found.json()['receipt']);self.assertEqual(value,trip)
                    else:
                        self.assertEqual(value['version'],2)
                        self.assertEqual(self.save_request(client,subject,p,'original-save').json()['receipt'],found.json()['receipt'])
                with db.connect(scope_for(ISSUER,subject)) as conn:
                    self.assertEqual(conn.execute('SELECT trip_version FROM cj_trip_needs_current').fetchone()[0],1 if subject=='save-rollback' else 2)

    def test_new_schema_minimal_columns_rls_and_nonempty_down_refusal(self):
        import psycopg
        from psycopg import sql
        subject='schema';app,outcome,db=self.plan(subject)
        with TestClient(app) as client:
            accepted=self.post(client,subject,self.action(subject,outcome,'accept'));self.assertEqual(accepted.status_code,200,accepted.text)
            trip_id=accepted.json()['receipt']['trip_id']
            trip=client.get('/v4/trip-structured',params={'trip_id':trip_id},headers=self.host.headers[subject]).json()['trip']
            self.prepare_request(client,subject,self.edit_request(subject,trip,'schema-edit'))
        self.replan(subject,'schema-context')
        tables=('cj_trip_needs_action','cj_trip_needs_current','cj_trip_needs_edit','cj_trip_needs_plan_context')
        rows={}
        with db.connect(scope_for(ISSUER,subject)) as conn:
            for table in tables:
                row=conn.execute(sql.SQL('SELECT * FROM {}').format(sql.Identifier(table))).fetchone();self.assertIsNotNone(row);rows[table]=row
                for privilege in ('UPDATE','DELETE','TRUNCATE'):
                    self.assertFalse(conn.execute('SELECT has_table_privilege(current_user,%s,%s)',(table,privilege)).fetchone()[0])
                self.assertEqual(conn.execute('SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=%s::regclass',(table,)).fetchone(),(True,True))
            for column in ('trip_id','trip_version'):
                self.assertTrue(conn.execute("SELECT has_column_privilege(current_user,'cj_trip_needs_current',%s,'UPDATE')",(column,)).fetchone()[0])
            self.assertFalse(conn.execute("SELECT has_column_privilege(current_user,'cj_trip_needs_current','needs_id','UPDATE')").fetchone()[0])
        for table,row in rows.items():
            with db.connect(scope_for(ISSUER,'reject')) as conn:
                self.assertEqual(conn.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table))).fetchone()[0],0)
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with db.connect(scope_for(ISSUER,'reject')) as conn:
                    conn.execute(sql.SQL('INSERT INTO {} VALUES ({})').format(sql.Identifier(table),sql.SQL(',').join(sql.Placeholder() for _ in row)),row)
        with psycopg.connect(**json.loads(Path(CONNINFO).read_text()),autocommit=True) as admin:
            counts={table:admin.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table))).fetchone()[0] for table in tables}
            with self.assertRaises(psycopg.errors.RaiseException):
                with admin.transaction():admin.execute((ROOT/'backend/migrations/down/0025_trip_needs_actions.down.sql').read_text())
            for table,count in counts.items():
                self.assertEqual(admin.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table))).fetchone()[0],count)

    def test_actual_context_publication_replays_the_same_retained_basis(self):
        from cj_draft.needs_context import publisher
        from cj_api.local_worker_context import checker_for
        import time
        subject='publish-replay';self.setup_source(subject)
        worker,db=self.worker(subject,source_fixture.PlanModel())
        worker.drafts=publisher(db,checker_for(self.host.auth),worker.message_context,
            lambda:self.host.headers[subject]['Authorization'][7:],scope_for(ISSUER,subject))
        now=time.time();worker.drafts.clock=lambda:now
        original=worker.drafts.publish_for_message;published=[]
        def twice(*args,**kwargs):
            first=original(*args,**kwargs);second=original(*args,**kwargs)
            self.assertEqual(first,second);published.extend((first,second));return second
        worker.drafts.publish_for_message=twice
        result=worker.process()[0];self.assertIsNotNone(result.proposal_id);self.assertEqual(len(published),2)
        with db.connect(scope_for(ISSUER,subject)) as conn:
            row=conn.execute('SELECT trip_id,trip_version,original_content FROM cj_trip_needs_plan_context WHERE proposal_id=%s',(result.proposal_id,)).fetchone()
            self.assertEqual(row,(None,None,None))
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_proposal WHERE proposal_id=%s',(result.proposal_id,)).fetchone()[0],1)

    def test_explicit_saved_offset_survives_fixed_context(self):
        from copy import deepcopy
        subject='saved-offset';app,outcome,db=self.plan(subject)
        with TestClient(app) as client:
            accepted=self.post(client,subject,self.action(subject,outcome,'accept'));self.assertEqual(accepted.status_code,200,accepted.text)
            trip_id=accepted.json()['receipt']['trip_id']
            def current():return client.get('/v4/trip-structured',params={'trip_id':trip_id},headers=self.host.headers[subject]).json()['trip']
            original=current();schedule=deepcopy(original['content']['items'][1]['schedule'])
            for event in schedule.values():event['utc_offset']=dict(state='known',value='+08:00')
            raw=json.loads(self.edit_request(subject,original,'saved-offset',title=None))
            raw['edit']['changes']=[dict(item_id='b',field='schedule',value=schedule)]
            p=self.prepare_request(client,subject,packed(raw));saved=self.save_request(client,subject,p,'save-observed-offset')
            self.assertEqual(saved.status_code,200,saved.text)
            raw=json.loads(self.edit_request(subject,current(),'lock-observed-offset',title=None))
            raw['edit']['changes']=[dict(item_id='b',field='fixed',value=dict(state='known',value=True))]
            p=self.prepare_request(client,subject,packed(raw));saved=self.save_request(client,subject,p,'lock-observed-offset')
            self.assertEqual(saved.status_code,200,saved.text);original=current()
        result=self.replan(subject,'retained-offset-plan')
        with TestClient(app) as client:
            proposed=client.get('/v2/trip-needs-proposals',params={'proposal_id':result.proposal_id},headers=self.host.headers[subject])
            self.assertEqual(proposed.status_code,200,proposed.text)
            self.assertEqual(proposed.json()['proposal']['content']['items'],original['content']['items'])
    def test_model_cannot_add_an_offset_to_the_adopted_unknown_event(self):
        from cj_agent.draft import proposal_id_for
        subject='new-offset';app,outcome,db=self.plan(subject)
        with TestClient(app) as client:
            accepted=self.post(client,subject,self.action(subject,outcome,'accept'));self.assertEqual(accepted.status_code,200,accepted.text)
        def invent(document):document['items'][1]['schedule']['start']['utc_offset']=dict(state='known',value='+08:00')
        result=self.replan(subject,'invented-offset-plan',invent,False)
        with db.connect(scope_for(ISSUER,subject)) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_proposal WHERE proposal_id=%s',(proposal_id_for(result.run_id),)).fetchone()[0],0)
            self.assertEqual(conn.execute("SELECT count(*) FROM cj_run_event WHERE run_id=%s AND kind='effect_committed'",(result.run_id,)).fetchone()[0],0)
            self.assertEqual(conn.execute('SELECT trip_version FROM cj_trip_needs_current').fetchone()[0],1)

    def test_invalid_model_structure_preserves_answer_and_uses_original_rejection(self):
        subject='malformed-model';app,outcome,db=self.plan(subject)
        with TestClient(app) as client:
            accepted=self.post(client,subject,self.action(subject,outcome,'accept'));self.assertEqual(accepted.status_code,200,accepted.text)
        def malformed(document):del document['items'][1]['fixed']
        result=self.replan(subject,'invalid-model-plan',malformed,False)
        self.assertEqual(result.status,'completed')
        with db.connect(scope_for(ISSUER,subject)) as conn:
            self.assertEqual(conn.execute("SELECT value FROM cj_run_event WHERE run_id=%s AND kind='draft_outcome'",(result.run_id,)).fetchone()[0],'validation_failed')
            self.assertEqual(conn.execute('SELECT trip_version FROM cj_trip_needs_current').fetchone()[0],1)
            self.assertEqual(conn.execute("SELECT count(*) FROM cj_run_event WHERE run_id=%s AND kind='effect_committed'",(result.run_id,)).fetchone()[0],0)

    def test_actual_manual_commit_during_model_io_rejects_old_publication(self):
        subject='edit-during-model';app,outcome,db=self.plan(subject)
        with TestClient(app) as client:
            accepted=self.post(client,subject,self.action(subject,outcome,'accept'));self.assertEqual(accepted.status_code,200,accepted.text)
            trip_id=accepted.json()['receipt']['trip_id']
            def edit_during_model(document):
                trip=client.get('/v4/trip-structured',params={'trip_id':trip_id},headers=self.host.headers[subject]).json()['trip']
                p=self.prepare_request(client,subject,self.edit_request(subject,trip,'model-intervening-edit'))
                saved=self.save_request(client,subject,p,'model-intervening-save');self.assertEqual(saved.status_code,200,saved.text)
            result=self.replan(subject,'stale-current-plan',edit_during_model,False)
            self.assertEqual(result.status,'unknown')
            trip=client.get('/v4/trip-structured',params={'trip_id':trip_id},headers=self.host.headers[subject]).json()['trip']
            self.assertEqual(trip['version'],2);self.assertEqual(trip['content']['title'],'explicit edited title')
        with db.connect(scope_for(ISSUER,subject)) as conn:
            self.assertEqual(conn.execute('SELECT trip_version FROM cj_trip_needs_current').fetchone()[0],2)
            self.assertEqual(conn.execute("SELECT count(*) FROM cj_run_event WHERE run_id=%s AND kind='effect_committed'",(result.run_id,)).fetchone()[0],0)

    def test_actual_accept_original_replay_and_owner_source_context(self):
        app,outcome,db=self.plan('accept');raw=self.action('accept',outcome,'accept')
        with TestClient(app) as client:
            response=self.post(client,'accept',raw);self.assertEqual(response.status_code,200,response.text)
            receipt=response.json()['receipt'];self.assertEqual(receipt['committed_version'],1)
            self.assertEqual(self.post(client,'accept',raw).json()['receipt'],receipt)
            changed=json.loads(raw);changed['kind']='reject'
            self.assertEqual(self.post(client,'accept',packed(changed)).status_code,409)
            source=client.get('/v4/trip-structured',params={'trip_id':receipt['trip_id']},headers=self.host.headers['accept'])
            self.assertEqual(source.status_code,200,source.text)
            self.assertEqual(source.json()['trip']['content']['content_version'],'structured.2')
            self.assertNotEqual(self.post(client,'reject',raw).status_code,200)
            found=client.get('/v1/trip-needs-action-receipts',params={'action_id':'accept-accept'},headers=self.host.headers['accept'])
            self.assertEqual(found.json()['receipt'],receipt)
        with db.connect(scope_for(ISSUER,'accept')) as conn:
            self.assertEqual(conn.execute('SELECT trip_id,trip_version FROM cj_trip_needs_current').fetchone(),(receipt['trip_id'],1))

    def test_source_corrected_before_accept_refuses_but_explicit_reject_remains(self):
        app,outcome,db=self.plan('stale');raw=self.action('stale',outcome,'accept')
        with patch.dict(__import__('os').environ,self.env),self.host.api('stale') as writer:
            correction=json.dumps(dict(action_id='correct-first',needs_id='visit',expected_version=1,
                source=dict(kind='manual',text='changed source'),changes=dict(party_size=dict(state='known',value=4)))).encode()
            self.assertEqual(writer.post('/v1/needs-actions',content=correction,
                headers={**self.host.headers['stale'],'Content-Type':'application/octet-stream'}).status_code,200)
        with TestClient(app) as client:
            denied=self.post(client,'stale',raw);self.assertEqual(denied.status_code,503,denied.text)
            rejected=json.loads(raw);rejected.update(kind='reject',action_id='reject-stale')
            response=self.post(client,'stale',packed(rejected));self.assertEqual(response.status_code,200,response.text)
            self.assertIsNone(response.json()['receipt']['committed_version'])
        with db.connect(scope_for(ISSUER,'stale')) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_record').fetchone()[0],0)
    def test_source_bound_manual_title_time_lock_unlock_and_original_versions(self):
        from hashlib import sha256
        app,outcome,db=self.plan('manual');raw=self.action('manual',outcome,'accept')
        with TestClient(app) as client:
            accepted=self.post(client,'manual',raw);self.assertEqual(accepted.status_code,200,accepted.text)
            trip_id=accepted.json()['receipt']['trip_id']
            def current():
                result=client.get('/v4/trip-structured',params={'trip_id':trip_id},headers=self.host.headers['manual'])
                self.assertEqual(result.status_code,200,result.text)
                return result.json()['trip']
            def edit(request_id,title=None,changes=()):
                value=current()
                return packed(dict(version='TRIP-needs-edit.1',needs_reference=dict(id='visit',expected_version=1),
                    edit=dict(version='TRIP-manual-edit.2',request_id=request_id,trip_id=trip_id,
                        expected_version=value['version'],original_hash=sha256(packed(value['content'])).hexdigest(),
                        title=title,changes=list(changes),order=None)))
            def prepare_save(request_id,title=None,changes=()):
                body=edit(request_id,title,changes)
                prepared=client.post('/v1/trip-needs-edits',content=body,
                    headers={**self.host.headers['manual'],'Content-Type':'application/octet-stream'})
                self.assertEqual(prepared.status_code,200,prepared.text)
                p=prepared.json()['preparation']
                save=packed(dict(version='TRIP-needs-save.1',action_id='save-'+request_id,
                    proposal_id=p['proposal_id'],candidate_hash=p['candidate_hash']))
                result=client.post('/v1/trip-needs-saves',content=save,
                    headers={**self.host.headers['manual'],'Content-Type':'application/octet-stream'})
                self.assertEqual(result.status_code,200,result.text)
                self.assertEqual(client.post('/v1/trip-needs-saves',content=save,
                    headers={**self.host.headers['manual'],'Content-Type':'application/octet-stream'}).json()['receipt'],result.json()['receipt'])
                return result.json()['receipt']
            before=current();first=prepare_save('title-change','用户标题 / explicit title')
            self.assertEqual(first['committed_version'],2)
            self.assertEqual(current()['content']['items'],before['content']['items'])
            locked=prepare_save('local-lock',changes=[dict(item_id='b',field='fixed',value=dict(state='known',value=True))])
            self.assertEqual(locked['committed_version'],3)
            # A later real planning run receives the committed local fixed state.
            with patch.dict(__import__('os').environ,self.env),self.host.api('manual') as message_client:
                chat=message_client.put('/v1/conversations',params={'conversation_id':'replan'},headers=self.host.headers['manual']).json()
                original=json.dumps(dict(version='MESSAGE-send.2',conversation_id='replan',message_id='replan-manual',
                    text='继续原安排 / continue adopted plan',trip_id=None,creation_intent='consider_trip',
                    expected_generation=chat['generation'],expected_sequence=0,travel_context=None,
                    needs_reference=dict(id='visit',expected_version=1))).encode()
                self.assertEqual(message_client.post('/v2/messages',content=original,
                    headers={**self.host.headers['manual'],'Content-Type':'application/octet-stream'}).status_code,200)
            from cj_agent.provider import FakeProvider
            from cj_draft.needs_publisher import SYSTEM
            from cj_draft.needs_context import publisher as context_publisher
            from cj_api.local_worker_context import checker_for
            seen=[]
            class ContextModel(FakeProvider):
                def stream(self,messages,system=None):
                    if system!=SYSTEM:
                        yield from super().stream(messages,system);return
                    self.calls+=1;source=json.loads(messages[-1]['content']);seen.append(source['current_trip'])
                    content=source['current_trip']['content']
                    yield json.dumps(dict(version='TRIP-model-plan.1',title=content['title'],items=content['items'],proposed_subjects={}),ensure_ascii=False)
            model=ContextModel();planning,database=self.worker('manual',model)
            planning.drafts=context_publisher(database,checker_for(self.host.auth),planning.message_context,
                lambda:self.host.headers['manual']['Authorization'][7:],scope_for(ISSUER,'manual'))
            planned=planning.process()[0]
            self.assertIsNotNone(planned.proposal_id)
            self.assertEqual(seen[0]['version'],3)
            self.assertEqual(seen[0]['content']['items'][1]['fixed'],dict(state='known',value=True))
            denied=client.post('/v1/trip-needs-edits',content=edit('incidental-edit',changes=[dict(item_id='b',field='text',value='not selected unlock')]),
                headers={**self.host.headers['manual'],'Content-Type':'application/octet-stream'})
            self.assertEqual(denied.status_code,409,denied.text)
            unlocked=prepare_save('local-unlock',changes=[dict(item_id='b',field='fixed',value=dict(state='known',value=False))])
            self.assertEqual(unlocked['committed_version'],4)
            old=current()['content']['items'][1]['schedule']
            revised=json.loads(json.dumps(old));revised['start']['time']=dict(state='known',value='12:00');revised['end']['time']=dict(state='known',value='13:00')
            timed=prepare_save('time-change',changes=[dict(item_id='b',field='schedule',value=revised)])
            self.assertEqual(timed['committed_version'],5)
            self.assertEqual(current()['content']['items'][0],before['content']['items'][0])
            stale=json.loads(self.action('manual',planned,'accept'));stale['action_id']='adopt-old-replan'
            refused=self.post(client,'manual',packed(stale))
            self.assertEqual(refused.status_code,409,refused.text)
            self.assertEqual(current()['version'],5)
            recovered=client.get('/v1/trip-needs-action-receipts',params={'action_id':'adopt-old-replan'},headers=self.host.headers['manual'])
            self.assertIsNone(recovered.json()['receipt'])

    def test_original_actions_survive_rollback_ack_unknown_and_rebuild(self):
        from cj_api.local_app import LocalDatabase
        for subject in ('fault-rollback','fault-ack'):
            with self.subTest(subject=subject):
                app,outcome,db=self.plan(subject);raw=self.action(subject,outcome,'accept')
                connect=LocalDatabase.connect
                class Cursor:
                    def __init__(self,base,owner):self.base,self.owner=base,owner
                    def __getattr__(self,name):return getattr(self.base,name)
                    def execute(self,query,*args,**kwargs):
                        if query.startswith('INSERT INTO cj_trip_needs_action'):
                            self.owner.saved=True
                            if subject=='fault-rollback':raise OSError('synthetic rollback')
                        self.base.execute(query,*args,**kwargs);return self
                class Connection:
                    def __init__(self,base):self.base,self.saved=base,False
                    def __getattr__(self,name):return getattr(self.base,name)
                    def __enter__(self):return self.base.__enter__()
                    def __exit__(self,*args):return self.base.__exit__(*args)
                    def cursor(self,*args,**kwargs):return Cursor(self.base.cursor(*args,**kwargs),self)
                    def commit(self):
                        self.base.commit()
                        if self.saved and subject=='fault-ack':raise OSError('synthetic ACK lost')
                def wrapped(database,*args,**kwargs):return Connection(connect(database,*args,**kwargs))
                with patch.object(LocalDatabase,'connect',wrapped),TestClient(app) as client:
                    response=self.post(client,subject,raw)
                self.assertEqual(response.status_code,503,response.text)
                self.assertEqual(response.json()['error']['recovery'],'reconcile_original')
                rebuilt=create_local_needs_app(conninfo_path=CONNINFO,auth_dir=self.host.auth,
                    run_context=self.host.profiles[subject][1],confirmation_signer=self.signer)
                with TestClient(rebuilt) as client:
                    result=client.get('/v1/trip-needs-action-receipts',params={'action_id':'accept-'+subject},headers=self.host.headers[subject])
                    self.assertEqual(result.status_code,200,result.text)
                    if subject=='fault-rollback':self.assertIsNone(result.json()['receipt'])
                    else:
                        self.assertEqual(result.json()['receipt']['committed_version'],1)
                        self.assertEqual(self.post(client,subject,raw).json()['receipt'],result.json()['receipt'])

    def test_lio_planner_saves_two_versions_with_the_original_source_and_receipts(self):
        from dataclasses import replace
        from hashlib import sha256
        from time import sleep
        from cj_api.local_needs import protected_reader
        from cj_api.local_worker_context import checker_for
        from cj_draft.lio_plan import LioPlanPublisher
        from cj_draft.needs_context import publisher
        from cj_message.needs_binding import needs_scope_for
        from cj_run.core import Binding
        from cj_trip.current_needs_source import CurrentNeedsSource
        from cj_trip.domain import Denied
        from cj_trip.lio_history import plan_action_id, TripHead, Undo
        from cj_trip.needs_edit_store import NeedsEdits

        subject='lio-plan'
        owner=scope_for(ISSUER,subject)
        needs_scope=needs_scope_for(owner)
        message=self.setup_source(subject)
        admitted={message['message_id']:None}
        binding=Binding(owner,message['conversation_id'],message['generation'],message['message_id'],
                        message['run_id'],message['sequence'])

        def original_needs(cursor,binding):
            cursor.execute('SELECT needs_id,needs_version,content_sha256 FROM cj_message_needs_binding '
                           'WHERE message_scope=%s AND message_id=%s AND run_id=%s',
                           (binding.scope,binding.message_id,binding.run_id))
            return cursor.fetchone()

        class FixtureLioPublisher(LioPlanPublisher):
            def publish_for_message(self,*args,before_publish):
                def final(*,check_trip):
                    before_publish()
                    if args[0].message_id == 'lio-omit-trip-check':
                        return
                    if args[0].message_id == 'lio-expired':
                        sleep(2.05)
                    check_trip()
                return super().publish_for_message(*args,before_publish=final)

        def wrap(publisher,signer=None):
            # Isolated stand-in for the still separate B-owned Lio admission.
            return FixtureLioPublisher(publisher,signer or self.signer,original_needs,lambda binding,original,expected:
                                    binding.message_id in admitted and admitted[binding.message_id] == expected
                                    and original.receipt.run_id == binding.run_id)

        worker,db=self.worker(subject,source_fixture.PlanModel())
        worker.drafts=wrap(publisher(db,checker_for(self.host.auth),worker.message_context,
                                    lambda:self.host.headers[subject]['Authorization'][7:],owner))
        repository=worker.drafts.repository
        self.assertIsNone(repository.lio_current_trip(needs_scope,'visit'))
        self.assertIsNone(repository.lio_plan_receipt(binding))
        first=worker.process()[0]
        self.assertEqual(first.status,'completed')
        saved=repository.lio_plan_receipt(binding)
        self.assertEqual(saved.committed_version,1)
        original=repository.detail(saved.trip_id)
        self.assertEqual(repository.proposal_detail(first.proposal_id).status,'accepted')

        with patch.dict(__import__('os').environ,self.env),self.host.api(subject) as client:
            source=json.dumps(dict(action_id='source-restated',needs_id='visit',expected_version=1,
                source=dict(kind='manual',text='restated exact commitments'),
                changes=dict(fixed_items=[source_fixture.fixed('a','09:00','10:00',True),
                                          source_fixture.fixed('b','11:00','12:00',False)]))).encode()
            response=client.post('/v1/needs-actions',content=source,
                headers={**self.host.headers[subject],'Content-Type':'application/octet-stream'})
            self.assertEqual(response.status_code,200,response.text)
        admitted['lio-replan']=TripHead.from_trip(original)
        second=self.replan(subject,'lio-replan',lambda plan:plan.update(title='Updated trip'),
                           wrap_publisher=wrap,needs_version=2,legacy_delta=True)
        saved_again=repository.query_action(plan_action_id(second.run_id))
        self.assertEqual((saved_again.trip_id,saved_again.committed_version),(saved.trip_id,2))
        updated=repository.detail(saved.trip_id)
        self.assertEqual(json.loads(updated.content)['title'],'Updated trip')
        self.assertEqual(json.loads(original.content)['items'],json.loads(updated.content)['items'])
        self.assertEqual(len(repository.list_trips()),1)
        self.assertEqual(repository.lio_current_trip(needs_scope,'visit'),
                         TripHead(saved.trip_id,2,sha256(updated.content).hexdigest()))
        self.assertEqual(repository.lio_plan_receipt(binding),saved)
        with self.assertRaises(Denied):
            repository.lio_plan_receipt(replace(binding,message_id='another-message'))
        admitted['lio-expired']=TripHead.from_trip(updated)
        expiring=ConfirmationSigner(self.signer.key,lifetime_seconds=2)
        expired=self.replan(subject,'lio-expired',expect_proposal=False,
                             wrap_publisher=lambda publisher:wrap(publisher,expiring),needs_version=2)
        self.assertEqual(expired.status,'completed')
        expired_message=worker.messages.query('lio-expired')
        expired_state=db.run_repository(owner).snapshot_optional(worker._binding(expired_message.receipt))
        self.assertEqual(expired_state.draft_outcome,'validation_failed')
        self.assertIsNone(repository.query_action(plan_action_id(expired.run_id)))
        self.assertEqual(repository.detail(saved.trip_id),updated)
        admitted['lio-omit-trip-check']=TripHead.from_trip(updated)
        omitted=self.replan(subject,'lio-omit-trip-check',expect_proposal=False,
                            wrap_publisher=wrap,needs_version=2)
        self.assertEqual(omitted.status,'unknown')
        self.assertIsNone(repository.query_action(plan_action_id(omitted.run_id)))
        self.assertEqual(repository.detail(saved.trip_id),updated)
        admitted['lio-stale']=TripHead.from_trip(original)
        stale=self.replan(subject,'lio-stale',expect_proposal=False,wrap_publisher=wrap,needs_version=2)
        self.assertEqual(stale.status,'unknown')
        self.assertIsNone(repository.query_action(plan_action_id(stale.run_id)))
        self.assertEqual(repository.detail(saved.trip_id),updated)

        checker=checker_for(self.host.auth)
        token=self.host.headers[subject]['Authorization'][7:]
        repository.needs_edits=NeedsEdits(CurrentNeedsSource(db,checker,token,protected_reader(db,checker)))
        request=Undo.parse(packed(dict(version='TRIP-lio-undo.1',action_id='undo-lio-replan',
            trip_id=saved.trip_id,expected_version=2,original_hash=sha256(updated.content).hexdigest())))
        self.assertEqual(repository.undo_lio(request).committed_version,3)
        self.assertEqual(repository.detail(saved.trip_id).content,original.content)

    def test_lio_travel_message_saves_one_replacement_and_can_undo_it(self):
        from copy import deepcopy
        from datetime import datetime, timezone
        from hashlib import sha256
        from cj_api.local_needs import protected_reader
        from cj_api.local_worker_context import checker_for
        from cj_draft.lio_plan import LioPlanPublisher
        from cj_draft.needs_context import publisher
        from cj_feasibility.solver import Limits
        from cj_trip.current_needs_source import CurrentNeedsSource
        from cj_trip.lio_history import TripHead, Undo, edit_action_id
        from cj_trip.needs_edit_store import NeedsEdits

        subject='lio-edit'
        owner=scope_for(ISSUER,subject)
        first=self.setup_source(subject)
        admitted={first['message_id']:None}
        limits=Limits(datetime(2026,11,1,tzinfo=timezone.utc),7*86400,1,10_000_000,60,120,128,.05,.05,100)

        def generated(plan):
            plan['items'][1].update(text='Accepted lunch override',source_category='unknown')
            item=deepcopy(plan['items'][1])
            item.update(id='generated',text='Jingshan Park',fixed=dict(state='unknown'),source_category='unknown')
            item['schedule']['start']['time']=dict(state='known',value='13:00')
            item['schedule']['end']['time']=dict(state='known',value='14:00')
            plan['items'].append(item)
            plan['proposed_subjects']['generated']=['self']

        def original_needs(cursor,binding):
            return cursor.execute('SELECT needs_id,needs_version,content_sha256 FROM cj_message_needs_binding '
                'WHERE message_scope=%s AND message_id=%s AND run_id=%s',
                (binding.scope,binding.message_id,binding.run_id)).fetchone()

        class FixturePublisher(LioPlanPublisher):
            def publish_for_message(self,binding,original,current,reply,capture,*,before_publish):
                def final(*,check_trip):
                    before_publish()
                    check_trip()
                if binding.message_id==first['message_id']:
                    return super().publish_for_message(binding,original,current,reply,capture,before_publish=final)
                trip=self.source.contexts[binding].trip
                item='a' if binding.message_id=='lio-edit-locked' else 'generated'
                identity=dict(request_id=binding.message_id,trip_id=trip.trip_id,expected_version=trip.version,
                              original_hash=sha256(trip.content).hexdigest())
                request=packed(dict(identity,version='TRIP-scoped-request.1',text=json.loads(original.raw)['text'],
                                    language='en',selection=dict(kind='items',item_ids=[item])))
                change=packed(dict(identity,version='TRIP-manual-edit.2',title=None,order=None,
                                   changes=[dict(item_id=item,field='text',value='Summer Palace')]))
                return self.publish_edit_for_message(binding,original,current,request,change,capture,
                                                     limits=limits,before_publish=final)

        def wrap(base):
            return FixturePublisher(base,self.signer,original_needs,lambda binding,original,expected:
                binding.message_id in admitted and admitted[binding.message_id]==expected
                and original.receipt.run_id==binding.run_id)

        worker,db=self.worker(subject,source_fixture.PlanModel(generated))
        checker=checker_for(self.host.auth)
        token=self.host.headers[subject]['Authorization'][7:]
        worker.drafts=wrap(publisher(db,checker,worker.message_context,lambda:token,owner))
        self.assertEqual(worker.process()[0].status,'completed')
        repository=worker.drafts.repository
        original,=repository.list_trips()
        before=json.loads(original.content)
        self.assertEqual(before['items'][-1]['fixed'],dict(state='known',value=False))
        self.assertEqual(before['items'][-1]['verification'],'pending')
        self.assertEqual(before['items'][0]['fixed'],dict(state='known',value=True))
        self.assertEqual(before['items'][1]['text'],'Accepted lunch override')

        admitted['lio-edit-locked']=TripHead.from_trip(original)
        locked=self.replan(subject,'lio-edit-locked',expect_proposal=False,wrap_publisher=wrap,
                           text='Replace the original a with Summer Palace')
        self.assertIsNone(repository.query_action(edit_action_id(locked.run_id)))
        self.assertEqual(repository.detail(original.trip_id),original)

        admitted['lio-edit-replace']=TripHead.from_trip(original)
        result=self.replan(subject,'lio-edit-replace',wrap_publisher=wrap,
                           text='Replace Jingshan Park with Summer Palace')
        stored=worker.messages.query('lio-edit-replace')
        binding=worker._binding(stored.receipt)
        receipt=repository.lio_edit_receipt(binding)
        self.assertEqual((receipt.proposal_id,receipt.trip_id,receipt.committed_version),
                         (result.proposal_id,original.trip_id,2))
        self.assertIsNone(repository.lio_plan_receipt(binding))
        edited=repository.detail(original.trip_id)
        after=json.loads(edited.content)
        before['items'][-1]['text']='Summer Palace'
        self.assertEqual(after,before)

        repository.needs_edits=NeedsEdits(CurrentNeedsSource(db,checker,token,protected_reader(db,checker)))
        action=Undo.parse(packed(dict(version='TRIP-lio-undo.1',action_id='undo-lio-edit',
            trip_id=original.trip_id,expected_version=2,original_hash=sha256(edited.content).hexdigest())))
        self.assertEqual(repository.undo_lio(action).committed_version,3)
        restored=repository.detail(original.trip_id)
        self.assertEqual(restored.content,original.content)
        self.assertEqual(repository.lio_edit_receipt(binding),receipt)

        with patch.dict(__import__('os').environ,self.env),self.host.api(subject) as client:
            source=json.dumps(dict(action_id='edit-source-restated',needs_id='visit',expected_version=1,
                source=dict(kind='manual',text='restated commitments'),
                changes=dict(fixed_items=[source_fixture.fixed('a','09:00','10:00',True),
                                          source_fixture.fixed('b','11:00','12:00',False)]))).encode()
            response=client.post('/v1/needs-actions',content=source,
                headers={**self.host.headers[subject],'Content-Type':'application/octet-stream'})
            self.assertEqual(response.status_code,200,response.text)
        admitted['lio-edit-new-source']=TripHead.from_trip(restored)
        newer=self.replan(subject,'lio-edit-new-source',expect_proposal=False,wrap_publisher=wrap,
                          needs_version=2,text='Replace Jingshan Park with Summer Palace')
        self.assertIsNone(repository.query_action(edit_action_id(newer.run_id)))
        self.assertEqual(repository.detail(original.trip_id),restored)

    def test_lio_undo_appends_original_bytes_and_keeps_the_accepted_history(self):
        from contextlib import contextmanager
        from dataclasses import asdict
        from hashlib import sha256
        from cj_agent.draft import trip_scope_for
        from cj_api.local_needs import protected_reader
        from cj_api.local_worker_context import checker_for
        from cj_needs.domain import Denied as NeedsDenied
        from cj_trip.auth_boundary import Boundary
        from cj_trip.current_needs_source import CurrentNeedsSource
        from cj_trip.domain import Conflict, Denied
        from cj_trip.lio_history import Undo
        from cj_trip.needs_edit_store import NeedsEdits
        from cj_trip.operation import OperationWithheld

        subject='lio-history'
        app,outcome,db=self.plan(subject)
        with TestClient(app) as client:
            adopted=self.post(client,subject,self.action(subject,outcome,'accept'))
            self.assertEqual(adopted.status_code,200,adopted.text)
            trip_id=adopted.json()['receipt']['trip_id']
            params={'trip_id':trip_id}
            headers=self.host.headers[subject]
            original=client.get('/v4/trip-structured',params=params,headers=headers).json()['trip']
            prepared=self.prepare_request(client,subject,self.edit_request(subject,original,'before-undo'))
            saved=self.save_request(client,subject,prepared,'original-edit')
            self.assertEqual(saved.status_code,200,saved.text)
            edited=client.get('/v4/trip-structured',params=params,headers=headers).json()['trip']

        checker=checker_for(self.host.auth)
        def resolve(principal):
            scope=scope_for(principal.issuer,principal.subject)
            return lambda:db.connect(scope),trip_scope_for(scope)

        class SourceBoundary(Boundary):
            def _bind(self, token):
                repository,principal,guard=super()._bind(token)
                source=CurrentNeedsSource(db,checker,token,protected_reader(db,checker))
                repository.needs_edits=NeedsEdits(source)
                return repository,principal,guard

        boundary=SourceBoundary(checker,resolve,self.signer,structured=True)
        token=headers['Authorization'][7:]
        repository=boundary._repository(token)
        command=dict(version='TRIP-lio-undo.1',action_id='lio-undo',trip_id=trip_id,expected_version=2,
                     original_hash=sha256(packed(edited['content'])).hexdigest())
        request=Undo.parse(packed(command))

        changed=Undo.parse(packed(dict(command,original_hash='0'*64)))
        with self.assertRaises(Conflict):
            repository.undo_lio(changed)
        foreign=boundary._repository(self.host.headers['scoped-preview']['Authorization'][7:])
        with self.assertRaises(Denied):
            foreign.lio_revisions(trip_id,None,10)
        with self.assertRaises(Denied):
            foreign.undo_lio(request)

        def apply(operation):
            return packed(asdict(operation.undo_lio(request)))
        hold=CurrentNeedsSource.hold

        @contextmanager
        def lose_source_after_commit(current_source,captured):
            with hold(current_source,captured) as check:
                yield check
                raise NeedsDenied('synthetic loss after committed undo')

        with patch.object(CurrentNeedsSource,'hold',lose_source_after_commit):
            with self.assertRaises(OperationWithheld) as withheld:
                boundary.with_operation(token,apply)
        self.assertEqual(withheld.exception.action_id,request.action_id)
        self.assertTrue(withheld.exception.commit_possible)
        receipt=boundary.with_operation(token,lambda op:packed(asdict(op.lio_undo_receipt(request))))
        self.assertEqual(json.loads(receipt)['committed_version'],3)
        self.assertEqual(boundary.with_operation(token,apply),receipt)
        self.assertEqual(boundary.with_operation(token,lambda op:packed(asdict(op.lio_undo_receipt(request)))),receipt)
        with self.assertRaises(Conflict):
            repository.undo_lio(changed)
        self.assertEqual(packed(asdict(repository.query_action(request.action_id))),receipt)
        history=repository.lio_revisions(trip_id,None,10)
        self.assertEqual([(trip.version,trip.content) for trip in history],
                         [(3,packed(original['content'])),(2,packed(edited['content'])),(1,packed(original['content']))])
        self.assertEqual(repository.lio_revisions(trip_id,3,1),history[1:2])

        with TestClient(app) as client:
            restored=client.get('/v4/trip-structured',params=params,headers=headers).json()['trip']
            self.assertEqual(restored['content'],original['content'])
            prepared=self.prepare_request(client,subject,self.edit_request(subject,restored,'after-undo','next edit'))
            self.assertEqual(self.save_request(client,subject,prepared,'after-undo-save').json()['receipt']['committed_version'],4)
            after=client.get('/v4/trip-structured',params=params,headers=headers).json()['trip']
            lock=json.loads(self.edit_request(subject,after,'lock-after-undo'))
            lock['edit']['changes']=[dict(item_id='b',field='fixed',value=dict(state='known',value=True))]
            prepared=self.prepare_request(client,subject,packed(lock))
            self.assertEqual(self.save_request(client,subject,prepared,'lock-after-undo-save').json()['receipt']['committed_version'],5)
        locked=repository.detail(trip_id)
        forbidden=Undo.parse(packed(dict(command,action_id='undo-lock',expected_version=5,
                                        original_hash=sha256(locked.content).hexdigest())))
        with self.assertRaisesRegex(Conflict,'fixed Trip item'):
            repository.undo_lio(forbidden)
        self.assertEqual(repository.detail(trip_id),locked)
        self.assertIsNone(repository.query_action(forbidden.action_id))

    def test_adopted_model_intent_lock_is_retained_by_next_real_planning(self):
        from copy import deepcopy
        from hashlib import sha256
        def new_item(value):
            item=deepcopy(value['items'][1]);item.update(id='c',text='提出的新活动 / adopted intent',fixed=dict(state='unknown'),source_category='unknown')
            item['schedule']['start']['time']=dict(state='known',value='13:00')
            item['schedule']['end']['time']=dict(state='known',value='14:00')
            value['items'].append(item);value['proposed_subjects']['c']=['self']
        app,outcome,db=self.plan('adopted',new_item);raw=self.action('adopted',outcome,'accept')
        with TestClient(app) as client:
            saved=self.post(client,'adopted',raw);self.assertEqual(saved.status_code,200,saved.text)
            trip_id=saved.json()['receipt']['trip_id']
            current=client.get('/v4/trip-structured',params={'trip_id':trip_id},headers=self.host.headers['adopted']).json()['trip']
            body=packed(dict(version='TRIP-needs-edit.1',needs_reference=dict(id='visit',expected_version=1),
                edit=dict(version='TRIP-manual-edit.2',request_id='lock-c',trip_id=trip_id,expected_version=1,
                    original_hash=sha256(packed(current['content'])).hexdigest(),title=None,
                    changes=[dict(item_id='c',field='fixed',value=dict(state='known',value=True))],order=None)))
            prepared=client.post('/v1/trip-needs-edits',content=body,headers={**self.host.headers['adopted'],'Content-Type':'application/octet-stream'})
            self.assertEqual(prepared.status_code,200,prepared.text);p=prepared.json()['preparation']
            save=packed(dict(version='TRIP-needs-save.1',action_id='lock-c-save',proposal_id=p['proposal_id'],candidate_hash=p['candidate_hash']))
            locked=client.post('/v1/trip-needs-saves',content=save,headers={**self.host.headers['adopted'],'Content-Type':'application/octet-stream'})
            self.assertEqual(locked.status_code,200,locked.text)
        with patch.dict(__import__('os').environ,self.env),self.host.api('adopted') as client:
            chat=client.put('/v1/conversations',params={'conversation_id':'c-next'},headers=self.host.headers['adopted']).json()
            message=json.dumps(dict(version='MESSAGE-send.2',conversation_id='c-next',message_id='c-next',text='continue',trip_id=None,
                creation_intent='consider_trip',expected_generation=chat['generation'],expected_sequence=0,travel_context=None,
                needs_reference=dict(id='visit',expected_version=1))).encode()
            self.assertEqual(client.post('/v2/messages',content=message,headers={**self.host.headers['adopted'],'Content-Type':'application/octet-stream'}).status_code,200)
        from cj_agent.provider import FakeProvider
        from cj_draft.needs_publisher import SYSTEM
        from cj_draft.needs_context import publisher as context_publisher
        from cj_api.local_worker_context import checker_for
        seen=[]
        class SameContextModel(FakeProvider):
            def stream(self,messages,system=None):
                if system!=SYSTEM:
                    yield from super().stream(messages,system);return
                self.calls+=1;source=json.loads(messages[-1]['content']);seen.append(source['current_trip'])
                content=source['current_trip']['content']
                yield json.dumps(dict(version='TRIP-model-plan.1',title=content['title'],items=content['items'],proposed_subjects={}),ensure_ascii=False)
        worker,database=self.worker('adopted',SameContextModel())
        worker.drafts=context_publisher(database,checker_for(self.host.auth),worker.message_context,
            lambda:self.host.headers['adopted']['Authorization'][7:],scope_for(ISSUER,'adopted'))
        result=worker.process()[0];self.assertIsNotNone(result.proposal_id)
        self.assertEqual(seen[0]['content']['items'][-1]['fixed'],dict(state='known',value=True))
        self.assertEqual(seen[0]['proposed_fields']['fixed_items'][-1]['applies_to'],['self'])



    def test_scoped_preview_reuses_actual_source_checker_without_write(self):
        from cj_trip.current_needs_source import CurrentNeedsSource
        from cj_trip.domain import Trip
        from cj_api.local_app import scope_for,ISSUER
        from cj_api.local_needs import protected_reader
        from cj_api.local_worker_context import checker_for
        from cj_manual_edit.scoped import Request,resolve,preview
        from hashlib import sha256
        subject='scoped-preview';app,outcome,db=self.plan(subject)
        with TestClient(app) as client:
            accepted=self.post(client,subject,self.action(subject,outcome,'accept'));self.assertEqual(accepted.status_code,200,accepted.text)
            trip_id=accepted.json()['receipt']['trip_id']
            value=client.get('/v4/trip-structured',params={'trip_id':trip_id},headers=self.host.headers[subject]).json()['trip']
        trip=Trip(trip_id,value['version'],packed(value['content']))
        request=Request.parse(packed(dict(version='TRIP-scoped-request.1',request_id='scope-edit',trip_id=trip_id,
            expected_version=trip.version,original_hash=sha256(trip.content).hexdigest(),language='en',text='Make selected item lighter',
            selection=dict(kind='items',item_ids=['b']))))
        raw=packed(dict(version='TRIP-manual-edit.2',request_id='scope-edit',trip_id=trip_id,expected_version=trip.version,
            original_hash=request.original_hash,title=None,changes=[dict(item_id='b',field='text',value='proposed easier choice')],order=None))
        checker=checker_for(self.host.auth);token=self.host.headers[subject]['Authorization'][7:]
        source=CurrentNeedsSource(db,checker,token,protected_reader(db,checker));captured=source.capture('visit',1)
        with db.connect(scope_for(ISSUER,subject)) as conn:
            original_fields=json.loads(bytes(conn.execute('SELECT proposed_input FROM cj_trip_needs_basis WHERE proposal_id=%s',(outcome.proposal_id,)).fetchone()[0]))
        with source.hold(captured):
            result=preview(resolve(trip,request),raw,source=captured,previous_fields=original_fields)
        self.assertFalse(result.can_publish);self.assertIsNone(result.time_report)
        self.assertTrue(any(c.code=='PROTECTED_SCOPE_UNCHANGED' and c.status=='PASS' for c in result.constraint_report.checks))
        self.assertTrue(all(c.zh and c.en for c in result.constraint_report.checks))
        self.assertEqual(json.loads(result.candidate.content)['items'][1]['source_category'],'unknown')
        with db.connect(scope_for(ISSUER,subject)) as conn:
            self.assertEqual(conn.execute('SELECT version FROM cj_trip_record WHERE trip_id=%s',(trip_id,)).fetchone()[0],1)
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_receipt').fetchone()[0],1)
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_proposal').fetchone()[0],1)


from needs_discovery_pg import NeedsDiscoveryChecks

from place_chain_pg import PlaceChainChecks

if __name__=='__main__':unittest.main(verbosity=2)
