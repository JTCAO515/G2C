"""HTTP-only edit-candidate discovery, genuine local sources and original worker."""
import json,sys,unittest
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend/memory/tests'),str(ROOT/'backend/trip/tests'),str(ROOT/'backend/agent/tests'),str(ROOT/'scripts')]
from edit_support import Fixture,ProbePublisher,Harness,CONNINFO
from cj_draft.scoped_publisher import local_configuration
from cj_trip.local_scoped_app import create_local_scoped_app
from cj_trip.domain import packed
from cj_api.local_app import create_local_app,load_history_configuration,ISSUER,LocalDatabase
from cj_usage.core import Meter


class DiscoveryFixture(Fixture):
    def legacy_source(self):
        # Test setup creates/accepts a real legacy via unmodified run_once, then
        # actual source-initialize HTTP; no SQL Trip seed or factory replacement.
        from source_initialization_pg import SourceInitializationChecks
        helper=SourceInitializationChecks()
        helper.host=self.host;helper.env=self.env;helper.signer=self.signer
        _,repository,original,raw,_=helper.legacy(self.subject)
        with TestClient(helper.source_app(self.subject)) as client:
            prepared=helper.prepare(client,self.subject,raw)
            response=helper.post(client,self.subject,'/v1/trip-source-initialization-saves',helper.save(prepared))
            self.case.assertEqual(response.status_code,200,response.text)
        self.trip_id=original.trip_id
        return repository.detail(self.trip_id)


class ScopedDiscoveryChecks(unittest.TestCase):
    headers=Harness.headers;setUpClass=classmethod(Harness.setUpClass.__func__);tearDownClass=classmethod(Harness.tearDownClass.__func__)
    def fixture(self,subject):
        from scoped_runtime_pg import limits
        f=DiscoveryFixture(self,subject,ProbePublisher(),legacy=True)
        credentials=lambda owner:f.host.headers[owner.removeprefix('local:'+ISSUER+':')]['Authorization'][7:]
        db,cfg=local_configuration(conninfo_path=CONNINFO,auth_dir=f.auth,run_context=f.context,memory=f.memory,credentials=credentials,
            confirmation=f.signer,limits=limits(),language='en')
        f.database,f.configuration=db,cfg
        f.app=create_local_app(conninfo_path=CONNINFO,auth_dir=f.auth,run_context=f.context,travel_context=True,edit_configuration=cfg,history_configuration=load_history_configuration(f.auth))
        return f
    def scoped_app(self,f,**kwargs):return create_local_scoped_app(database=f.database,configuration=f.configuration,**kwargs)
    def get(self,client,f,binding,**kwargs):
        return client.get('/v1/trip-scoped-discovery',params=dict(message_id=binding.message_id,run_id=binding.run_id),headers=f.headers,**kwargs)
    def generate(self,f,key='edit',model=None):
        from scoped_runtime_pg import Model
        binding=f.send(key);model=model or Model()
        f.run(model)  # Discard Outcome: candidate identity only comes from HTTP below.
        return binding,model
    def published(self,response):
        self.assertEqual(response.status_code,200,response.text)
        d=response.json();self.assertEqual(d['version'],'TRIP-scoped-discovery.1')
        self.assertEqual(d['discovery']['state'],'published');return d['discovery']
    def action(self,p):return packed(dict(version='TRIP-scoped-action.1',action_id='discovered-accept',kind='accept',proposal_id=p['proposal_id'],candidate_hash=p['candidate_hash']))
    def post(self,client,f,raw):return client.post('/v1/trip-scoped-actions',content=raw,headers={**f.headers,'Content-Type':'application/octet-stream'})

    def test_http_receipt_only_discovery_diff_original_accept_readback_and_rebuild(self):
        f=self.fixture('discover-positive');binding,model=self.generate(f,'消息 / + & %')
        with TestClient(self.scoped_app(f)) as client:
            result=self.published(self.get(client,f,binding));p=result['proposal']
            self.assertEqual(result['reference']['message_id'],binding.message_id)
            self.assertEqual(result['reference']['run_id'],binding.run_id)
            self.assertEqual(result['reference']['modification_intent'],'propose_scoped_edit')
            self.assertEqual(p['scope']['reference'],result['reference'])
            self.assertEqual(result['reference']['namespace']['id'],f.namespace['id'])
            self.assertEqual(p['diff']['before'],json.loads(f.trip.content))
            # The original detail agrees, but is not needed to discover the ID.
            old=client.get('/v1/trip-scoped-proposals',params={'proposal_id':p['proposal_id']},headers=f.headers)
            self.assertEqual(old.json()['proposal'],p)
        with TestClient(self.scoped_app(f)) as rebuilt:
            again=self.published(self.get(rebuilt,f,binding));self.assertEqual(again,result)
            raw=self.action(again['proposal']);accepted=self.post(rebuilt,f,raw)
            self.assertEqual(accepted.status_code,200,accepted.text);receipt=accepted.json()['receipt']
            self.assertEqual(receipt['trip_id'],f.trip.trip_id);self.assertEqual(receipt['committed_version'],f.trip.version+1)
            self.assertEqual(self.post(rebuilt,f,raw).json()['receipt'],receipt)
            # Source Trip advanced: no newly current candidate bytes are returned.
            self.assertEqual(self.get(rebuilt,f,binding).status_code,503)
            recovered=rebuilt.get('/v1/trip-scoped-action-receipts',params={'action_id':'discovered-accept'},headers=f.headers)
            self.assertEqual(recovered.json()['receipt'],receipt)
        from cj_trip.local_structured_read import create_local_structured_read_app
        with TestClient(create_local_structured_read_app(conninfo_path=CONNINFO,auth_dir=f.auth,run_context=f.context)) as client:
            current=client.get('/v5/trip-structured',params={'trip_id':f.trip.trip_id},headers=f.headers)
            self.assertEqual(current.json()['trip']['content'],p['content'])
        self.assertEqual(model.calls,1)

    def test_discovery_executes_no_business_dml_or_extra_meter_model_step(self):
        f=self.fixture('discover-readonly');binding,model=self.generate(f)
        before=f.host.ledger(f.subject);writes=[];connect=LocalDatabase.connect
        def observe(q):
            if type(q) is str and q.lstrip().upper().startswith(('INSERT ','UPDATE ','DELETE ','TRUNCATE ')):writes.append(q.split()[0])
        class Cursor:
            def __init__(self,base):self.base=base
            def __getattr__(self,name):return getattr(self.base,name)
            def execute(self,q,*args,**kwargs):observe(q);self.base.execute(q,*args,**kwargs);return self
        class Connection:
            def __init__(self,base):self.base=base
            def __getattr__(self,name):return getattr(self.base,name)
            def __enter__(self):self.base.__enter__();return self
            def __exit__(self,*args):return self.base.__exit__(*args)
            def cursor(self):return Cursor(self.base.cursor())
            def execute(self,q,*args,**kwargs):observe(q);return self.base.execute(q,*args,**kwargs)
        def wrapped(database,*args,**kwargs):return Connection(connect(database,*args,**kwargs))
        with patch.object(LocalDatabase,'connect',wrapped),TestClient(self.scoped_app(f)) as client:self.published(self.get(client,f,binding))
        self.assertEqual(writes,[])
        self.assertEqual(f.host.ledger(f.subject),before);self.assertEqual(model.calls,1)
        self.assertGreater(Meter.exposure(before),0)

    def test_explicit_nonrequested_validation_failure_and_unknown_are_distinct(self):
        from scoped_runtime_pg import Model
        from cj_agent.provider import ProviderUnknown
        class Unknown(Model):
            def stream(self,messages,system=None):
                self.calls+=1;raise ProviderUnknown('synthetic unknown');yield ''
        for mode in ('none','invalid','unknown'):
            with self.subTest(mode=mode):
                f=self.fixture('discover-'+mode)
                binding=f.send('edit',intent='none' if mode=='none' else 'propose_scoped_edit')
                model=Unknown() if mode=='unknown' else Model((lambda d:d.update(modification_intent='propose_scoped_edit')) if mode=='invalid' else None)
                f.run(model)
                with TestClient(self.scoped_app(f)) as client:
                    response=self.get(client,f,binding);self.assertEqual(response.status_code,200,response.text)
                    d=response.json()['discovery'];self.assertIsNone(d['proposal'])
                    self.assertEqual(d['state'],{'none':'not_requested','invalid':'no_candidate','unknown':'unknown'}[mode])
                    if mode=='invalid':self.assertEqual(d['draft_outcome'],'validation_failed')
                    self.get(client,f,binding);self.assertEqual(model.calls,1)

    def test_inflight_running_is_pending_without_dispatch_or_outcome_guess(self):
        from scoped_runtime_pg import Model
        f=self.fixture('discover-pending');binding=f.send('edit');model=Model();observed=[]
        def during():
            with TestClient(self.scoped_app(f)) as client:
                response=self.get(client,f,binding);self.assertEqual(response.status_code,200,response.text)
                observed.append(response.json()['discovery'])
        model.hook=during;f.run(model)
        self.assertEqual([d['state'] for d in observed],['pending']);self.assertIsNone(observed[0]['proposal'])
        with TestClient(self.scoped_app(f)) as client:self.published(self.get(client,f,binding))
        self.assertEqual(model.calls,1)

    def test_current_memory_change_withholds_and_original_reject_receipt_survives(self):
        f=self.fixture('discover-memory');binding,model=self.generate(f)
        with TestClient(self.scoped_app(f)) as client:
            p=self.published(self.get(client,f,binding))['proposal']
            f.manage('edit',1,text='纠正 / corrected')
            denied=self.get(client,f,binding);self.assertEqual(denied.status_code,503,denied.text)
            self.assertNotIn(p['content']['title'],denied.text)
            raw=json.loads(self.action(p));raw['kind']='reject'
            response=self.post(client,f,packed(raw));self.assertEqual(response.status_code,200,response.text)
            self.assertIsNone(response.json()['receipt']['committed_version'])
            self.assertEqual(self.post(client,f,packed(raw)).json()['receipt'],response.json()['receipt'])
        self.assertEqual(model.calls,1)

    def test_actual_source_namespace_selection_generation_and_withdrawal_fences(self):
        for mode in ('needs','namespace','selection','generation','withdraw'):
            with self.subTest(mode=mode):
                f=self.fixture('discover-source-'+mode);binding,model=self.generate(f)
                with TestClient(self.scoped_app(f)) as client:p=self.published(self.get(client,f,binding))['proposal']
                if mode=='withdraw':
                    with TestClient(f.memory_app) as current:
                        item=current.get('/v2/memory-items',params={'item_id':'mem-long'},headers=f.headers).json()['item']
                        body=packed(dict(version='MEMORY-STOP-USE@2',action_id='stop',operation='withdraw',item_id='mem-long',
                            expected_version=1,source_id=item['command']['source_id'],expected_source_version=1))
                        response=current.post('/v2/memory-withdrawal-actions',content=body,headers={**f.headers,'Content-Type':'application/octet-stream'})
                        self.assertEqual(response.status_code,200,response.text)
                elif mode=='needs':
                    with patch.dict(__import__('os').environ,f.env),f.host.api(f.subject) as current:
                        response=current.post('/v1/needs-actions',content=packed(dict(action_id='correct',needs_id='visit',expected_version=1,
                            source=dict(kind='manual',text='explicit correction'),changes=dict(party_size=dict(state='known',value=2)))),
                            headers={**f.headers,'Content-Type':'application/octet-stream'})
                        self.assertEqual(response.status_code,200,response.text)
                elif mode=='namespace':
                    with patch.dict(__import__('os').environ,f.env),f.host.api(f.subject) as current:
                        response=current.post('/v1/travel-context-actions',content=packed(dict(version='TRAVEL-context-action.1',action_id='advance',operation='advance',
                            travel_context=dict(id=f.namespace['id'],expected_version=1))),headers={**f.headers,'Content-Type':'application/octet-stream'})
                        self.assertEqual(response.status_code,200,response.text)
                elif mode=='selection':
                    from hashlib import sha256
                    with TestClient(f.app) as current:
                        response=current.post('/v4/messages',content=packed(dict(version='MESSAGE-send.4',conversation_id=binding.conversation_id,
                            message_id='next-selection',text='new explicit selection',trip_id=None,creation_intent='none',
                            expected_generation=binding.generation,expected_sequence=binding.message_sequence,modification_intent='propose_scoped_edit',
                            trip_context=dict(id=f.trip.trip_id,expected_version=f.trip.version,content_sha256=sha256(f.trip.content).hexdigest(),
                                day=None,item_ids=[json.loads(f.trip.content)['items'][-1]['id']]),
                            travel_context=dict(id=f.other_namespace['id'],expected_version=1),needs_reference=dict(id='visit',expected_version=1))),
                            headers={**f.headers,'Content-Type':'application/octet-stream'})
                        self.assertEqual(response.status_code,200,response.text)
                else:
                    # B has no public generation-reset producer. This is only a
                    # private-PG invalidation rejection probe, not a positive path.
                    import psycopg
                    with psycopg.connect(**json.loads(Path(CONNINFO).read_text())) as admin:
                        admin.execute('UPDATE cj_message_chat SET active=false WHERE scope=%s AND conversation_id=%s',(f.scope,binding.conversation_id))
                with TestClient(self.scoped_app(f)) as client:
                    denied=self.get(client,f,binding);self.assertEqual(denied.status_code,503,denied.text)
                    self.assertNotIn('proposal_id',denied.text)
                self.assertEqual(model.calls,1)

    def test_cancel_during_real_model_returns_no_candidate_or_model_redispatch(self):
        from scoped_runtime_pg import Model
        f=self.fixture('discover-cancel');binding=f.send('edit');model=Model()
        def cancel():
            with TestClient(f.app) as current:
                response=current.post('/v4/run-cancellations',json=dict(version='RUN-cancel.4',message_id='edit'),headers=f.headers)
                self.assertEqual(response.status_code,200,response.text)
        model.hook=cancel;f.run(model)
        with TestClient(self.scoped_app(f)) as client:
            response=self.get(client,f,binding)
            if response.status_code==200:
                self.assertEqual(response.json()['discovery']['state'],'unavailable')
                self.assertIsNone(response.json()['discovery']['proposal'])
            else:self.assertEqual(response.status_code,503,response.text)
        self.assertEqual(model.calls,1)

    def test_final_serialization_revocation_and_cleanup_withhold_all_private_bytes(self):
        from cj_trip import local_scoped_app
        f=self.fixture('discover-lifetime');binding,model=self.generate(f)
        invitations=(f.auth/'invited.json').read_bytes();original=local_scoped_app.json.dumps
        def revoke(value,*args,**kwargs):
            raw=original(value,*args,**kwargs)
            if type(value) is dict and value.get('version')=='TRIP-scoped-discovery.1':(f.auth/'invited.json').write_text('[]')
            return raw
        try:
            with patch.object(local_scoped_app.json,'dumps',revoke),TestClient(self.scoped_app(f)) as client:
                response=self.get(client,f,binding);self.assertEqual(response.status_code,503,response.text)
                self.assertNotIn('proposal_id',response.text)
        finally:(f.auth/'invited.json').write_bytes(invitations)
        connect=LocalDatabase.connect
        class Connection:
            def __init__(self,base):self.base=base
            def __getattr__(self,name):return getattr(self.base,name)
            def __enter__(self):self.base.__enter__();return self
            def __exit__(self,*args):return self.base.__exit__(*args)
            def close(self):self.base.close();raise OSError('synthetic strict read close failure')
        def wrapped(database,*args,**kwargs):return Connection(connect(database,*args,**kwargs))
        with patch.object(LocalDatabase,'connect',wrapped),TestClient(self.scoped_app(f)) as client:
            response=self.get(client,f,binding);self.assertEqual(response.status_code,503,response.text)
            self.assertNotIn('proposal_id',response.text)
        with TestClient(self.scoped_app(f)) as client:self.published(self.get(client,f,binding))
        self.assertEqual(model.calls,1)

    def test_parallel_discovery_and_bilingual_rebuild_return_same_original_candidate(self):
        f=self.fixture('discover-parallel');binding,model=self.generate(f)
        def read():
            with TestClient(self.scoped_app(f)) as client:return self.published(self.get(client,f,binding))
        with ThreadPoolExecutor(max_workers=2) as pool:values=[v.result(timeout=20) for v in [pool.submit(read),pool.submit(read)]]
        self.assertEqual(values[0],values[1])
        # Trusted host may change presentation language; original bytes/action remain.
        old=f.configuration.publisher.language;f.configuration.publisher.language='zh-Hans'
        try:
            with TestClient(self.scoped_app(f)) as rebuilt:self.assertEqual(self.published(self.get(rebuilt,f,binding)),values[0])
        finally:f.configuration.publisher.language=old
        self.assertEqual(model.calls,1)

    def test_owner_wrong_run_missing_auth_query_encoding_and_bounds(self):
        f=self.fixture('discover-boundary');binding,model=self.generate(f)
        with TestClient(self.scoped_app(f)) as client:
            self.assertEqual(client.get('/v1/trip-scoped-discovery',params={'message_id':binding.message_id,'run_id':binding.run_id}).status_code,401)
            wrong=client.get('/v1/trip-scoped-discovery',params={'message_id':binding.message_id,'run_id':binding.run_id},headers=f.host.headers['other-'+f.subject])
            self.assertEqual(wrong.status_code,503)
            self.assertEqual(client.get('/v1/trip-scoped-discovery',params={'message_id':binding.message_id,'run_id':'wrong'},headers=f.headers).status_code,503)
            for query in ('message_id=edit','message_id=edit&run_id=x&run_id=y','message_id=%FF&run_id=x','message_id=%ZZ&run_id=x','message_id=&run_id=x','message_id=edit&run_id=x&owner=other'):
                self.assertEqual(client.get('/v1/trip-scoped-discovery?'+query,headers=f.headers).status_code,400)
            self.assertEqual(client.get('/v1/trip-scoped-discovery?message_id='+'%61'*4200+'&run_id=x',headers=f.headers).status_code,400)
            self.assertEqual(client.get('/v1/trip-scoped-discovery',params={'message_id':'字'*700,'run_id':'x'},headers=f.headers).status_code,400)
        with TestClient(self.scoped_app(f,max_response_bytes=1)) as tiny:
            denied=self.get(tiny,f,binding);self.assertEqual(denied.status_code,503);self.assertNotIn('proposal_id',denied.text)
        self.assertEqual(model.calls,1)


if __name__=='__main__':unittest.main(verbosity=2)
