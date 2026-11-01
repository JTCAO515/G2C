"""Actual NEEDS producer, protected HTTP discovery and original planning action."""
import json,sys,unittest
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend/draft/tests'),str(ROOT/'backend/agent/tests'),str(ROOT/'backend/cj_api/tests'),str(ROOT/'scripts')]
from e2e_local import Harness,CONNINFO
from registered_host_support import RegisteredHost
import needs_runtime_pg as fixture
import dev_auth
from cj_message.travel import ABI
from cj_api.local_app import LocalDatabase,scope_for,ISSUER
from cj_trip.confirmation import ConfirmationSigner
from cj_trip.local_needs_app import create_local_needs_app
from cj_trip.domain import packed


class NeedsDiscoveryChecks(unittest.TestCase):
    headers=Harness.headers;setup_source=fixture.NeedsPlanChecks.setup_source;worker=fixture.NeedsPlanChecks.worker
    @classmethod
    def setUpClass(cls):
        Harness.setUpClass.__func__(cls)
        cls.host=RegisteredHost(cls.auth/'needs-discovery',Path(CONNINFO),{s:(30,3,30000) for s in ('nd-discovery','nd-context','nd-stale','nd-bounds','nd-readonly','nd-unknown','nd-invalid','nd-late')})
        cls.env=dict(CJ_LOCAL_NEEDS_PROFILE='manual-v1',CJ_LOCAL_TRAVEL_CONTEXT='message-travel.1')
        cls.signer=ConfirmationSigner(b'synthetic-needs-discovery-signer-1234567')
        for subject in cls.host.subjects:dev_auth.activate_travel(Path(CONNINFO),subject,cls.host.profiles[subject][1],ABI)
    tearDownClass=classmethod(Harness.tearDownClass.__func__)
    def needs_app(self,subject,**kwargs):return create_local_needs_app(conninfo_path=CONNINFO,auth_dir=self.host.auth,
        run_context=self.host.profiles[subject][1],confirmation_signer=self.signer,**kwargs)
    def discover(self,client,subject,receipt):return client.get('/v1/trip-needs-discovery',params=dict(message_id=receipt['message_id'],run_id=receipt['run_id']),headers=self.host.headers[subject])
    def published(self,response):
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['version'],'TRIP-needs-discovery.1')
        d=response.json()['discovery'];self.assertEqual(d['state'],'published');return d
    def generate(self,subject,model=None):
        receipt=self.setup_source(subject);model=model or fixture.PlanModel()
        worker,db=self.worker(subject,model)
        worker.process()  # Outcome is not used to discover the candidate.
        return receipt,model,db
    def post(self,client,subject,path,raw):return client.post(path,content=raw,headers={**self.host.headers[subject],'Content-Type':'application/octet-stream'})
    def action(self,p,aid='original-accept',kind='accept'):return packed(dict(version='TRIP-needs-action.1',action_id=aid,kind=kind,proposal_id=p['proposal_id'],candidate_hash=p['candidate_hash']))

    def test_original_http_receipt_discovers_source1_and_original_accept_reject_recovery(self):
        subject='nd-discovery';receipt,model,db=self.generate(subject)
        with TestClient(self.needs_app(subject)) as client:
            d=self.published(self.discover(client,subject,receipt));p=d['proposal']
            self.assertEqual(d['reference']['message_id'],receipt['message_id']);self.assertEqual(d['reference']['run_id'],receipt['run_id'])
            self.assertEqual(d['source_profile'],'TRIP-source-input.1');self.assertIsNone(d['planning_context'])
            self.assertEqual(p['content']['content_version'],'structured.2')
            self.assertEqual(d['needs_reference'],dict(id='visit',expected_version=1))
            old=client.get('/v2/trip-needs-proposals',params={'proposal_id':p['proposal_id']},headers=self.host.headers[subject])
            self.assertEqual(old.json()['proposal'],p)
        with TestClient(self.needs_app(subject)) as rebuilt:
            self.assertEqual(self.published(self.discover(rebuilt,subject,receipt)),d)
            raw=self.action(p);accepted=self.post(rebuilt,subject,'/v1/trip-needs-actions',raw)
            self.assertEqual(accepted.status_code,200,accepted.text);r=accepted.json()['receipt']
            self.assertEqual(self.post(rebuilt,subject,'/v1/trip-needs-actions',raw).json()['receipt'],r)
            got=rebuilt.get('/v1/trip-needs-action-receipts',params={'action_id':'original-accept'},headers=self.host.headers[subject])
            self.assertEqual(got.json()['receipt'],r)
            current=rebuilt.get('/v4/trip-structured',params={'trip_id':r['trip_id']},headers=self.host.headers[subject])
            self.assertEqual(current.json()['trip']['content'],p['content'])
            self.assertEqual(self.discover(rebuilt,subject,receipt).status_code,409)
        self.assertEqual(model.calls,2)

    def test_source2_original_adopted_context_and_local_fixed_are_checked(self):
        subject='nd-context';receipt,model,db=self.generate(subject)
        with TestClient(self.needs_app(subject)) as client:
            root=self.published(self.discover(client,subject,receipt))['proposal']
            response=self.post(client,subject,'/v1/trip-needs-actions',self.action(root));self.assertEqual(response.status_code,200,response.text)
            trip=client.get('/v4/trip-structured',params={'trip_id':root['trip_id']},headers=self.host.headers[subject]).json()['trip']
            def edit(key,fixed):
                current=client.get('/v4/trip-structured',params={'trip_id':trip['trip_id']},headers=self.host.headers[subject]).json()['trip']
                raw=packed(dict(version='TRIP-needs-edit.1',needs_reference=dict(id='visit',expected_version=1),edit=dict(version='TRIP-manual-edit.2',
                    request_id=key,trip_id=current['trip_id'],expected_version=current['version'],original_hash=sha256(packed(current['content'])).hexdigest(),
                    title=None,order=None,changes=[dict(item_id='b',field='fixed',value=dict(state='known',value=fixed))])))
                prepared=self.post(client,subject,'/v1/trip-needs-edits',raw);self.assertEqual(prepared.status_code,200,prepared.text)
                p=prepared.json()['preparation'];saved=self.post(client,subject,'/v1/trip-needs-saves',packed(dict(version='TRIP-needs-save.1',action_id=key,
                    proposal_id=p['proposal_id'],candidate_hash=p['candidate_hash'])))
                self.assertEqual(saved.status_code,200,saved.text)
            edit('local-lock',True)
            before=client.get('/v4/trip-structured',params={'trip_id':trip['trip_id']},headers=self.host.headers[subject]).json()['trip']
            with patch.dict(__import__('os').environ,self.env),self.host.api(subject) as messages:
                head=messages.put('/v1/conversations',params={'conversation_id':'replan'},headers=self.host.headers[subject]).json()
                response=self.post(messages,subject,'/v2/messages',packed(dict(version='MESSAGE-send.2',conversation_id='replan',message_id='new-plan',text='continue adopted trip',trip_id=None,
                    creation_intent='consider_trip',expected_generation=head['generation'],expected_sequence=0,travel_context=None,needs_reference=dict(id='visit',expected_version=1))))
                self.assertEqual(response.status_code,200,response.text);next_receipt=response.json()['receipt']
            from cj_draft.needs_context import publisher
            from cj_draft.needs_publisher import SYSTEM
            from cj_api.local_worker_context import checker_for
            from cj_agent.provider import FakeProvider
            seen=[]
            class ContextModel(FakeProvider):
                def stream(self,messages,system=None):
                    if system!=SYSTEM:yield from super().stream(messages,system);return
                    self.calls+=1;source=json.loads(messages[-1]['content']);seen.append(source)
                    doc=source['current_trip']['content'];yield packed(dict(version='TRIP-model-plan.1',title=doc['title'],items=doc['items'],proposed_subjects={})).decode()
            planning,_=self.worker(subject,ContextModel())
            planning.drafts=publisher(db,checker_for(self.host.auth),planning.message_context,lambda:self.host.headers[subject]['Authorization'][7:],scope_for(ISSUER,subject))
            planning.process()  # Actual C factory composition; B official source2 host remains a separate delivery.
            result=self.published(self.discover(client,subject,next_receipt))
            self.assertEqual(result['source_profile'],'TRIP-source-input.2')
            self.assertEqual(result['planning_context'],dict(trip_id=before['trip_id'],version=before['version'],content_sha256=sha256(packed(before['content'])).hexdigest()))
            self.assertEqual(seen[0]['current_trip']['content']['items'][1]['fixed'],dict(state='known',value=True))
            edit('local-unlock',False)
            self.assertEqual(self.discover(client,subject,next_receipt).status_code,409)
            denied=self.post(client,subject,'/v1/trip-needs-actions',self.action(result['proposal'],'stale-accept'))
            self.assertEqual(denied.status_code,409,denied.text)

    def test_current_needs_correction_and_foreign_wrong_run_withhold(self):
        subject='nd-stale';receipt,model,db=self.generate(subject)
        with TestClient(self.needs_app(subject)) as client:
            self.published(self.discover(client,subject,receipt))
            foreign=client.get('/v1/trip-needs-discovery',params=dict(message_id=receipt['message_id'],run_id=receipt['run_id']),headers=self.host.headers['nd-bounds'])
            self.assertEqual(foreign.status_code,503)
            self.assertEqual(client.get('/v1/trip-needs-discovery',params=dict(message_id=receipt['message_id'],run_id='wrong'),headers=self.host.headers[subject]).status_code,503)
        with patch.dict(__import__('os').environ,self.env),self.host.api(subject) as current:
            response=self.post(current,subject,'/v1/needs-actions',packed(dict(action_id='correct',needs_id='visit',expected_version=1,
                source=dict(kind='manual',text='explicit correction'),changes=dict(party_size=dict(state='known',value=2)))))
            self.assertEqual(response.status_code,200,response.text)
        with TestClient(self.needs_app(subject)) as client:self.assertEqual(self.discover(client,subject,receipt).status_code,503)
        self.assertEqual(model.calls,2)

    def test_unknown_validation_and_query_lifetime_bounds(self):
        from cj_agent.provider import ProviderUnknown
        class Unknown(fixture.PlanModel):
            def stream(self,messages,system=None):self.calls+=1;raise ProviderUnknown('synthetic unknown');yield ''
        for subject,model,expected in [('nd-unknown',Unknown(),'unknown'),('nd-invalid',fixture.PlanModel(lambda d:d['items'][0].update(text='changed locked')),'no_candidate')]:
            with self.subTest(subject=subject):
                receipt,model,db=self.generate(subject,model)
                with TestClient(self.needs_app(subject)) as client:
                    response=self.discover(client,subject,receipt);self.assertEqual(response.status_code,200,response.text)
                    self.assertEqual(response.json()['discovery']['state'],expected);self.assertIsNone(response.json()['discovery']['proposal'])
        subject='nd-bounds';receipt,model,db=self.generate(subject)
        with TestClient(self.needs_app(subject)) as client:
            for q in ('message_id=x','message_id=x&run_id=a&run_id=b','message_id=%FF&run_id=x','message_id=%ZZ&run_id=x','message_id=x&run_id=x&owner=z'):
                self.assertEqual(client.get('/v1/trip-needs-discovery?'+q,headers=self.host.headers[subject]).status_code,400)
            self.assertEqual(client.get('/v1/trip-needs-discovery',params=dict(message_id=receipt['message_id'],run_id=receipt['run_id'])).status_code,401)
        with TestClient(self.needs_app(subject,max_response_bytes=1)) as tiny:
            response=self.discover(tiny,subject,receipt);self.assertEqual(response.status_code,503,response.text)
            self.assertNotIn('proposal_id',response.text)

    def test_readonly_concurrent_discovery_has_no_meter_model_or_dml(self):
        subject='nd-readonly';receipt,model,db=self.generate(subject)
        before=self.host.ledger(subject);writes=[];original=LocalDatabase.connect
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
        def wrapped(database,*args,**kwargs):return Connection(original(database,*args,**kwargs))
        def get():
            with TestClient(self.needs_app(subject)) as client:return self.published(self.discover(client,subject,receipt))
        with patch.object(LocalDatabase,'connect',wrapped),ThreadPoolExecutor(max_workers=2) as pool:
            values=[v.result(timeout=20) for v in [pool.submit(get),pool.submit(get)]]
        self.assertEqual(values[0],values[1]);self.assertEqual(writes,[])
        self.assertEqual(self.host.ledger(subject),before);self.assertEqual(model.calls,2)

    def test_final_auth_and_strict_run_cleanup_withhold_private_snapshot(self):
        from cj_trip import local_needs_app
        subject='nd-late';receipt,model,db=self.generate(subject)
        invitations=(self.host.auth/'invited.json').read_bytes();original=local_needs_app.json.dumps
        def revoke(value,*args,**kwargs):
            raw=original(value,*args,**kwargs)
            if type(value) is dict and value.get('version')=='TRIP-needs-discovery.1':(self.host.auth/'invited.json').write_text('[]')
            return raw
        try:
            with patch.object(local_needs_app.json,'dumps',revoke),TestClient(self.needs_app(subject)) as client:
                response=self.discover(client,subject,receipt);self.assertEqual(response.status_code,503,response.text)
                self.assertNotIn('proposal_id',response.text)
        finally:(self.host.auth/'invited.json').write_bytes(invitations)
        connect=LocalDatabase.connect
        class Connection:
            def __init__(self,base):self.base=base
            def __getattr__(self,name):return getattr(self.base,name)
            def __enter__(self):self.base.__enter__();return self
            def __exit__(self,*args):return self.base.__exit__(*args)
            def close(self):self.base.close();raise OSError('synthetic original RUN cleanup loss')
        def wrapped(database,*args,**kwargs):return Connection(connect(database,*args,**kwargs))
        with patch.object(LocalDatabase,'connect',wrapped),TestClient(self.needs_app(subject)) as client:
            response=self.discover(client,subject,receipt);self.assertEqual(response.status_code,503,response.text)
            self.assertNotIn('proposal_id',response.text)
        with TestClient(self.needs_app(subject)) as client:self.published(self.discover(client,subject,receipt))
        self.assertEqual(model.calls,2)


if __name__=='__main__':unittest.main(verbosity=2)
