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
        cls.host=RegisteredHost(cls.auth/'needs-actions',Path(CONNINFO),{s:(12,2,30000) for s in ('accept','reject','stale','manual','fault-rollback','fault-ack','adopted','switch','manual-writer','manual-save','save-rollback','save-ack','schema','publish-replay')})
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

    def replan(self,subject,key):
        with patch.dict(__import__('os').environ,self.env),self.host.api(subject) as client:
            chat=client.put('/v1/conversations',params={'conversation_id':key},headers=self.host.headers[subject]).json()
            raw=json.dumps(dict(version='MESSAGE-send.2',conversation_id=key,message_id=key,text='continue original trip',trip_id=None,
                creation_intent='consider_trip',expected_generation=chat['generation'],expected_sequence=0,travel_context=None,
                needs_reference=dict(id='visit',expected_version=1))).encode()
            response=client.post('/v2/messages',content=raw,headers={**self.host.headers[subject],'Content-Type':'application/octet-stream'})
            self.assertEqual(response.status_code,200,response.text)
        from cj_agent.provider import FakeProvider
        from cj_draft.needs_publisher import SYSTEM
        from cj_draft.needs_context import publisher
        from cj_api.local_worker_context import checker_for
        class OriginalContextModel(FakeProvider):
            def stream(self,messages,system=None):
                if system!=SYSTEM:
                    yield from super().stream(messages,system);return
                self.calls+=1;source=json.loads(messages[-1]['content']);content=source['current_trip']['content']
                yield json.dumps(dict(version='TRIP-model-plan.1',title=content['title'],items=content['items'],proposed_subjects={}),ensure_ascii=False)
        worker,db=self.worker(subject,OriginalContextModel())
        worker.drafts=publisher(db,checker_for(self.host.auth),worker.message_context,
            lambda:self.host.headers[subject]['Authorization'][7:],scope_for(ISSUER,subject))
        result=worker.process()[0];self.assertIsNotNone(result.proposal_id)
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



if __name__=='__main__':unittest.main(verbosity=2)
