"""Isolation consumer proof; old formal producer/worker guards remain closed."""
from datetime import datetime,timedelta,timezone
import json,sys,unittest
from pathlib import Path

from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend/trip/tests'),str(ROOT/'scripts')]
import manual_pg as manual
import dev_auth,local_run_context,message_trip_profile,run_worker
from cj_api.local_app import create_local_app,LocalDatabase,scope_for,ISSUER
from cj_api.local_account_admission_v2 import account_checker_for
from cj_agent.provider import FakeProvider
from cj_auth.interfaces import AdmissionStatus
from cj_memory.formal_runtime import FormalRuntimeConfiguration
from cj_memory.runtime import RuntimeDenied
from cj_memory.typed_local import TypedConfiguration
from cj_memory.typed_api import create_local_typed_app
from cj_message.travel_reference import MessageContextAuthority
from cj_run.core import Binding
from cj_trip.domain import packed


class FormalMemoryChecks(manual.ManualChecks):
    def test_real_formal_reference_never_selects_unrelated_travel_memory(self):
        path=Path(manual.CONNINFO);run=self.run_context
        local_run_context.provision_budget(path,run,'alice')
        dev_auth.activate_travel(path,'alice',run,'MESSAGE-TRAVEL-CONSUMER@1')
        message_trip_profile.activate(path,'alice',run,'MESSAGE-TRIP-CONSUMER@1')
        app=create_local_app(conninfo_path=path,auth_dir=self.auth,run_context=run,travel_context=True,trip_context=True)
        database=LocalDatabase(path,run_context=run,travel_context=True,trip_context=True)
        headers={**self.headers('alice'),'Content-Type':'application/octet-stream'};token=headers['Authorization'][7:]
        receipts={}
        with TestClient(app) as client:
            response=client.post('/v1/travel-context-actions',content=packed(dict(version='TRAVEL-context-action.1',action_id='formal-independent-travel',
                operation='create',travel_context=None)),headers=headers)
            self.assertEqual(response.status_code,200,response.text);travel=response.json()['receipt']['travel_context']
            for name in ('formal','travel','none'):
                head=client.put('/v1/conversations',params={'conversation_id':name},headers=headers).json()
                raw=packed(dict(version='MESSAGE-send.3',conversation_id=name,message_id=name,text='A genuine read-only original',trip_id=None,
                    creation_intent='none',expected_generation=head['generation'],expected_sequence=0,
                    travel_context=dict(id=travel['id'],expected_version=travel['version']) if name=='travel' else None,needs_reference=None,
                    trip_context=dict(id=self.trip_id,expected_version=self.base_version,day=None,item_id=None) if name=='formal' else None))
                response=client.post('/v3/messages',content=raw,headers=headers)
                self.assertEqual(response.status_code,200,response.text);receipts[name]=response.json()['receipt']
        normal=FakeProvider();results=run_worker.run_once(database,normal,self.auth)
        self.assertEqual(normal.calls,3);self.assertTrue(all(r.status=='completed' for r in results),results)
        expires=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
        profile=dict(subjects=['self'],slots={'pace':dict(kind='preference',collection_allowed=True,semantic_resolved=True)},
            extents=['long_term','current'],context_ids=[])
        collection=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',expires_at=expires,profiles={'alice':profile}),
            travel_contexts={'alice':[travel['id']]})
        typed=TypedConfiguration.from_bytes(packed(collection))
        with TestClient(create_local_typed_app(conninfo_path=path,auth_dir=self.auth,configuration=typed)) as client:
            for item,text,extent,context in (
                ('long','A steady long-term pace','long_term',None),
                ('temporary','Only this Travel can be fast','current',dict(kind='travel',id=travel['id'],expected_version=travel['version'])),
            ):
                response=client.post('/v2/memories',content=packed(dict(version='MEMORY-manual.2',operation_id='save-'+item,item_id=item,
                    subject='self',slot='pace',kind='preference',text=text,extent=extent,context=context,occurred_at='date unknown')),headers=headers)
                self.assertEqual(response.status_code,200,response.text)
        config=FormalRuntimeConfiguration.from_bytes(packed(dict(version='local-memory-formal-run.1',collection=collection,
            selections={'alice':dict(subject='self',slots=['pace'],max_bytes=32768)})))
        checker=account_checker_for(self.auth,database)
        def admit():
            admission=checker.check(token);self.assertIs(admission.status,AdmissionStatus.ALLOWED);return admission.principal
        authority=MessageContextAuthority(database.message_repository(self.owner),admit)
        memory=config.bind_readonly(database,self.owner,'alice',admit,message_context=authority)
        observed={};captured={}
        for name,receipt in receipts.items():
            binding=Binding(self.owner,receipt['conversation_id'],receipt['generation'],receipt['message_id'],receipt['run_id'],receipt['sequence'])
            ref={k:receipt[k] for k in ('conversation_id','generation','sequence','message_id','input_sha256')}
            run=memory.capture_history(binding,[ref],decision_source_sha256s=[])
            captured[name]=(binding,run)
            with run.hold(binding) as check:
                check();observed[name]=json.loads(run.payload)['items']
        self.assertEqual([i['text'] for i in observed['formal']],['A steady long-term pace'])
        self.assertEqual([i['text'] for i in observed['none']],['A steady long-term pace'])
        self.assertEqual([i['text'] for i in observed['travel']],['Only this Travel can be fast'])
        bob_scope=scope_for(ISSUER,'bob')
        bob_token=self.headers('bob')['Authorization'][7:]
        def admit_bob():
            admission=checker.check(bob_token);self.assertIs(admission.status,AdmissionStatus.ALLOWED);return admission.principal
        bob_authority=MessageContextAuthority(database.message_repository(bob_scope),admit_bob)
        with self.assertRaises(RuntimeDenied):config.bind_readonly(database,self.owner,'alice',admit,message_context=bob_authority)
        with self.assertRaises(RuntimeDenied):config.bind_readonly(database,self.owner,'alice',admit_bob,message_context=authority)
        with TestClient(create_local_typed_app(conninfo_path=path,auth_dir=self.auth,configuration=typed)) as client:
            disabled=client.post('/v2/memory-management-actions',content=packed(dict(version='MEMORY-management.2',action_id='disable-long',
                operation='pause',item_id='long',expected_version=1,expected_source_version=1)),headers=headers)
            self.assertEqual(disabled.status_code,200,disabled.text)
        original_binding,old=captured['formal']
        with self.assertRaises(RuntimeDenied):
            with old.hold(original_binding):pass
        empty=memory.capture(original_binding)
        self.assertEqual(json.loads(empty.payload)['items'],[])
        travel_binding,_=captured['travel']
        still_current=memory.capture(travel_binding)
        self.assertEqual([i['text'] for i in json.loads(still_current.payload)['items']],['Only this Travel can be fast'])
        with database.connect(self.owner) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM cj_memory_item').fetchone(),(2,))
        with self.assertRaises(RuntimeDenied):run_worker.require_memory_configuration(database,self.owner,config)
        with TestClient(app) as client:
            head=client.put('/v1/conversations',params={'conversation_id':'old-producer-blocked'},headers=headers).json()
            blocked=client.post('/v3/messages',content=packed(dict(version='MESSAGE-send.3',conversation_id='old-producer-blocked',message_id='blocked',
                text='Old producer must remain blocked',trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=0,
                travel_context=None,needs_reference=None,trip_context=dict(id=self.trip_id,expected_version=self.base_version,day=None,item_id=None))),headers=headers)
            self.assertEqual(blocked.status_code,503,blocked.text)
        print('PASS genuine signed formal/Travel/none original refs + real limited PG Memory consumer: formal uses long-term only, actual Travel overrides its own scope, no namespace inference or value mutation; old MESSAGE3/worker Memory guard still denies, new foreground producer integration UNRUN')


if __name__=='__main__':unittest.main(defaultTest='FormalMemoryChecks.test_real_formal_reference_never_selects_unrelated_travel_memory')
