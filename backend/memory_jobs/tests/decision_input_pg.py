"""Actual accepted/modified Trip + signed MSG3 + genuine source/Trip/Memory locks."""
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json,sys,unittest
from pathlib import Path
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend/trip/tests'),str(ROOT/'scripts')]
import manual_pg as manual
import dev_auth,message_trip_profile,local_run_context
from cj_api.local_app import create_local_app,scope_for,ISSUER
from cj_message.source import SourceQuery
from cj_memory.manual import ManualPolicy
from cj_memory_jobs.collection_app import create_collection_app
from cj_memory_jobs.extraction import CollectionPolicy
from cj_memory_jobs.source_policy import SourcePolicy
from cj_memory_jobs.decision_input import prepared,DATA_VERSION
from cj_memory_jobs.codec import Unavailable
from cj_trip.decision_lease import DecisionAuthority
from cj_trip.decision_source import DecisionQuery
from cj_trip.domain import Denied,packed
from cj_usage.background_exit import ModelInput


class DecisionInputChecks(manual.ManualChecks):
    def test_real_modified_trip_and_committed_discussion_feed_bounded_data(self):
        # ManualChecks.setUp already used the original worker/Fake, user accept
        # and signed structured initialization, producing accepted Trip version2.
        local_run_context.provision_budget(Path(manual.CONNINFO),self.run_context,'alice')
        dev_auth.activate_travel(Path(manual.CONNINFO),'alice',self.run_context,'MESSAGE-TRAVEL-CONSUMER@1')
        self.assertEqual(message_trip_profile.activate(Path(manual.CONNINFO),'alice',self.run_context,'MESSAGE-TRIP-CONSUMER@1'),'activated')
        app=create_local_app(conninfo_path=manual.CONNINFO,auth_dir=self.auth,run_context=self.run_context,
            travel_context=True,trip_context=True)
        headers={**self.headers('alice'),'Content-Type':'application/octet-stream'};token=headers['Authorization'][7:]
        with TestClient(app) as client:
            head=client.put('/v1/conversations',params={'conversation_id':'decision-source'},headers=headers).json()
            raw=packed(dict(version='MESSAGE-send.3',conversation_id='decision-source',message_id='selected-decision',
                text='Discuss the plan I accepted, without claiming I visited it',trip_id=None,creation_intent='none',
                expected_generation=head['generation'],expected_sequence=0,travel_context=None,needs_reference=None,
                trip_context=dict(id=self.trip_id,expected_version=self.base_version,day=None,item_id=None)))
            response=client.post('/v3/messages',content=raw,headers=headers)
            self.assertEqual(response.status_code,200,response.text)
        extraction=CollectionPolicy(frozenset({'self'}),frozenset({'planning.choice'}),5,4096,lambda entry:True,lambda entry,rows:False)
        policy=ManualPolicy(extraction.subjects,extraction.slots,frozenset({'long_term'}),frozenset(),
            datetime.now(timezone.utc)+timedelta(hours=1),lambda command,raw:True,lambda command,raw:True)
        collection=create_collection_app(conninfo_path=manual.CONNINFO,auth_dir=self.auth,run_context=self.run_context,
            resolve_collection=lambda principal:(extraction,policy,lambda entry:(None,None))).state.memory_history
        collection.service.apply_consent(token,packed(dict(version='MEMORY-HISTORY@1',action_id='enable',operation='enable',
            conversation_id='decision-source',expected_generation=head['generation'],expected_epoch=0,expected_source_version=0)))
        query=SourceQuery('decision-source',head['generation'],0,0,1,1,1)
        authority=DecisionAuthority(self.decision_reader(),token)
        selected=DecisionQuery(self.trip_id,self.base_version,sha256(self.content).hexdigest())
        holder={}
        def read(context):
            repository,principal,guard=collection.service._binding(context,token)
            actual=SourcePolicy(repository,principal,guard)
            class Joined:
                @contextmanager
                def hold(self,who,scope,query):
                    with authority.hold(who,selected,max_source_bytes=4_000_000) as lease:
                        holder['lease']=lease
                        with actual.hold(who,scope,query) as permit:yield permit
            def project(snapshot):
                holder.update(snapshot=snapshot,tx=actual.transaction)
                result,count=prepared(actual.transaction,snapshot,holder['lease'],extraction,'incremental',max_payload_bytes=262144)
                self.assertEqual(count,1)
                with self.assertRaises(Unavailable):prepared(actual.transaction,snapshot,holder['lease'],extraction,'incremental',max_payload_bytes=1)
                return result
            return context.with_enabled_source(query,Joined(),project)
        result=collection.boundary.with_history_context(token,read)
        model=ModelInput.parse(result);data=json.loads(model.messages[0][1])
        self.assertEqual(data['version'],DATA_VERSION)
        self.assertEqual(len(data['trip_decisions']),1)
        self.assertEqual(json.loads(data['trip_decisions'][0]['document']),json.loads(self.content))
        self.assertEqual(data['trip_decisions'][0]['anchor_ref'],data['messages'][0]['ref'])
        self.assertTrue(data['trip_decisions'][0]['ref'].startswith('trip-decision-v1:'))
        self.assertNotIn('trip_id',data['trip_decisions'][0])
        self.assertIn('never that a visit happened',model.system)
        with self.assertRaises(Denied):prepared(holder['tx'],holder['snapshot'],holder['lease'],extraction,'incremental',max_payload_bytes=262144)
        print('PASS actual original worker/user accept/modified Trip2 + signed MSG3 before consent + enabled protected source + genuine Trip→Memory lease produce bounded opaque decision data; expired lease/byte bound refuse; unpublished input only, no extraction/dispatch/publication claim')


if __name__=='__main__':
    unittest.main(defaultTest='DecisionInputChecks.test_real_modified_trip_and_committed_discussion_feed_bounded_data',verbosity=2)
