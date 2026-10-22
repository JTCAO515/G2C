"""Wire codec fixtures plus actual pinned AUTH entry denial; no DB/listener."""
import base64
import json
import os
from unittest.mock import patch
from fastapi.testclient import TestClient
from cj_api.trip_composition import create_trip_composed_app,TripWireConfiguration
from cj_api.composition import CompositionUnavailable
from cj_auth.interfaces import Fact
from cj_trip.domain import Action,Proposal,ProposalDetail,Receipt,Trip,packed,Conflict,Denied
from cj_trip.operation import OperationWithheld
from cj_trip.auth_boundary import Boundary
from test_composition import SyntheticFixture

class TripWireChecks(SyntheticFixture):
    def setUp(self):
        super().setUp()
        self.env=patch.dict(os.environ,{'CJ_ENV':'local'});self.env.start();self.addCleanup(self.env.stop)
        self.options=TripWireConfiguration(1024,2,65536)
        self.connected=False
        def no_connect():self.connected=True;raise AssertionError('No DB in fixture')
        self.args=dict(environment='local',jwt_configuration=self.config,verification_keys=self.keys,
            access_provider=self.policy,resolve=lambda p:(no_connect,'fixture-scope'),confirmation_validator=None)
        self.app=create_trip_composed_app(configuration=self.options,**self.args)
        self.client=TestClient(self.app);self.addCleanup(self.client.close)
        self.headers={'Authorization':'Bearer '+self.token}
        self.content=packed({'title':'Synthetic e\u0301 中文','items':[{'id':'i1','text':'Pending synthetic item','verification':'pending','evidence':[]}]})
        self.p=Proposal('p1','t1',0,'basis1',1,self.content)
        self.action=Action('a1','accept','p1',self.p.digest('fixture-scope'),'server-confirmation')
    def post(self,raw):return self.client.post('/v1/trip-actions',content=raw,headers=dict(self.headers,**{'Content-Type':'application/octet-stream'}))
    def get(self,path,**q):return self.client.get(path,params=q,headers=self.headers)
    def fixture(self,ctx):
        return patch.object(Boundary,'with_operation',side_effect=lambda token,operation:operation(ctx))

    def test_actual_auth_unknown_and_denied_do_not_connect(self):
        for fact in [Fact.NO,Fact.UNKNOWN]:
            self.policy.invited=fact
            response=self.get('/v1/trip-proposals',proposal_id='p1')
            self.assertEqual(response.status_code,503)
            self.assertEqual(response.json()['error']['outcome'],'unknown')
            self.assertFalse(self.connected)
        self.assertEqual(self.client.get('/v1/trips?limit=1').status_code,401)

    def test_codec_action_original_receipt_and_required_null(self):
        owner=self
        class Context:
            def act(self,a):
                owner.assertEqual(a.raw(),owner.action.raw())
                return Receipt(a.action_id,a.kind,a.proposal_id,a.candidate_hash,'t1',1)
            def query_action(self,aid):return None
        with self.fixture(Context()):
            r=self.post(self.action.raw());self.assertEqual(r.status_code,200,r.text)
            self.assertEqual(r.json()['receipt']['action_id'],'a1')
            self.assertEqual(r.json()['request_id'],r.headers['X-Request-ID'])
            self.assertEqual(r.headers['Cache-Control'],'no-store')
            q=self.get('/v1/trip-action-receipts',action_id='absent')
            self.assertIsNone(q.json()['receipt'])

    def test_public_snapshot_detail_list_exact_content_and_pending(self):
        owner=self
        class Context:
            def proposal_detail(self,pid):return ProposalDetail(owner.p,owner.action.candidate_hash,'pending')
            def detail(self,tid):return Trip(tid,1,owner.content)
            def list_trips(self,after,limit):return [] if after else [Trip('t1',1,owner.content)]
        with self.fixture(Context()):
            snapshot=self.get('/v1/trip-proposals',proposal_id='p1').json()['proposal']
            self.assertEqual((snapshot['status'],snapshot['expires_at']),('pending',1))
            self.assertEqual(snapshot['candidate_hash'],self.action.candidate_hash)
            self.assertEqual(base64.b64decode(snapshot['content_utf8_base64']),self.content)
            detail=self.get('/v1/trip-details',trip_id='t1').json()['trip']
            self.assertEqual(detail['document']['items'][0]['verification'],'pending')
            page=self.get('/v1/trips',limit=1).json();self.assertEqual(page['next_after'],'t1')
            self.assertIsNone(self.get('/v1/trips',limit=1,after='t1').json()['next_after'])

    def test_input_extra_scope_noncanonical_media_and_limits(self):
        for raw in [self.action.raw()+b' ',b'{"owner":"caller","viewed":true}',b'\xff',b'[]']:
            self.assertEqual(self.post(raw).status_code,400)
        self.assertEqual(self.post(b'x'*1025).status_code,413)
        self.assertEqual(self.client.post('/v1/trip-actions',content=self.action.raw(),headers=self.headers).status_code,415)
        for url in ['/v1/trips?limit=3','/v1/trip-details?trip_id=x&owner=a','/v1/trip-action-receipts?action_id=x&action_id=x','/v1/trip-proposals?proposal_id=%ff']:
            self.assertEqual(self.client.get(url,headers=self.headers).status_code,400)
        self.assertFalse(self.connected)

    def test_distinguishable_conflict_and_withheld_never_expose_receipt(self):
        for error,status,recovery in [(Conflict(),409,'do_not_retry'),(Denied(),503,'reconcile_original'),
                                     (OperationWithheld('a1',True),503,'reconcile_original')]:
            with patch.object(Boundary,'with_operation',side_effect=error):
                r=self.post(self.action.raw());self.assertEqual(r.status_code,status)
                self.assertEqual(r.json()['error']['recovery'],recovery)
                self.assertNotIn('receipt',r.json())

    def test_missing_host_config_and_default_confirmation_stays_absent(self):
        for field in ['resolve','verification_keys','access_provider']:
            with self.assertRaises(CompositionUnavailable):
                create_trip_composed_app(configuration=self.options,**dict(self.args,**{field:None}))
        boundary,modules=__import__('cj_api.trip_composition',fromlist=['build_trip_boundary']).build_trip_boundary(**self.args)
        self.assertIsNone(boundary.confirm)
        with self.assertRaises(CompositionUnavailable):
            create_trip_composed_app(configuration=self.options,**dict(self.args,environment='production'))

    def test_same_app_factory_and_mismatched_receipt_withheld(self):
        from cj_api.composition import create_composed_app
        self.policy.invited=Fact.NO
        with TestClient(create_composed_app(**self.kwargs,max_body_bytes=4096,
                trip_configuration=self.options,resolve_trip=self.args['resolve'])) as client:
            self.assertEqual(client.get('/v1/probe').status_code,200)
            self.assertEqual(client.get('/v1/trips?limit=1',headers=self.headers).status_code,503)
        owner=self
        class Context:
            def act(self,a):return Receipt(a.action_id,a.kind,'wrong-proposal',a.candidate_hash,'t1',1)
        with self.fixture(Context()):
            result=self.post(self.action.raw());self.assertEqual(result.status_code,503)
            self.assertNotIn('receipt',result.json())
