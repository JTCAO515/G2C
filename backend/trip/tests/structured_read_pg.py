"""Signed formal discovery through real producer/accept, not seeded Trip rows."""
import sys,json,unittest
from pathlib import Path
from hashlib import sha256
from unittest.mock import patch
from fastapi.testclient import TestClient
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend/trip/tests'),str(ROOT/'backend/draft/tests'),str(ROOT/'backend/agent/tests'),str(ROOT/'backend/cj_api/tests'),str(ROOT/'scripts')]
import needs_actions_pg as needs_fixture
import manual_pg as manual_fixture
from e2e_local import Harness,CONNINFO
from registered_host_support import RegisteredHost
from cj_trip.local_structured_read import create_local_structured_read_app,VERSION
from cj_trip.domain import packed
from cj_trip.confirmation import ConfirmationSigner
from cj_message.travel import ABI
import dev_auth


class ReadChecks(unittest.TestCase):
    headers=Harness.headers
    setup_source=needs_fixture.NeedsActionChecks.setup_source
    worker=needs_fixture.NeedsActionChecks.worker
    plan=needs_fixture.NeedsActionChecks.plan
    action=needs_fixture.NeedsActionChecks.action
    post=needs_fixture.NeedsActionChecks.post
    @classmethod
    def setUpClass(cls):
        Harness.setUpClass.__func__(cls)
        cls.host=RegisteredHost(cls.auth/'discovery',Path(CONNINFO),{s:(12,2,30000) for s in ('read','foreign','revoke')})
        cls.env=dict(CJ_LOCAL_NEEDS_PROFILE='manual-v1',CJ_LOCAL_TRAVEL_CONTEXT='message-travel.1')
        cls.signer=ConfirmationSigner(b'synthetic-trip-discovery-signer-123456789')
        for subject in cls.host.subjects:dev_auth.activate_travel(Path(CONNINFO),subject,cls.host.profiles[subject][1],ABI)
    tearDownClass=classmethod(Harness.tearDownClass.__func__)
    def reader(self,subject,**kwargs):return create_local_structured_read_app(conninfo_path=CONNINFO,
        auth_dir=self.host.auth,run_context=self.host.profiles[subject][1],**kwargs)

    def test_real_pending_accept_discover_detail_cursor_and_rebuild(self):
        app,outcome,db=self.plan('read')
        with TestClient(self.reader('read')) as client,TestClient(app) as writer:
            empty=client.get('/v1/trip-structured-list',headers=self.host.headers['read']);self.assertEqual(empty.status_code,200,empty.text)
            self.assertEqual(empty.json()['trips'],[])
            accepted=self.post(writer,'read',self.action('read',outcome,'accept'));self.assertEqual(accepted.status_code,200,accepted.text)
            trip_id=accepted.json()['receipt']['trip_id']
            page=client.get('/v1/trip-structured-list',params={'limit':'1'},headers=self.host.headers['read'])
            self.assertEqual(page.status_code,200,page.text);value=page.json();self.assertEqual(value['version'],VERSION)
            self.assertEqual(value['next_after'],trip_id);self.assertEqual(value['trips'][0]['trip_id'],trip_id)
            detail=client.get('/v5/trip-structured',params={'trip_id':trip_id},headers=self.host.headers['read'])
            self.assertEqual(detail.status_code,200,detail.text);original=detail.json()['trip']
            self.assertEqual(original['version'],1);self.assertEqual(original['content']['content_version'],'structured.2')
            self.assertEqual(original['content']['items'][0]['schedule']['start']['time'],dict(state='known',value='09:00'))
            self.assertEqual(original['content_sha256'],sha256(packed(original['content'])).hexdigest())
            self.assertEqual(value['trips'][0]['content_sha256'],original['content_sha256'])
            last=client.get('/v1/trip-structured-list',params={'limit':'1','after':trip_id},headers=self.host.headers['read']).json()
            self.assertEqual(last['trips'],[]);self.assertIsNone(last['next_after'])
            self.assertEqual(client.get('/v1/trip-structured-list',headers=self.host.headers['foreign']).json()['trips'],[])
            self.assertIsNone(client.get('/v5/trip-structured',params={'trip_id':trip_id},headers=self.host.headers['foreign']).json()['trip'])
            old=writer.get('/v4/trip-structured',params={'trip_id':trip_id},headers=self.host.headers['read'])
            self.assertEqual(old.status_code,200,old.text);self.assertEqual(old.json()['version'],'TRIP-needs-result.1')
            self.assertNotIn('content_sha256',old.json()['trip'])
        with TestClient(self.reader('read')) as rebuilt:
            self.assertEqual(rebuilt.get('/v5/trip-structured',params={'trip_id':trip_id},headers=self.host.headers['read']).json()['trip'],original)
        with TestClient(self.reader('read',max_response_bytes=1)) as bounded:
            response=bounded.get('/v5/trip-structured',params={'trip_id':trip_id},headers=self.host.headers['read'])
            self.assertEqual(response.status_code,503);self.assertNotIn(trip_id,response.text)

    def test_exact_queries_missing_and_expired_signed_identity(self):
        with TestClient(self.reader('foreign')) as client:
            self.assertEqual(client.get('/v1/trip-structured-list').status_code,401)
            expired={'Authorization':'Bearer '+dev_auth.token(self.host.auth,'foreign',-1)}
            self.assertEqual(client.get('/v1/trip-structured-list',headers=expired).status_code,503)
            for query in ('limit=0','limit=101','limit=01','limit=1&limit=2','owner=read','after=../x'):
                self.assertEqual(client.get('/v1/trip-structured-list?'+query,headers=self.host.headers['foreign']).status_code,400)
            self.assertEqual(client.get('/v5/trip-structured?trip_id=x&trip_id=y',headers=self.host.headers['foreign']).status_code,400)

    def test_actual_revocation_after_private_encoding_withholds(self):
        invited=self.host.auth/'invited.json';original=invited.read_bytes()
        from cj_trip import local_structured_read as api
        dumps=json.dumps
        def revoke(value,*args,**kwargs):
            raw=dumps(value,*args,**kwargs)
            if type(value) is dict and value.get('version')==VERSION:
                invited.write_text(dumps([s for s in json.loads(original) if s!='revoke']))
            return raw
        try:
            with TestClient(self.reader('revoke')) as client,patch.object(api.json,'dumps',revoke):
                response=client.get('/v1/trip-structured-list',headers=self.host.headers['revoke'])
                self.assertEqual(response.status_code,503,response.text)
                self.assertNotIn('trips',response.json())
        finally:invited.write_bytes(original)


class OriginalStructuredRead(unittest.TestCase):
    headers=Harness.headers;send=Harness.send;work=Harness.work
    @classmethod
    def setUpClass(cls):
        Harness.setUpClass.__func__(cls)
        cls.old_app=cls.app
        cls.signer=ConfirmationSigner(b'synthetic-old-trip-discovery-signer-123456')
        from cj_api.local_run_context import load_run_context
        import time
        path=cls.auth/'discovery-context.json';now=int(time.time())
        path.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',history=[],current=dict(
            meter=dict(unit='provider_call',budget=100,period_start=now-60,period_end=now+3600,
                max_steps=20,max_tools=10,max_output=10000,max_seconds=600),
            output_limits=dict(model=4000,tool=8000,memory=2000)))))
        cls.run_context=load_run_context(path)
        from cj_trip.local_manual_app import create_local_manual_app
        cls.app=create_local_manual_app(conninfo_path=CONNINFO,auth_dir=cls.auth,
            confirmation_signer=cls.signer,run_context=cls.run_context)
    tearDownClass=classmethod(Harness.tearDownClass.__func__)
    setUp=manual_fixture.ManualChecks.setUp
    legacy_trip=manual_fixture.ManualChecks.legacy_trip
    write=manual_fixture.ManualChecks.write
    def test_original_initialized_structured_one_and_legacy_page_cursor(self):
        legacy_id,*_=self.legacy_trip()
        app=create_local_structured_read_app(conninfo_path=CONNINFO,auth_dir=self.auth,run_context=self.run_context)
        found=[];cursor='';seen=set()
        with TestClient(app) as client:
            while True:
                page=client.get('/v1/trip-structured-list',params={'limit':'1','after':cursor},headers=self.headers('alice'))
                self.assertEqual(page.status_code,200,page.text);value=page.json();found.extend(value['trips'])
                cursor=value['next_after']
                if cursor is None:break
                self.assertNotIn(cursor,seen);seen.add(cursor)
            matches=[trip for trip in found if trip['trip_id']==self.trip_id]
            self.assertEqual(len(matches),1);self.assertEqual(matches[0]['content_version'],'structured.1')
            self.assertNotIn(legacy_id,[trip['trip_id'] for trip in found])
            self.assertIsNone(client.get('/v5/trip-structured',params={'trip_id':legacy_id},headers=self.headers('alice')).json()['trip'])
            trip=client.get('/v5/trip-structured',params={'trip_id':self.trip_id},headers=self.headers('alice')).json()['trip']
            self.assertEqual(packed(trip['content']),self.content);self.assertEqual(trip['version'],2)


if __name__=='__main__':unittest.main(verbosity=2)
