"""Actual signed source/RUN/model/diff/confirmation/act, private PG only."""
import sys,json,unittest
from pathlib import Path
from datetime import datetime,timezone
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend/memory/tests'),str(ROOT/'backend/agent/tests'),str(ROOT/'scripts')]
from edit_support import Fixture,ProbePublisher,Harness,CONNINFO
from cj_draft.scoped_publisher import local_configuration
from cj_trip.local_scoped_app import create_local_scoped_app
from cj_trip.domain import packed
from cj_feasibility.solver import Limits
from cj_api.local_app import create_local_app,load_history_configuration,scope_for,ISSUER
from cj_agent.provider import FakeProvider


def limits():return Limits(datetime(2026,11,1,tzinfo=timezone.utc),7*86400,1,10_000_000,60,120,128,.05,.05,100)


class Model(FakeProvider):
    def __init__(self,change=None):super().__init__();self.change=change;self.hook=None;self.inputs=[]
    def stream(self,messages,system=None):
        self.calls+=1;self.inputs.append(messages);yield ''
        if self.hook is not None:self.hook()
        if system is None:yield 'discussion only';return
        value=json.loads(system)
        document=dict(version=value['edit_version'],request_id=value['request_id'],trip_id=value['trip_id'],expected_version=value['expected_version'],
            original_hash=value['original_hash'],title=None,order=None,changes=[dict(item_id=value['selected_item_ids'][0],field='text',value='A lighter choice / 本次轻松一点')])
        if self.change:self.change(document)
        yield packed(document).decode()


class ScopedRuntimeChecks(unittest.TestCase):
    headers=Harness.headers;setUpClass=classmethod(Harness.setUpClass.__func__);tearDownClass=classmethod(Harness.tearDownClass.__func__)
    def fixture(self,subject,*,legacy=False):
        f=Fixture(self,subject,ProbePublisher(),legacy=legacy)
        credentials=lambda owner:f.host.headers[owner.removeprefix('local:'+ISSUER+':')]['Authorization'][7:]
        db,cfg=local_configuration(conninfo_path=CONNINFO,auth_dir=f.auth,run_context=f.context,memory=f.memory,credentials=credentials,
            confirmation=f.signer,limits=limits(),language='en')
        f.database,f.configuration=db,cfg
        f.app=create_local_app(conninfo_path=CONNINFO,auth_dir=f.auth,run_context=f.context,travel_context=True,edit_configuration=cfg,history_configuration=load_history_configuration(f.auth))
        return f
    def scoped(self,f):return create_local_scoped_app(database=f.database,configuration=f.configuration)
    def detail(self,client,f,pid):
        response=client.get('/v1/trip-scoped-proposals',params=dict(proposal_id=pid),headers=f.headers)
        self.assertEqual(response.status_code,200,response.text);return response.json()['proposal']
    def action(self,p,aid='original-accept',kind='accept'):
        return packed(dict(version='TRIP-scoped-action.1',action_id=aid,kind=kind,proposal_id=p['proposal_id'],candidate_hash=p['candidate_hash']))
    def post(self,client,f,raw):return client.post('/v1/trip-scoped-actions',content=raw,headers={**f.headers,'Content-Type':'application/octet-stream'})
    def test_actual_generate_diff_explicit_accept_read_and_original_replay(self):
        f=self.fixture('normal');binding=f.send('edit');model=Model();result=f.run(model)[0]
        self.assertEqual(result.status,'completed');self.assertIsNotNone(result.proposal_id)
        self.assertEqual(model.calls,1)
        with TestClient(self.scoped(f)) as client:
            p=self.detail(client,f,result.proposal_id)
            self.assertEqual(p['expected_version'],f.trip.version)
            self.assertEqual(p['diff']['before'],json.loads(f.trip.content))
            self.assertEqual(p['content']['items'][0],json.loads(f.trip.content)['items'][0])
            self.assertEqual(p['content']['items'][1]['source_category'],'unknown')
            self.assertEqual(p['feasibility']['status'],'UNKNOWN')
            raw=self.action(p);accepted=self.post(client,f,raw);self.assertEqual(accepted.status_code,200,accepted.text)
            receipt=accepted.json()['receipt'];self.assertEqual(receipt['committed_version'],f.trip.version+1)
            self.assertEqual(self.post(client,f,raw).json()['receipt'],receipt)
            from cj_trip.local_structured_read import create_local_structured_read_app
            read=create_local_structured_read_app(conninfo_path=CONNINFO,auth_dir=f.auth,run_context=f.context)
            with TestClient(read) as current:
                trip=current.get('/v5/trip-structured',params={'trip_id':f.trip.trip_id},headers=f.headers).json()['trip']
                self.assertEqual(trip['version'],f.trip.version+1);self.assertEqual(trip['content'],p['content'])
            changed=json.loads(raw);changed['kind']='reject';self.assertEqual(self.post(client,f,packed(changed)).status_code,409)
            wrong=client.get('/v1/trip-scoped-proposals',params=dict(proposal_id=p['proposal_id']),headers=f.host.headers['other-'+f.subject])
            self.assertEqual(wrong.status_code,503)
        state=f.database.run_repository(f.scope).recover(binding).state
        self.assertEqual(state.effects,('trip_proposal:'+p['proposal_id'],))
        with TestClient(self.scoped(f)) as rebuilt:
            self.assertEqual(self.post(rebuilt,f,raw).json()['receipt'],receipt)

    def generated(self,subject,change=None):
        f=self.fixture(subject);binding=f.send('edit');model=Model(change);outcome=f.run(model)[0]
        self.assertEqual(outcome.status,'completed');self.assertIsNotNone(outcome.proposal_id)
        return f,binding,outcome

    def test_actual_model_outside_scope_fixed_or_invalid_output_never_publishes(self):
        changes=[lambda d:d['changes'][0].update(item_id='a'),lambda d:d['changes'][0].update(field='fixed',value=dict(state='known',value=False)),
                 lambda d:d.update(expected_version=999),lambda d:d.pop('changes'),lambda d:d.update(modification_intent='propose_scoped_edit')]
        for index,change in enumerate(changes):
            with self.subTest(case=index):
                f=self.fixture('invalid-'+str(index));binding=f.send('edit');model=Model(change)
                outcome=f.run(model)[0];self.assertEqual(outcome.status,'completed');self.assertIsNone(outcome.proposal_id)
                state=f.database.run_repository(f.scope).recover(binding).state
                self.assertEqual(state.effects,());self.assertEqual(state.draft_outcome,'validation_failed')
                with f.database.connect(f.scope) as conn:
                    self.assertEqual(conn.execute('SELECT version,content FROM cj_trip_record WHERE trip_id=%s',(f.trip.trip_id,)).fetchone(),(f.trip.version,f.trip.content))
                    self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_scoped_basis').fetchone()[0],0)

    def test_memory_changed_after_proposal_refuses_accept_and_explicit_reject_retains_original(self):
        f,binding,outcome=self.generated('memory-after')
        with TestClient(self.scoped(f)) as client:
            p=self.detail(client,f,outcome.proposal_id);raw=self.action(p)
            f.manage('edit',1,text='new current preference')
            denied=self.post(client,f,raw);self.assertEqual(denied.status_code,503,denied.text)
            self.assertIsNone(client.get('/v1/trip-scoped-action-receipts',params={'action_id':'original-accept'},headers=f.headers).json()['receipt'])
            rejected=self.post(client,f,self.action(p,'reject-original','reject'));self.assertEqual(rejected.status_code,200,rejected.text)
            self.assertIsNone(rejected.json()['receipt']['committed_version'])
            self.assertEqual(self.detail(client,f,p['proposal_id'])['diff'],p['diff'])

    def test_original_accept_survives_rollback_unknown_ack_and_rebuild(self):
        from cj_api.local_app import LocalDatabase
        from unittest.mock import patch
        for mode in ('rollback','ack'):
            with self.subTest(mode=mode):
                f,binding,outcome=self.generated('action-'+mode)
                with TestClient(self.scoped(f)) as client:
                    p=self.detail(client,f,outcome.proposal_id);raw=self.action(p)
                connect=LocalDatabase.connect
                class Cursor:
                    def __init__(self,base,owner):self.base,self.owner=base,owner
                    def __getattr__(self,name):return getattr(self.base,name)
                    def execute(self,query,*args,**kw):
                        if query.startswith('INSERT INTO cj_trip_scoped_action'):
                            self.owner.wrote=True
                            if mode=='rollback':raise OSError('synthetic rollback after original act')
                        self.base.execute(query,*args,**kw);return self
                class Connection:
                    def __init__(self,base):self.base,self.wrote=base,False
                    def __getattr__(self,name):return getattr(self.base,name)
                    def __enter__(self):return self.base.__enter__()
                    def __exit__(self,*args):return self.base.__exit__(*args)
                    def cursor(self,*args,**kw):return Cursor(self.base.cursor(*args,**kw),self)
                    def commit(self):
                        self.base.commit()
                        if self.wrote and mode=='ack':raise OSError('synthetic physical commit ACK loss')
                def wrapped(db,*args,**kw):return Connection(connect(db,*args,**kw))
                with patch.object(LocalDatabase,'connect',wrapped),TestClient(self.scoped(f)) as client:
                    result=self.post(client,f,raw)
                self.assertEqual(result.status_code,503,result.text);self.assertEqual(result.json()['error']['recovery'],'reconcile_original')
                with TestClient(self.scoped(f)) as rebuilt:
                    response=rebuilt.get('/v1/trip-scoped-action-receipts',params={'action_id':'original-accept'},headers=f.headers)
                    self.assertEqual(response.status_code,200,response.text);receipt=response.json()['receipt']
                    if mode=='rollback':self.assertIsNone(receipt)
                    else:
                        self.assertEqual(receipt['committed_version'],f.trip.version+1)
                        self.assertEqual(self.post(rebuilt,f,raw).json()['receipt'],receipt)
                    self.assertEqual(self.detail(rebuilt,f,p['proposal_id'])['diff'],p['diff'])
                with f.database.connect(f.scope) as conn:
                    self.assertEqual(conn.execute('SELECT version FROM cj_trip_record WHERE trip_id=%s',(f.trip.trip_id,)).fetchone()[0],f.trip.version+(mode=='ack'))

    def test_same_original_action_concurrent_accept_reconciles_once(self):
        from concurrent.futures import ThreadPoolExecutor
        f,binding,outcome=self.generated('concurrent-action')
        with TestClient(self.scoped(f)) as client:
            p=self.detail(client,f,outcome.proposal_id);raw=self.action(p)
        def send():
            with TestClient(self.scoped(f)) as client:return self.post(client,f,raw)
        from unittest.mock import patch
        from cj_trip.scoped_actions import ScopedActions
        original_apply=ScopedActions.apply;errors=[]
        def traced(service,*args):
            try:return original_apply(service,*args)
            except Exception as exc:
                errors.append((type(exc).__name__,str(exc),type(exc.__cause__).__name__,str(exc.__cause__)))
                raise
        with patch.object(ScopedActions,'apply',traced),ThreadPoolExecutor(max_workers=2) as pool:
            results=[future.result(timeout=20) for future in [pool.submit(send),pool.submit(send)]]
        self.assertEqual([r.status_code for r in results],[200,200],errors or [r.text for r in results])
        self.assertEqual(results[0].json()['receipt'],results[1].json()['receipt'])
        with f.database.connect(f.scope) as conn:self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_scoped_action').fetchone()[0],1)

    def test_structured_one_keeps_precision_and_reports_missing_occupancy(self):
        f=self.fixture('structured-one',legacy=True);binding=f.send('edit');model=Model();outcome=f.run(model)[0]
        self.assertEqual(outcome.status,'completed');self.assertIsNotNone(outcome.proposal_id)
        with TestClient(self.scoped(f)) as client:
            p=self.detail(client,f,outcome.proposal_id)
            self.assertEqual(p['content']['content_version'],'structured.1')
            self.assertEqual(p['content']['items'][0]['schedule']['start']['time'],json.loads(f.trip.content)['items'][0]['schedule']['start']['time'])
            self.assertIn('TRIP_ITEM_METADATA_UNKNOWN',{v['code'] for v in p['feasibility']['checks']})
            result=self.post(client,f,self.action(p));self.assertEqual(result.status_code,200,result.text)
            self.assertEqual(result.json()['receipt']['committed_version'],f.trip.version+1)

    def test_current_source_cancel_unknown_and_late_trip_changes_have_zero_new_effect(self):
        from unittest.mock import patch
        from cj_api.local_app import LocalDatabase
        from cj_agent.provider import ProviderUnknown
        for mode in ('needs','cancel','trip'):
            with self.subTest(mode=mode):
                f=self.fixture('during-'+mode);binding=f.send('edit');model=Model()
                def change():
                    if mode=='needs':
                        app=create_local_app(conninfo_path=CONNINFO,auth_dir=f.auth,run_context=f.context,travel_context=True,
                            edit_configuration=f.configuration,needs_profile='manual-v1')
                        with TestClient(app) as client:
                            response=client.post('/v1/needs-actions',content=packed(dict(action_id='new-needs',needs_id='visit',expected_version=1,
                                source=dict(kind='manual',text='explicit changed input'),changes=dict(party_size=dict(state='known',value=3)))),
                                headers={**f.headers,'Content-Type':'application/octet-stream'})
                            self.assertEqual(response.status_code,200,response.text)
                    elif mode=='cancel':
                        with TestClient(f.app) as client:
                            response=client.post('/v4/run-cancellations',json=dict(version='RUN-cancel.4',message_id='edit'),headers=f.headers)
                            self.assertEqual(response.status_code,200,response.text)
                    else:
                        # Negative source mutation, not a positive formal Trip seed.
                        from cj_agent.draft import trip_scope_for
                        import psycopg
                        with psycopg.connect(**json.loads(Path(CONNINFO).read_text())) as admin:
                            admin.execute('SELECT scope FROM cj_trip_scope WHERE scope=%s FOR UPDATE',(trip_scope_for(f.scope),))
                            admin.execute('UPDATE cj_trip_record SET version=version+1 WHERE scope=%s AND trip_id=%s',(trip_scope_for(f.scope),f.trip.trip_id))
                model.hook=change;outcome=f.run(model)[0]
                self.assertIn(outcome.status,('context_invalid','cancelled'));self.assertIsNone(outcome.proposal_id)
                self.assertEqual(f.database.run_repository(f.scope).recover(binding).state.effects,())
                with f.database.connect(f.scope) as conn:self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_scoped_basis').fetchone()[0],0)
        f=self.fixture('model-unknown');binding=f.send('edit')
        class Unknown(Model):
            def stream(self,*args,**kw):self.calls+=1;raise ProviderUnknown('synthetic uncertain original model');yield
        model=Unknown();self.assertEqual(f.run(model)[0].status,'unknown');self.assertEqual(model.calls,1)
        self.assertEqual(f.run(model),[]);self.assertEqual(model.calls,1)

    def test_new_tables_min_acl_owner_and_nonempty_down_refusal(self):
        import psycopg
        from psycopg import sql
        f,binding,outcome=self.generated('scope-schema')
        with TestClient(self.scoped(f)) as client:
            p=self.detail(client,f,outcome.proposal_id)
            self.assertEqual(self.post(client,f,self.action(p)).status_code,200)
        rows={}
        with f.database.connect(f.scope) as conn:
            for table in ('cj_trip_scoped_basis','cj_trip_scoped_action'):
                rows[table]=conn.execute(sql.SQL('SELECT * FROM {}').format(sql.Identifier(table))).fetchone()
                for privilege in ('UPDATE','DELETE','TRUNCATE'):
                    self.assertFalse(conn.execute('SELECT has_table_privilege(current_user,%s,%s)',(table,privilege)).fetchone()[0])
                self.assertEqual(conn.execute('SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=%s::regclass',(table,)).fetchone(),(True,True))
        for table,row in rows.items():
            with f.database.connect(scope_for(ISSUER,'other-'+f.subject)) as conn:
                self.assertEqual(conn.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(table))).fetchone()[0],0)
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                with f.database.connect(scope_for(ISSUER,'other-'+f.subject)) as conn:
                    conn.execute(sql.SQL('INSERT INTO {} VALUES ({})').format(sql.Identifier(table),sql.SQL(',').join(sql.Placeholder() for _ in row)),row)
        with psycopg.connect(**json.loads(Path(CONNINFO).read_text()),autocommit=True) as admin:
            count=admin.execute('SELECT count(*) FROM cj_trip_scoped_basis').fetchone()[0]
            with self.assertRaises(psycopg.errors.RaiseException):
                with admin.transaction():admin.execute((ROOT/'backend/migrations/down/0028_trip_scoped_edit.down.sql').read_text())
            self.assertEqual(admin.execute('SELECT count(*) FROM cj_trip_scoped_basis').fetchone()[0],count)

    def test_discussion_none_is_not_a_mutating_model_intent(self):
        f=self.fixture('discussion');binding=f.send('no-edit',intent='none');model=Model()
        result=f.run(model)[0];self.assertEqual(result.status,'completed');self.assertIsNone(result.proposal_id)
        self.assertEqual(f.database.run_repository(f.scope).recover(binding).state.effects,())
        with f.database.connect(f.scope) as conn:self.assertEqual(conn.execute('SELECT count(*) FROM cj_trip_scoped_basis').fetchone()[0],0)

    def test_day_selection_respects_original_timezone_member_ids(self):
        from copy import deepcopy
        from hashlib import sha256
        from cj_trip.postgres import Repository
        from cj_trip.domain import Proposal
        from cj_agent.draft import trip_scope_for
        import time
        f=self.fixture('day-zone',legacy=True);document=json.loads(f.trip.content)
        other=deepcopy(document['items'][0]);other['id']='other-zone'
        for event in other['schedule'].values():event['timezone']=dict(state='known',value='America/New_York')
        document['items'].append(other)
        repo=Repository(lambda:f.database.connect(f.scope),trip_scope_for(f.scope),f.signer,structured=True)
        proposal=Proposal('explicit-add-zone',f.trip.trip_id,f.trip.version,'fixture-explicit.1',int(time.time())+300,packed(document))
        repo.publish(proposal);detail=repo.proposal_detail(proposal.proposal_id)
        repo.act(f.signer.issue(repo.scope,detail,action_id='accept-zone-source',kind='accept',candidate_hash=detail.candidate_hash).action)
        f.trip=repo.detail(f.trip.trip_id)
        item=document['items'][0];day=item['schedule']['start']
        selection=dict(id=f.trip.trip_id,expected_version=f.trip.version,content_sha256=sha256(f.trip.content).hexdigest(),
            day=dict(date=day['date']['value'],timezone=day['timezone']['value']),item_ids=[])
        f.send('edit',trip=selection);result=f.run(Model())[0];self.assertIsNotNone(result.proposal_id)
        with TestClient(self.scoped(f)) as client:
            p=self.detail(client,f,result.proposal_id)
            self.assertEqual(p['scope']['reference']['resolved_item_ids'],[item['id']])
            self.assertEqual(p['content']['items'][-1],other)

    def test_final_slow_admission_cannot_commit_expired_original_confirmation(self):
        import time
        from unittest.mock import patch
        from cj_trip.postgres import Repository
        f=self.fixture('confirmation-expiry')
        f.configuration.publisher.clock=lambda:time.time()-292
        binding=f.send('edit');outcome=f.run(Model())[0];self.assertIsNotNone(outcome.proposal_id)
        with TestClient(self.scoped(f)) as client:
            p=self.detail(client,f,outcome.proposal_id);raw=self.action(p)
            state={'finals':0,'delayed':False};original_final=Repository._final_action_eligibility
            checker=f.configuration.publisher.checker;original_check=type(checker).check
            def final(repository,*args):
                result=original_final(repository,*args);state['finals']+=1;return result
            def check(actual,*args):
                result=original_check(actual,*args)
                if state['finals']>=2 and not state['delayed']:
                    state['delayed']=True;time.sleep(max(0,p['expires_at']-time.time())+.15)
                return result
            with patch.object(Repository,'_final_action_eligibility',final),patch.object(type(checker),'check',check):
                response=self.post(client,f,raw)
            self.assertTrue(state['delayed']);self.assertIn(response.status_code,(409,503),response.text)
            self.assertIsNone(client.get('/v1/trip-scoped-action-receipts',params={'action_id':'original-accept'},headers=f.headers).json()['receipt'])
            self.assertEqual(self.detail(client,f,p['proposal_id'])['status'],'pending')
        with f.database.connect(f.scope) as conn:
            self.assertEqual(conn.execute('SELECT version FROM cj_trip_record WHERE trip_id=%s',(f.trip.trip_id,)).fetchone()[0],f.trip.version)

from scoped_discovery_pg import ScopedDiscoveryChecks

if __name__=='__main__':unittest.main(verbosity=2)
