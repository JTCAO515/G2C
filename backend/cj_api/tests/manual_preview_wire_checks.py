"""Actual TRIP public lifetime with public detail stub and actual pure edit algorithm."""
import base64,json,os
from unittest.mock import patch
from fastapi.testclient import TestClient
from cj_auth.interfaces import Fact
from cj_trip.domain import Trip,packed
from cj_trip.postgres import Repository
from cj_api.manual_preview_composition import ManualPreviewConfiguration,create_manual_preview_app
from cj_api.composition import CompositionUnavailable
from test_composition import SyntheticFixture

class PreviewChecks(SyntheticFixture):
    def setUp(self):
        super().setUp();self.env=patch.dict(os.environ,{'CJ_ENV':'local'});self.env.start();self.addCleanup(self.env.stop)
        self.content=packed({'title':'Synthetic 原题','items':[{'id':'a','text':'A original','verification':'verified','evidence':['synthetic-a']},
            {'id':'b','text':'B unchanged','verification':'pending','evidence':[]},{'id':'c','text':'C original','verification':'verified','evidence':['synthetic-c']}]})
        self.original=Trip('t1',1,self.content)
        def no_connect():raise AssertionError('No DB in public detail stub fixture')
        self.args=dict(environment='local',jwt_configuration=self.config,verification_keys=self.keys,access_provider=self.policy,resolve=lambda p:(no_connect,'fixture-scope'))
        self.options=ManualPreviewConfiguration(262144,131072,4096,524288)
        self.client=TestClient(create_manual_preview_app(configuration=self.options,**self.args));self.addCleanup(self.client.close)
        self.headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'}
    def request(self,**extra):
        value=dict(trip_id='t1',expected_version=1,original_content_utf8_base64=base64.b64encode(self.content).decode(),
            selected_ids=['a','c'],title_selected=True,title='Changed title',text_updates=[{'item_id':'a','text':'Changed e\u0301 中文'}],order=['c','b','a'])
        value.update(extra);return value
    def post(self,value):return self.client.post('/v1/trip-manual-previews',content=json.dumps(value,ensure_ascii=False).encode(),headers=self.headers)
    def detail(self,values=None):return patch.object(Repository,'detail',return_value=self.original) if values is None else patch.object(Repository,'detail',side_effect=values)
    def test_exact_diff_outside_selection_fact_reset_and_unavailable_save(self):
        with self.detail(),patch.object(Repository,'act',side_effect=AssertionError('Preview must not act')):
            result=self.post(self.request());self.assertEqual(result.status_code,200,result.text)
        p=result.json()['preview'];self.assertEqual(p['preview_status'],'LOCAL');self.assertEqual(p['protection_status'],'UNKNOWN');self.assertFalse(p['can_save'])
        self.assertEqual(result.json()['request_id'],result.headers['X-Request-ID']);self.assertEqual(result.headers['Cache-Control'],'no-store')
        before=json.loads(self.content);after=json.loads(base64.b64decode(p['content_utf8_base64']))
        self.assertEqual(after['items'][1],before['items'][1]);self.assertEqual(after['items'][0],before['items'][2])
        self.assertEqual(after['items'][2]['verification'],'pending');self.assertEqual(after['items'][2]['evidence'],[])
        self.assertEqual([c['path'] for c in p['diff']],[['title'],['items','order'],['items','id','a']])
        self.assertEqual(base64.b64decode(p['original']['content_utf8_base64']),self.content)
        self.assertNotIn('proposal_id',p);self.assertNotIn('action_id',p);self.assertNotIn('confirmation_ref',p)
    def test_noop_and_title_only(self):
        cases=[(dict(selected_ids=[],title_selected=False,title=None,text_updates=[],order=None),[]),
               (dict(selected_ids=[],title_selected=True,title='Title only',text_updates=[],order=None),[['title']])]
        for fields,expected in cases:
            with self.detail():result=self.post(self.request(**fields))
            self.assertEqual(result.status_code,200,result.text)
            self.assertEqual([d['path'] for d in result.json()['preview']['diff']],expected)
            self.assertFalse(result.json()['preview']['can_save'])
    def test_original_conflict_and_unknown_keep_original_request(self):
        import copy
        for fields in [dict(expected_version=2),dict(original_content_utf8_base64=base64.b64encode(b'other original bytes').decode())]:
            request=self.request(**fields);before=copy.deepcopy(request)
            with self.detail():result=self.post(request)
            self.assertEqual(result.status_code,409);self.assertNotIn('preview',result.json());self.assertEqual(request,before)
        for values in [[None],[self.original,None],[self.original,self.original,None]]:
            request=self.request();before=copy.deepcopy(request)
            with self.detail(values):result=self.post(request)
            self.assertEqual(result.status_code,503);self.assertNotIn('preview',result.json());self.assertEqual(request,before)
    def test_unselected_unsupported_authority_and_bounds_rejected(self):
        bad=[dict(text_updates=[{'item_id':'b','text':'not selected'}]),dict(order=['b','a','c']),
             dict(protected_ids=[]),dict(owner='caller'),dict(action_id='not-an-action'),dict(day=1),
             dict(title_selected=False,title='not selected'),dict(selected_ids=['missing'])]
        with self.detail():
            for fields in bad:self.assertEqual(self.post(self.request(**fields)).status_code,400)
        self.assertEqual(self.post(self.request(text_updates=[{'item_id':'a','text':'x'*4097}])).status_code,413)
        duplicate=json.dumps(self.request()).replace('"trip_id": "t1"','"trip_id": "t1", "trip_id":"t2"')
        self.assertEqual(self.client.post('/v1/trip-manual-previews',content=duplicate,headers=self.headers).status_code,400)
    def test_late_version_and_encoding_or_auth_failure_no_success(self):
        from cj_api import manual_preview_routes
        encoder=manual_preview_routes.encode_response
        changed=json.loads(self.content);changed['title']='Concurrent change'
        newer=Trip('t1',2,packed(changed));current=[self.original]
        def change(session,rid,domain):
            body=encoder(session,rid,domain);current[0]=newer;return body
        with patch.object(Repository,'detail',side_effect=lambda _:current[0]),patch.object(manual_preview_routes,'encode_response',side_effect=change):
            result=self.post(self.request());self.assertEqual(result.status_code,409);self.assertNotIn('preview',result.json())
        def unknown(session,rid,domain):
            body=encoder(session,rid,domain);self.policy.invited=Fact.UNKNOWN;return body
        with self.detail(),patch.object(manual_preview_routes,'encode_response',side_effect=unknown):
            result=self.post(self.request());self.assertEqual(result.status_code,503);self.assertNotIn('preview',result.json())
        self.policy.invited=Fact.YES
        with self.detail(),patch.object(manual_preview_routes,'encode_response',side_effect=RuntimeError('PRIVATE_CODEC_SENTINEL')):
            result=self.post(self.request());self.assertEqual(result.status_code,503);self.assertNotIn('PRIVATE_CODEC_SENTINEL',result.text)
    def test_invalid_auth_default_config_and_response_cap(self):
        for fact in [Fact.NO,Fact.UNKNOWN]:
            self.policy.invited=fact
            with patch.object(Repository,'detail',side_effect=AssertionError('No private read on invalid AUTH')):
                result=self.post(self.request());self.assertEqual(result.status_code,503)
        self.policy.invited=Fact.YES
        self.assertEqual(self.client.post('/v1/trip-manual-previews',json=self.request()).status_code,401)
        with self.assertRaises(CompositionUnavailable):create_manual_preview_app(configuration=self.options,**dict(self.args,resolve=None))
        with self.assertRaises(CompositionUnavailable):ManualPreviewConfiguration(True,1,1,1)
        with TestClient(create_manual_preview_app(configuration=ManualPreviewConfiguration(262144,131072,4096,1),**self.args)) as c:
            with self.detail():result=c.post('/v1/trip-manual-previews',json=self.request(),headers=self.headers)
            self.assertEqual(result.status_code,413);self.assertNotIn('preview',result.json())
