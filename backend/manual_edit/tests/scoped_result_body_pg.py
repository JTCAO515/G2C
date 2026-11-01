"""C production publisher2/body API, original signed RUN and restricted PG."""
import json,unittest,hashlib
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import psycopg
from fastapi.testclient import TestClient

from scoped_discovery_pg import DiscoveryFixture
from edit_support import ProbePublisher,Harness,CONNINFO,ROOT
from cj_draft.scoped_result_publisher import local_configuration,ScopedResultPublisher
from cj_trip.local_scoped_app import create_local_scoped_app
from cj_trip.domain import packed
from cj_api.local_app import LocalDatabase,create_local_app,load_history_configuration,ISSUER
from cj_message.travel import Selection
from cj_run.core import Binding
from cj_usage.core import Meter


def Model(*args,**kwargs):
    from scoped_runtime_pg import Model as OriginalModel
    return OriginalModel(*args,**kwargs)


class ScopedResultChecks(unittest.TestCase):
    headers=Harness.headers;setUpClass=classmethod(Harness.setUpClass.__func__);tearDownClass=classmethod(Harness.tearDownClass.__func__)
    def fixture(self,subject):
        from scoped_runtime_pg import limits
        from cj_api.edit_result_profile import activate
        f=DiscoveryFixture(self,'c-result-'+subject,ProbePublisher(),legacy=True)
        credentials=lambda owner:f.host.headers[owner.removeprefix('local:'+ISSUER+':')]['Authorization'][7:]
        f.database,f.configuration=local_configuration(conninfo_path=CONNINFO,auth_dir=f.auth,run_context=f.context,memory=f.memory,
            credentials=credentials,confirmation=f.signer,limits=limits(),language='en')
        self.assertEqual(activate(CONNINFO,f.subject,f.context,f.configuration,Selection(f.namespace['id'],1)),'activated')
        f.app=create_local_app(conninfo_path=CONNINFO,auth_dir=f.auth,run_context=f.context,travel_context=True,needs_profile='manual-v1',
            edit_configuration=f.configuration,history_configuration=load_history_configuration(f.auth))
        return f
    def body_app(self,f,**kw):return create_local_scoped_app(database=f.database,configuration=f.configuration,**kw)
    def send(self,f,key='original',*,clarify=False,all_items=False,version=None):
        items=[v['id'] for v in json.loads(f.trip.content)['items']]
        with TestClient(f.app) as client:
            head=client.put('/v1/conversations',params={'conversation_id':key},headers=f.headers).json()
            raw=packed(dict(version='MESSAGE-send.4',conversation_id=key,message_id=key,text='Tomorrow / 明天' if clarify else 'Make this selected item lighter / 轻松一点',trip_id=None,
                creation_intent='none',expected_generation=head['generation'],expected_sequence=0,modification_intent='propose_scoped_edit',
                trip_context=dict(id=f.trip.trip_id,expected_version=version or f.trip.version,content_sha256=hashlib.sha256(f.trip.content).hexdigest(),day=None,item_ids=items if all_items else items[-1:]),
                travel_context=dict(id=f.namespace['id'],expected_version=1),needs_reference=dict(id='visit',expected_version=1)))
            response=client.post('/v4/messages',content=raw,headers={**f.headers,'Content-Type':'application/octet-stream'})
            self.assertEqual(response.status_code,200,response.text);r=response.json()['receipt']
        return Binding(f.scope,key,r['generation'],key,r['run_id'],r['sequence']),raw,r
    def expand_model(self,f):
        first=json.loads(f.trip.content)['items'][0]['id']
        return Model(lambda value:value['changes'][0].update(item_id=first))
    def pointer(self,f,binding):
        with TestClient(f.app) as client:
            response=client.get('/v6/run-draft-status',params={'message_id':binding.message_id},headers=f.headers)
            self.assertEqual(response.status_code,200,response.text)
            return response.json()['scoped_result']
    def get(self,f,key,*,headers=None,**kw):
        with TestClient(self.body_app(f,**kw)) as client:
            return client.get('/v1/trip-scoped-results',params={'result_id':key},headers=headers or f.headers)
    def rows(self,f):
        with f.database.connect(f.scope) as c:return c.execute('SELECT result_id,kind,original_input,model_input,explanation FROM cj_trip_scoped_result').fetchall()
    def counts(self,f):
        with f.database.connect(f.scope) as c:
            return tuple(c.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in ('cj_trip_proposal','cj_trip_receipt','cj_trip_scoped_result'))

    def test_both_original_outcomes_durable_zero_proposal_or_trip_changes_and_no_accept(self):
        for clarify in (True,False):
            with self.subTest(clarify=clarify):
                f=self.fixture('both-'+str(clarify));binding,raw,receipt=self.send(f,clarify=clarify)
                before=self.counts(f);model=self.expand_model(f)
                f.run(model)  # Client identity is recovered solely through B HTTP.
                pointer=self.pointer(f,binding);self.assertIsNotNone(pointer)
                kind='clarification_required' if clarify else 'expansion_required'
                self.assertEqual(pointer['kind'],kind);self.assertEqual(model.calls,0 if clarify else 1)
                self.assertEqual(self.counts(f),(before[0],before[1],before[2]+1))
                response=self.get(f,pointer['result_id']);self.assertEqual(response.status_code,200,response.text)
                display=response.json()['display'];body=display['result']
                self.assertEqual((display['state'],body['kind']),('current',kind))
                self.assertEqual(body['reference']['input_sha256'],hashlib.sha256(raw).hexdigest())
                self.assertEqual(body['explanation']['status'],kind.upper())
                self.assertTrue(body['explanation']['reason']['zh']);self.assertTrue(body['explanation']['reason']['en'])
                self.assertNotIn('model_input',body);self.assertNotIn('candidate_hash',body);self.assertNotIn('proposal_id',body)
                self.assertEqual(bytes(self.rows(f)[0][2]),raw)
                self.assertEqual(self.rows(f)[0][3] is None,clarify)
                ledger=f.host.ledger(f.subject)
                f.configuration.publisher.language='zh-Hans'
                self.assertEqual(self.get(f,pointer['result_id']).json()['display'],display)
                self.assertEqual(f.run(model),[]);self.assertEqual(f.host.ledger(f.subject),ledger)
                self.assertEqual(model.calls,0 if clarify else 1)
                with TestClient(f.app) as client:
                    replay=client.post('/v4/messages',content=raw,headers={**f.headers,'Content-Type':'application/octet-stream'})
                    self.assertEqual(replay.json()['receipt'],receipt)
                    self.assertEqual(client.get('/v5/run-draft-status',params={'message_id':binding.message_id},headers=f.headers).status_code,503)
                with TestClient(self.body_app(f)) as client:
                    rejected=client.post('/v1/trip-scoped-actions',content=packed(dict(version='TRIP-scoped-action.1',action_id='cannot-accept-result',kind='accept',proposal_id=pointer['result_id'],candidate_hash='0'*64)),headers={**f.headers,'Content-Type':'application/octet-stream'})
                    self.assertEqual(rejected.status_code,503,rejected.text)
                    self.assertEqual(client.post('/v1/trip-scoped-results',json={}).status_code,405)
                with f.database.connect(f.scope) as c:
                    self.assertEqual(c.execute('SELECT version,content FROM cj_trip_record WHERE trip_id=%s',(f.trip.trip_id,)).fetchone(),(f.trip.version,f.trip.content))

    def test_new_explicit_send_expands_selection_original_signer_act_accepts_and_old_result_is_stale(self):
        f=self.fixture('expanded');binding,_,_=self.send(f);model=self.expand_model(f);f.run(model)
        key=self.pointer(f,binding)['result_id'];display=self.get(f,key).json()['display']['result']
        expected=[v['id'] for v in json.loads(f.trip.content)['items']]
        self.assertEqual(display['explanation']['required_selection']['item_ids'],[expected[0],expected[-1]])
        self.assertTrue(display['explanation']['outside_item_ids'])
        reject_binding,_,_=self.send(f,'user-expanded-reject',all_items=True);f.run(model)
        with TestClient(self.body_app(f)) as client:
            rejected_candidate=client.get('/v1/trip-scoped-discovery',params=dict(message_id=reject_binding.message_id,run_id=reject_binding.run_id),headers=f.headers).json()['discovery']['proposal']
            raw=packed(dict(version='TRIP-scoped-action.1',action_id='reject-expanded-original',kind='reject',proposal_id=rejected_candidate['proposal_id'],candidate_hash=rejected_candidate['candidate_hash']))
            rejected=client.post('/v1/trip-scoped-actions',content=raw,headers={**f.headers,'Content-Type':'application/octet-stream'})
            self.assertEqual(rejected.status_code,200,rejected.text);self.assertIsNone(rejected.json()['receipt']['committed_version'])
        with f.database.connect(f.scope) as c:self.assertEqual(c.execute('SELECT version FROM cj_trip_record WHERE trip_id=%s',(f.trip.trip_id,)).fetchone()[0],f.trip.version)
        fresh,_,_=self.send(f,'new-user-selection',all_items=True);f.run(model)
        with TestClient(self.body_app(f)) as client:
            response=client.get('/v1/trip-scoped-discovery',params=dict(message_id=fresh.message_id,run_id=fresh.run_id),headers=f.headers)
            self.assertEqual(response.status_code,200,response.text);p=response.json()['discovery']['proposal'];self.assertIsNotNone(p)
            action=packed(dict(version='TRIP-scoped-action.1',action_id='accept-expanded-original',kind='accept',proposal_id=p['proposal_id'],candidate_hash=p['candidate_hash']))
            result=client.post('/v1/trip-scoped-actions',content=action,headers={**f.headers,'Content-Type':'application/octet-stream'})
            self.assertEqual(result.status_code,200,result.text);receipt=result.json()['receipt'];self.assertEqual(receipt['committed_version'],f.trip.version+1)
            self.assertEqual(client.post('/v1/trip-scoped-actions',content=action,headers={**f.headers,'Content-Type':'application/octet-stream'}).json()['receipt'],receipt)
        stale=self.get(f,key);self.assertEqual(stale.status_code,200,stale.text)
        self.assertEqual(stale.json()['display'],dict(result_id=key,state='stale',expected_version=f.trip.version,current_version=f.trip.version+1,result=None))
        from cj_trip.local_structured_read import create_local_structured_read_app
        with TestClient(create_local_structured_read_app(conninfo_path=CONNINFO,auth_dir=f.auth,run_context=f.context)) as client:
            trip=client.get('/v5/trip-structured',params={'trip_id':f.trip.trip_id},headers=f.headers).json()['trip']
            self.assertEqual(trip['version'],receipt['committed_version']);self.assertEqual(trip['content'],p['content'])

    def test_model_fixed_invalid_and_invariant_failures_remain_validation_failed(self):
        for i,change in enumerate((lambda d:d['changes'][0].update(field='fixed',value=dict(state='known',value=False)),lambda d:d.update(expected_version=999),lambda d:d.update(modification_intent='propose_scoped_edit'))):
            f=self.fixture('invalid-'+str(i));binding,_,_=self.send(f);model=Model(change);f.run(model)
            self.assertEqual(self.rows(f),[]);self.assertIsNone(self.pointer(f,binding))
            self.assertEqual(f.database.run_repository(f.scope).recover(binding).state.draft_outcome,'validation_failed')

    def test_memory_correction_disable_withdrawal_and_current_needs_withhold_original_content(self):
        for mode in ('edit','pause','withdraw','needs'):
            f=self.fixture('current-'+mode);binding,_,_=self.send(f);f.run(self.expand_model(f));key=self.pointer(f,binding)['result_id']
            self.assertEqual(self.get(f,key).status_code,200)
            if mode=='needs':
                with TestClient(f.app) as client:
                    response=client.post('/v1/needs-actions',content=packed(dict(action_id='needs-correction',needs_id='visit',expected_version=1,source=dict(kind='manual',text='Explicit correction'),changes=dict(party_size=dict(state='known',value=2)))),headers={**f.headers,'Content-Type':'application/octet-stream'})
                    self.assertEqual(response.status_code,200,response.text)
            elif mode=='withdraw':
                with TestClient(f.memory_app) as client:
                    item=client.get('/v2/memory-items',params={'item_id':'mem-long'},headers=f.headers).json()['item']
                    body=packed(dict(version='MEMORY-STOP-USE@2',action_id='stop-original',operation='withdraw',item_id='mem-long',expected_version=1,source_id=item['command']['source_id'],expected_source_version=1))
                    response=client.post('/v2/memory-withdrawal-actions',content=body,headers={**f.headers,'Content-Type':'application/octet-stream'})
                    self.assertEqual(response.status_code,200,response.text)
            else:f.manage(mode,1,text='Current corrected preference' if mode=='edit' else None)
            self.assertEqual(self.get(f,key).status_code,503)
            self.assertEqual(len(self.rows(f)),1)

    def test_result_acl_cross_owner_bounded_read_and_retained_down_refusal(self):
        from psycopg import sql
        f=self.fixture('acl');binding,_,_=self.send(f,clarify=True);f.run(Model());key=self.pointer(f,binding)['result_id']
        self.assertEqual(self.get(f,key,headers=f.host.headers['other-'+f.subject]).status_code,503)
        self.assertEqual(self.get(f,key,max_response_bytes=8).status_code,503)
        with TestClient(self.body_app(f)) as client:
            self.assertEqual(client.get('/v1/trip-scoped-results',params={'result_id':key}).status_code,401)
            self.assertEqual(client.get('/v1/trip-scoped-results?result_id=x&result_id=y',headers=f.headers).status_code,400)
        with f.database.connect(f.scope) as c:
            original=c.execute('SELECT * FROM cj_trip_scoped_result').fetchone()
            columns=[v.name for v in c.execute('SELECT * FROM cj_trip_scoped_result LIMIT 0').description]
        insert=sql.SQL('INSERT INTO cj_trip_scoped_result ({}) VALUES ({})').format(sql.SQL(',').join(map(sql.Identifier,columns)),sql.SQL(',').join(sql.Placeholder() for _ in columns))
        with self.assertRaises(psycopg.errors.InsufficientPrivilege),f.database.connect('local:'+ISSUER+':other-'+f.subject) as c:c.execute(insert,original)
        with f.database.connect(f.scope) as c:
            self.assertEqual(c.execute("SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid='cj_trip_scoped_result'::regclass").fetchone(),(True,True))
        other=f.database.connect('local:'+ISSUER+':other-'+f.subject)
        with other as c:self.assertEqual(c.execute('SELECT result_id FROM cj_trip_scoped_result').fetchall(),[])
        for verb in ('UPDATE cj_trip_scoped_result SET kind=kind','DELETE FROM cj_trip_scoped_result','TRUNCATE cj_trip_scoped_result'):
            with self.assertRaises(psycopg.errors.InsufficientPrivilege),f.database.connect(f.scope) as c:c.execute(verb)
        with self.assertRaises(psycopg.Error),psycopg.connect(**json.loads(Path(CONNINFO).read_text())) as admin:
            admin.execute((ROOT/'backend/migrations/down/0030_trip_scoped_result.down.sql').read_text())

    def test_cancel_deadline_unknown_and_changed_memory_before_write_leave_no_result(self):
        from cj_run.core import Service,Event as RunEvent
        from cj_usage.metered_exit import MeteredExitCore
        for mode in ('cancel','deadline','unknown','memory'):
            f=self.fixture('before-'+mode);binding,_,_=self.send(f,clarify=True);original=ScopedResultPublisher._prepare;expired=[False]
            def prepare(p,*args):
                prepared=original(p,*args)
                service=Service(f.database.run_repository(f.scope),lambda _:True)
                if mode=='cancel':service.cancel(binding)
                elif mode=='unknown':
                    state=service.snapshot(binding);service.apply(RunEvent(binding,state.sequence+1,'controlled-unknown','unknown'))
                elif mode=='memory':f.manage('edit',1,text='New actual preference')
                else:expired[0]=True
                return prepared
            now=MeteredExitCore._now
            def clock(core,previous):
                value=now(core,previous);return value+core.config.max_seconds+1 if expired[0] else value
            model=Model()
            with patch.object(ScopedResultPublisher,'_prepare',prepare),patch.object(MeteredExitCore,'_now',clock):f.run(model)
            self.assertEqual(model.calls,0);self.assertEqual(self.rows(f),[])
            self.assertEqual(f.database.run_repository(f.scope).recover(binding).state.effects,())

    def test_common_transaction_rollback_physical_ack_unknown_and_original_rebuild(self):
        for mode in ('rollback','ack'):
            f=self.fixture('commit-'+mode);binding,raw,receipt=self.send(f);model=self.expand_model(f);connect=LocalDatabase.connect
            class Cursor:
                def __init__(self,base,owner):self.base,self.owner=base,owner
                def __getattr__(self,name):return getattr(self.base,name)
                def execute(self,q,*a,**kw):
                    value=self.base.execute(q,*a,**kw)
                    if type(q) is str and q.startswith('INSERT INTO cj_trip_scoped_result'):
                        self.owner.wrote=True
                        if mode=='rollback':raise OSError('controlled rollback after physical C insert')
                    return self
            class Connection:
                def __init__(self,base):self.base,self.wrote=base,False
                def __getattr__(self,name):return getattr(self.base,name)
                def __enter__(self):return self.base.__enter__()
                def __exit__(self,*a):return self.base.__exit__(*a)
                def cursor(self,*a,**kw):return Cursor(self.base.cursor(*a,**kw),self)
                def commit(self):
                    self.base.commit()
                    if self.wrote and mode=='ack':raise OSError('controlled physical common commit ACK loss')
            def wrapped(db,*a,**kw):return Connection(connect(db,*a,**kw))
            with patch.object(LocalDatabase,'connect',wrapped):
                if mode=='rollback':
                    with self.assertRaises(OSError):f.run(model)
                else:f.run(model)
            self.assertEqual(model.calls,1)
            if mode=='rollback':self.assertEqual(self.rows(f),[])
            else:
                key=self.pointer(f,binding)['result_id'];self.assertEqual(self.get(f,key).status_code,200)
                self.assertEqual(len(self.rows(f)),1)
                f.run(model);self.assertEqual(model.calls,1)
                with TestClient(f.app) as client:
                    self.assertEqual(client.post('/v4/messages',content=raw,headers={**f.headers,'Content-Type':'application/octet-stream'}).json()['receipt'],receipt)

    def test_parallel_body_reads_do_not_write_or_call_model_and_hold_memory_through_encoding(self):
        f=self.fixture('parallel');binding,_,_=self.send(f);model=self.expand_model(f);f.run(model);key=self.pointer(f,binding)['result_id']
        ledger=f.host.ledger(f.subject)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=[v.result(timeout=25) for v in [pool.submit(self.get,f,key),pool.submit(self.get,f,key)]]
        self.assertEqual([v.status_code for v in results],[200,200],[v.text for v in results])
        self.assertEqual(results[0].json()['display'],results[1].json()['display'])
        self.assertEqual(f.host.ledger(f.subject),ledger);self.assertEqual(model.calls,1)
        entered,release,started=Event(),Event(),Event();original=ScopedResultPublisher.explanation
        def held(p,*a):
            entered.set();self.assertTrue(release.wait(10));return original(p,*a)
        def change():started.set();return f.manage('edit',1,text='Concurrent actual correction')
        with patch.object(ScopedResultPublisher,'explanation',held),ThreadPoolExecutor(max_workers=2) as pool:
            reading=pool.submit(self.get,f,key);self.assertTrue(entered.wait(10))
            writing=pool.submit(change);self.assertTrue(started.wait(2));self.assertFalse(writing.done())
            release.set();self.assertEqual(reading.result(timeout=15).status_code,200);writing.result(timeout=15)
        self.assertEqual(self.get(f,key).status_code,503)

    def test_body_read_has_zero_business_dml_and_result_source_namespace_fence(self):
        f=self.fixture('readonly-source');binding,_,_=self.send(f);model=self.expand_model(f);f.run(model)
        key=self.pointer(f,binding)['result_id'];writes=[];connect=LocalDatabase.connect
        class Cursor:
            def __init__(self,base):self.base=base
            def __getattr__(self,name):return getattr(self.base,name)
            def execute(self,q,*a,**kw):
                if type(q) is str and q.lstrip().upper().startswith(('INSERT ','UPDATE ','DELETE ','TRUNCATE ')):writes.append(q.split()[0])
                self.base.execute(q,*a,**kw);return self
        class Connection:
            def __init__(self,base):self.base=base
            def __getattr__(self,name):return getattr(self.base,name)
            def __enter__(self):return self.base.__enter__()
            def __exit__(self,*a):return self.base.__exit__(*a)
            def cursor(self,*a,**kw):return Cursor(self.base.cursor(*a,**kw))
        def wrapped(db,*a,**kw):return Connection(connect(db,*a,**kw))
        ledger=f.host.ledger(f.subject)
        with patch.object(LocalDatabase,'connect',wrapped):
            response=self.get(f,key);self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(writes,[]);self.assertEqual(f.host.ledger(f.subject),ledger);self.assertEqual(model.calls,1)
        with TestClient(f.app) as client:
            advanced=client.post('/v1/travel-context-actions',content=packed(dict(version='TRAVEL-context-action.1',action_id='advance',operation='advance',travel_context=dict(id=f.namespace['id'],expected_version=1))),headers={**f.headers,'Content-Type':'application/octet-stream'})
            self.assertEqual(advanced.status_code,200,advanced.text)
        self.assertEqual(self.get(f,key).status_code,503)

    def test_expansion_source_change_during_model_and_old_trip_request_do_not_publish(self):
        for mode in ('memory','cancel'):
            f=self.fixture('model-source-'+mode);binding,_,_=self.send(f);model=self.expand_model(f)
            def change():
                if mode=='memory':f.manage('edit',1,text='New actual preference during model')
                else:
                    with TestClient(f.app) as client:
                        response=client.post('/v4/run-cancellations',json=dict(version='RUN-cancel.4',message_id=binding.message_id),headers=f.headers)
                        self.assertEqual(response.status_code,200,response.text)
            model.hook=change;f.run(model)
            self.assertEqual(model.calls,1);self.assertEqual(self.rows(f),[])
            self.assertEqual(f.database.run_repository(f.scope).recover(binding).state.effects,())
        f=self.fixture('old-source')
        with TestClient(f.app) as client:
            head=client.put('/v1/conversations',params={'conversation_id':'stale'},headers=f.headers).json()
            stale=packed(dict(version='MESSAGE-send.4',conversation_id='stale',message_id='stale',text='explicit selected edit',trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=0,
                modification_intent='propose_scoped_edit',trip_context=dict(id=f.trip.trip_id,expected_version=f.trip.version-1,content_sha256=hashlib.sha256(f.trip.content).hexdigest(),day=None,item_ids=[json.loads(f.trip.content)['items'][-1]['id']]),
                travel_context=dict(id=f.namespace['id'],expected_version=1),needs_reference=dict(id='visit',expected_version=1)))
            denied=client.post('/v4/messages',content=stale,headers={**f.headers,'Content-Type':'application/octet-stream'})
            self.assertEqual(denied.status_code,409,denied.text)
        self.assertEqual(self.rows(f),[])

    def test_encoding_revocation_and_strict_cleanup_withhold_result_content(self):
        from cj_trip import local_scoped_app
        f=self.fixture('lifetime');binding,_,_=self.send(f);model=self.expand_model(f);f.run(model)
        key=self.pointer(f,binding)['result_id'];invitations=(f.auth/'invited.json').read_bytes();original=local_scoped_app.json.dumps
        def revoke(value,*a,**kw):
            raw=original(value,*a,**kw)
            if type(value) is dict and value.get('version')=='TRIP-scoped-display.1':(f.auth/'invited.json').write_text('[]')
            return raw
        try:
            with patch.object(local_scoped_app.json,'dumps',revoke):
                response=self.get(f,key);self.assertEqual(response.status_code,503,response.text);self.assertNotIn('changes',response.text)
        finally:(f.auth/'invited.json').write_bytes(invitations)
        connect=LocalDatabase.connect
        class Connection:
            def __init__(self,base):self.base=base
            def __getattr__(self,name):return getattr(self.base,name)
            def __enter__(self):self.base.__enter__();return self
            def __exit__(self,*a):return self.base.__exit__(*a)
            def close(self):self.base.close();raise OSError('controlled strict result read cleanup failure')
        def wrapped(db,*a,**kw):return Connection(connect(db,*a,**kw))
        with patch.object(LocalDatabase,'connect',wrapped):
            response=self.get(f,key);self.assertEqual(response.status_code,503,response.text);self.assertNotIn('changes',response.text)
        self.assertEqual(self.get(f,key).status_code,200);self.assertEqual(model.calls,1)
