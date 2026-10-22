"""NEEDS codecs/public seam fixtures and actual AUTH entry rejection, no DB/listener."""
import base64
import json
import os
from unittest.mock import patch
from fastapi.testclient import TestClient
from cj_auth.interfaces import Fact
from cj_needs.domain import Command,Receipt,Snapshot,Revision,Conflict,InvalidInput
from cj_needs.boundary import Boundary,OperationWithheld
from cj_api.needs_composition import create_needs_composed_app,NeedsWireConfiguration
from cj_api.composition import CompositionUnavailable
from test_composition import SyntheticFixture

class NeedsWireChecks(SyntheticFixture):
    def setUp(self):
        super().setUp();self.env=patch.dict(os.environ,{'CJ_ENV':'local'});self.env.start();self.addCleanup(self.env.stop)
        self.connected=False
        def no_connect():self.connected=True;raise AssertionError('No DB in wire fixture')
        self.args=dict(environment='local',jwt_configuration=self.config,verification_keys=self.keys,
            access_provider=self.policy,resolve=lambda p:(no_connect,'fixture-scope'))
        self.options=NeedsWireConfiguration(131072,524288)
        self.client=TestClient(create_needs_composed_app(configuration=self.options,**self.args));self.addCleanup(self.client.close)
        self.headers={'Authorization':'Bearer '+self.token}
    def raw(self,changes=None,**extra):
        obj=dict(action_id='a1',needs_id='n1',expected_version=0,source={'kind':'manual','text':'Synthetic e\u0301 中文, dates undecided'},
            changes=changes if changes is not None else {'party_size':{'state':'known','value':3},'budget_total':{'state':'unknown'}})
        obj.update(extra);return json.dumps(obj,ensure_ascii=False,indent=1).encode()
    def post(self,raw):return self.client.post('/v1/needs-actions',content=raw,headers=dict(self.headers,**{'Content-Type':'application/octet-stream'}))
    def get(self,path,**q):return self.client.get(path,params=q,headers=self.headers)
    def fixture(self,ctx):return patch.object(Boundary,'with_operation',side_effect=lambda token,callback:callback(ctx))

    def test_original_action_revision_and_missing_fields_no_defaults(self):
        owner=self;raw=self.raw();content=json.dumps(Command(raw).data['changes'],ensure_ascii=False).encode()
        class Ctx:
            def act(self,c):owner.assertEqual(c.raw,raw);return Receipt('a1','n1',1)
            def query_action(self,aid):return Receipt('a1','n1',1) if aid=='a1' else None
            def detail(self,nid):return Snapshot(nid,1,content)
            def revision(self,nid,version):return Revision(nid,version,'a1',raw,content)
        with self.fixture(Ctx()):
            saved=self.post(raw);self.assertEqual(saved.status_code,200,saved.text)
            self.assertEqual(saved.json()['receipt'],self.get('/v1/needs-action-receipts',action_id='a1').json()['receipt'])
            self.assertEqual(saved.headers['X-Request-ID'],saved.json()['request_id'])
            self.assertIsNone(self.get('/v1/needs-action-receipts',action_id='absent').json()['receipt'])
            detail=self.get('/v1/needs',needs_id='n1').json()['needs']
            self.assertEqual(set(detail['fields']),{'party_size','budget_total'})
            self.assertEqual(detail['fields']['budget_total'],{'state':'unknown'})
            self.assertEqual(detail['source_kind'],'user_provided')
            revision=self.get('/v1/needs-revisions',needs_id='n1',version=1).json()['revision']
            self.assertEqual(base64.b64decode(revision['original_input_utf8_base64']),raw)
            self.assertEqual(base64.b64decode(revision['content_utf8_base64']),content)

    def test_observations_money_local_time_and_fixed_user_claim_preserved(self):
        unknown={'state':'unknown'}
        event={'date':{'state':'known','value':'2026-11-01'},'time':{'state':'known','value':'01:30'},'timezone':{'state':'known','value':'America/New_York'},'place':unknown}
        changes={'arrival':event,'budget_total':{'state':'known','value':'1000.00'},'budget_paid':{'state':'missing'},
            'pace':{'state':'uncertain','note':'Undecided / 未定'},'companions':{'mother':'Synthetic companion'},
            'fixed_items':[{'item_id':'i1','kind':'hotel','description':'User reports booking','applies_to':['companion:mother'],
              'locked':{'state':'known','value':True},'booking_status':{'state':'known','value':'booked'},'start':event,'end':{k:unknown for k in event}}]}
        raw=self.raw(changes);content=json.dumps(changes,ensure_ascii=False).encode()
        class Ctx:
            def act(self,c):return Receipt('a1','n1',1)
            def detail(self,n):return Snapshot(n,1,content)
        with self.fixture(Ctx()):
            self.assertEqual(self.post(raw).status_code,200)
            fields=self.get('/v1/needs',needs_id='n1').json()['needs']['fields']
            self.assertEqual(fields,changes)
            self.assertNotIn('budget_currency',fields)
            self.assertTrue(fields['fixed_items'][0]['locked']['value'])

    def test_invalid_inputs_authority_and_nonfinite_fail_before_connection(self):
        for raw in [self.raw(owner='caller'),self.raw(source={'kind':'message','text':'claim'}),self.raw(source={'kind':'manual','text':'claim','verified':True}),
                    self.raw({'party_size':{'state':'known','value':True}}),self.raw({'budget_total':{'state':'known','value':0}}),
                    self.raw({'party_size':None}),self.raw(changes={}),b'\xff',self.raw().replace(b'"a1"',b'"a1", "action_id":"second"')]:
            self.assertEqual(self.post(raw).status_code,400)
        self.assertEqual(self.post(b'x'*131073).status_code,413)
        for url in ['/v1/needs?needs_id=n1&owner=a','/v1/needs-revisions?needs_id=n1&version=0','/v1/needs-action-receipts?action_id=a1&action_id=a1']:
            self.assertEqual(self.client.get(url,headers=self.headers).status_code,400)
        self.assertFalse(self.connected)

    def test_actual_auth_unknown_denied_and_missing_config(self):
        for fact in [Fact.NO,Fact.UNKNOWN]:
            self.policy.invited=fact
            result=self.get('/v1/needs',needs_id='n1');self.assertEqual(result.status_code,503)
            self.assertNotIn('needs',result.json());self.assertFalse(self.connected)
        self.assertEqual(self.client.get('/v1/needs?needs_id=n1').status_code,401)
        for key in ['resolve','verification_keys','access_provider']:
            with self.assertRaises(CompositionUnavailable):create_needs_composed_app(configuration=self.options,**dict(self.args,**{key:None}))

    def test_conflict_invalid_resultant_reference_and_unknown_never_return_receipt(self):
        for exc,status in [(Conflict(),409),(InvalidInput(),400),(OperationWithheld('a1',True),503)]:
            with patch.object(Boundary,'with_operation',side_effect=exc):
                result=self.post(self.raw());self.assertEqual(result.status_code,status);self.assertNotIn('receipt',result.json())
                if status==503:self.assertEqual(result.json()['error']['recovery'],'reconcile_original')

    def test_required_null_missing_and_mismatched_historical_binding(self):
        class Ctx:
            def detail(self,n):return None
            def revision(self,n,v):return None
        with self.fixture(Ctx()):
            self.assertIsNone(self.get('/v1/needs',needs_id='absent').json()['needs'])
            self.assertIsNone(self.get('/v1/needs-revisions',needs_id='absent',version=1).json()['revision'])
        raw=self.raw();content=b'{}'
        class Wrong:
            def revision(self,n,v):return Revision(n,v,'different-action',raw,content)
        with self.fixture(Wrong()):
            result=self.get('/v1/needs-revisions',needs_id='n1',version=1)
            self.assertEqual(result.status_code,503);self.assertNotIn('revision',result.json())
