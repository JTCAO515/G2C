"""Protected legacy, actual signed API/run_once/Meter/Fake/Signer/act, fresh PG."""
import json,sys,time,unittest
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend/draft/tests'),str(ROOT/'backend/agent/tests'),str(ROOT/'backend/cj_api/tests'),str(ROOT/'scripts')]
from e2e_local import Harness,CONNINFO
from registered_host_support import RegisteredHost
import needs_runtime_pg as source_fixture
import run_worker,dev_auth
from cj_api.local_app import LocalDatabase,create_local_app,scope_for,ISSUER
from cj_message.travel import ABI
from cj_agent.provider import FakeProvider
from cj_agent.draft import trip_scope_for
from cj_trip.domain import packed
from cj_trip.confirmation import ConfirmationSigner
from cj_trip.postgres import Repository
from cj_trip.local_needs_app import create_local_needs_app
from cj_trip.local_manual_app import create_local_manual_app


class SourceInitializationChecks(unittest.TestCase):
    headers=Harness.headers
    setup_source=source_fixture.NeedsPlanChecks.setup_source
    @classmethod
    def setUpClass(cls):
        Harness.setUpClass.__func__(cls)
        cls.host=RegisteredHost(cls.auth/'source-initializations',Path(CONNINFO),{s:(30,3,30000) for s in ('source-init','source-stale','source-concurrent','source-rollback','source-ack','source-expiry')})
        cls.env=dict(CJ_LOCAL_NEEDS_PROFILE='manual-v1',CJ_LOCAL_TRAVEL_CONTEXT='message-travel.1')
        cls.signer=ConfirmationSigner(b'synthetic-source-initialization-key-12345')
        for subject in cls.host.subjects:dev_auth.activate_travel(Path(CONNINFO),subject,cls.host.profiles[subject][1],ABI)
    tearDownClass=classmethod(Harness.tearDownClass.__func__)

    def source_app(self,subject):return create_local_needs_app(conninfo_path=CONNINFO,auth_dir=self.host.auth,run_context=self.host.profiles[subject][1],confirmation_signer=self.signer)
    def post(self,client,subject,path,raw):return client.post(path,content=raw,headers={**self.host.headers[subject],'Content-Type':'application/octet-stream'})
    def legacy(self,subject):
        self.setup_source(subject);context=self.host.profiles[subject][1];owner=scope_for(ISSUER,subject)
        db=LocalDatabase(CONNINFO,run_context=context,travel_context=True,needs_context=True)
        model=FakeProvider();result=run_worker.run_once(db,model,self.host.auth)[0]
        self.assertIsNotNone(result.proposal_id);self.assertEqual(result.status,'completed')
        repository=Repository(lambda:db.connect(owner),trip_scope_for(owner),self.signer,structured=True)
        detail=repository.proposal_detail(result.proposal_id)
        self.assertNotIn('content_version',json.loads(detail.proposal.content))
        action=self.signer.issue(repository.scope,detail,action_id='original-accept',kind='accept',candidate_hash=detail.candidate_hash).action
        original=create_local_app(conninfo_path=CONNINFO,auth_dir=self.host.auth,run_context=context,
            travel_context=True,needs_profile='manual-v1',confirmation_signer=self.signer)
        with TestClient(original) as client:
            accepted=self.post(client,subject,'/v1/trip-actions',action.raw());self.assertEqual(accepted.status_code,200,accepted.text)
        trip=repository.detail(detail.proposal.trip_id);self.assertEqual(trip.version,1)
        unknown={key:dict(state='unknown') for key in ('date','time','timezone','utc_offset')}
        initialization=dict(version='TRIP-initialize.1',request_id='initialize-'+subject,trip_id=trip.trip_id,
            expected_version=1,original_hash=sha256(trip.content).hexdigest(),
            items=[dict(id=v['id'],schedule=dict(start=unknown,end=unknown),fixed=dict(state='known',value=False)) for v in json.loads(trip.content)['items']])
        raw=packed(dict(version='TRIP-source-initialize.1',needs_reference=dict(id='visit',expected_version=1),initialization=initialization))
        return db,repository,trip,raw,model

    def prepare(self,client,subject,raw):
        response=self.post(client,subject,'/v1/trip-source-initializations',raw)
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(response.json()['version'],'TRIP-source-initialize-result.1')
        return response.json()['preparation']
    def save(self,p):return packed(dict(version='TRIP-source-initialize-save.1',action_id='accept-initialization',proposal_id=p['proposal_id'],candidate_hash=p['candidate_hash']))

    def test_actual_protected_legacy_initialization_new_version_and_old_guard_retained(self):
        subject='source-init';db,repo,trip,raw,model=self.legacy(subject)
        legacy=create_local_manual_app(conninfo_path=CONNINFO,auth_dir=self.host.auth,confirmation_signer=self.signer,run_context=self.host.profiles[subject][1])
        with TestClient(legacy) as client:
            denied=self.post(client,subject,'/v1/trip-structured-initializations',packed(json.loads(raw)['initialization']))
            self.assertEqual(denied.status_code,503,denied.text)
        with TestClient(self.source_app(subject)) as client:
            p=self.prepare(client,subject,raw);self.assertEqual(p['content']['content_version'],'structured.1')
            self.assertEqual(p['item_source_association']['status'],'UNKNOWN')
            self.assertTrue(p['item_source_association']['zh'] and p['item_source_association']['en'])
            for old,new in zip(json.loads(trip.content)['items'],p['content']['items']):
                self.assertEqual(old['text'],new['text']);self.assertEqual(new['schedule']['start']['date'],{'state':'unknown'})
            self.assertEqual(repo.detail(trip.trip_id),trip)
            foreign='source-stale'
            self.assertEqual(self.post(client,foreign,'/v1/trip-source-initializations',raw).status_code,503)
            save=self.save(p);response=self.post(client,subject,'/v1/trip-source-initialization-saves',save)
            self.assertEqual(response.status_code,200,response.text);receipt=response.json()['receipt']
            self.assertEqual(receipt['trip_id'],trip.trip_id);self.assertEqual(receipt['committed_version'],2)
            self.assertEqual(self.post(client,subject,'/v1/trip-source-initialization-saves',save).json()['receipt'],receipt)
            self.assertEqual(repo.detail(trip.trip_id).content,packed(p['content']))
            altered=json.loads(save);altered['candidate_hash']='0'*64
            self.assertEqual(self.post(client,subject,'/v1/trip-source-initialization-saves',packed(altered)).status_code,409)
        with TestClient(self.source_app(subject)) as rebuilt:
            got=rebuilt.get('/v1/trip-source-initialization-receipts',params={'action_id':'accept-initialization'},headers=self.host.headers[subject])
            self.assertEqual(got.json()['receipt'],receipt)
        self.assertEqual(model.calls,2)

    def test_source_correction_and_retargeting_refuse_new_effects(self):
        subject='source-stale';db,repo,trip,raw,model=self.legacy(subject)
        with TestClient(self.source_app(subject)) as client:
            wrong=json.loads(raw);wrong['needs_reference']['id']='other'
            self.assertEqual(self.post(client,subject,'/v1/trip-source-initializations',packed(wrong)).status_code,503)
            p=self.prepare(client,subject,raw)
        with patch.dict(__import__('os').environ,self.env),self.host.api(subject) as current:
            changed=self.post(current,subject,'/v1/needs-actions',packed(dict(action_id='correction',needs_id='visit',expected_version=1,
                source=dict(kind='manual',text='explicit correction'),changes=dict(party_size=dict(state='known',value=2)))))
            self.assertEqual(changed.status_code,200,changed.text)
        with TestClient(self.source_app(subject)) as client:
            self.assertEqual(self.post(client,subject,'/v1/trip-source-initialization-saves',self.save(p)).status_code,503)
            recovered=client.get('/v1/trip-source-initializations',params={'request_id':'initialize-'+subject},headers=self.host.headers[subject])
            self.assertEqual(recovered.status_code,503)
        self.assertEqual(repo.detail(trip.trip_id),trip);self.assertIsNone(repo.query_action('accept-initialization'))

    def test_concurrent_original_accept_commits_once(self):
        subject='source-concurrent';db,repo,trip,raw,model=self.legacy(subject)
        with TestClient(self.source_app(subject)) as client:p=self.prepare(client,subject,raw)
        save=self.save(p)
        def send():
            with TestClient(self.source_app(subject)) as client:return self.post(client,subject,'/v1/trip-source-initialization-saves',save)
        with ThreadPoolExecutor(max_workers=2) as pool:responses=[f.result(timeout=30) for f in [pool.submit(send),pool.submit(send)]]
        self.assertEqual([r.status_code for r in responses],[200,200],[r.text for r in responses])
        self.assertEqual(responses[0].json()['receipt'],responses[1].json()['receipt']);self.assertEqual(repo.detail(trip.trip_id).version,2)

    def test_actual_rollback_and_physical_ack_unknown_recover_original_receipt(self):
        for mode in ('rollback','ack'):
            subject='source-'+mode
            with self.subTest(mode=mode):
                db,repo,trip,raw,model=self.legacy(subject)
                with TestClient(self.source_app(subject)) as client:p=self.prepare(client,subject,raw)
                connect=LocalDatabase.connect
                class Cursor:
                    def __init__(self,base,owner):self.base,self.owner=base,owner
                    def __getattr__(self,name):return getattr(self.base,name)
                    def execute(self,query,*args,**kw):
                        if query.startswith('INSERT INTO cj_trip_manual_intent'):
                            self.owner.wrote=True
                            if mode=='rollback':raise OSError('synthetic original act rollback')
                        self.base.execute(query,*args,**kw);return self
                class Connection:
                    def __init__(self,base):self.base,self.wrote=base,False
                    def __getattr__(self,name):return getattr(self.base,name)
                    def cursor(self):return Cursor(self.base.cursor(),self)
                    def commit(self):
                        self.base.commit()
                        if mode=='ack' and self.wrote:raise OSError('synthetic ACK loss after physical commit')
                def wrapped(database,*args,**kwargs):return Connection(connect(database,*args,**kwargs))
                with patch.object(LocalDatabase,'connect',wrapped),TestClient(self.source_app(subject)) as client:
                    response=self.post(client,subject,'/v1/trip-source-initialization-saves',self.save(p))
                    self.assertEqual(response.status_code,503,response.text)
                with TestClient(self.source_app(subject)) as rebuilt:
                    got=rebuilt.get('/v1/trip-source-initialization-receipts',params={'action_id':'accept-initialization'},headers=self.host.headers[subject])
                    self.assertEqual(got.status_code,200,got.text)
                    if mode=='rollback':self.assertIsNone(got.json()['receipt']);self.assertEqual(repo.detail(trip.trip_id),trip)
                    else:self.assertEqual(got.json()['receipt']['committed_version'],2);self.assertEqual(repo.detail(trip.trip_id).version,2)

    def test_confirmation_expiring_after_original_act_rolls_back_before_commit(self):
        from cj_trip import source_initialization
        from cj_trip.domain import Proposal
        subject='source-expiry';db,repo,trip,raw,model=self.legacy(subject)
        def short(pid,tid,version,basis,expires,content):return Proposal(pid,tid,version,basis,int(time.time())+2,content)
        with patch.object(source_initialization,'Proposal',short),TestClient(self.source_app(subject)) as client:
            p=self.prepare(client,subject,raw)
        original_act=Repository._act_in_tx
        def late(repository,cur,action):
            result=original_act(repository,cur,action)
            if action.action_id=='accept-initialization':time.sleep(2.1)
            return result
        with patch.object(Repository,'_act_in_tx',late),TestClient(self.source_app(subject)) as client:
            response=self.post(client,subject,'/v1/trip-source-initialization-saves',self.save(p))
            self.assertEqual(response.status_code,409,response.text)
        self.assertEqual(repo.detail(trip.trip_id),trip);self.assertIsNone(repo.query_action('accept-initialization'))
        self.assertEqual(repo.proposal_detail(p['proposal_id']).status,'pending')


if __name__=='__main__':unittest.main()
