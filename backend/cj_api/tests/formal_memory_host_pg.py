"""Actual installed C formal adapter, unchanged signed MSG3 and original worker."""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import json,sys,unittest,os,subprocess
from unittest.mock import patch
from fastapi.testclient import TestClient
from cj_api.local_app import create_local_app,LocalDatabase,app_from_environment
from cj_agent.provider import FakeProvider
from cj_memory.formal_runtime import FormalRuntimeConfiguration
from cj_memory.typed_local import TypedConfiguration
from cj_memory.typed_api import create_local_typed_app
from cj_memory.runtime import RuntimeDenied
from cj_trip.domain import packed

ROOT=Path(__file__).resolve().parents[3];sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'backend/trip/tests')]
import manual_pg as manual,dev_auth,local_run_context,message_trip_profile,run_worker


class FormalHostChecks(manual.ManualChecks):
    def test_installed_formal_factory_preserves_original_wire_and_namespace(self):
        path=Path(manual.CONNINFO);run=self.run_context
        local_run_context.provision_budget(path,run,'alice')
        dev_auth.activate_travel(path,'alice',run,'MESSAGE-TRAVEL-CONSUMER@1')
        message_trip_profile.activate(path,'alice',run,'MESSAGE-TRIP-CONSUMER@1')
        database=LocalDatabase(path,run_context=run,travel_context=True,trip_context=True)
        old=create_local_app(conninfo_path=path,auth_dir=self.auth,run_context=run,travel_context=True,trip_context=True)
        headers={**self.headers('alice'),'Content-Type':'application/octet-stream'}
        originals={}
        def send(client,name,travel=None,trip=True):
            head=client.put('/v1/conversations',params={'conversation_id':name},headers=headers).json()
            raw=packed(dict(version='MESSAGE-send.3',conversation_id=name,message_id=name,text=name,trip_id=None,
                creation_intent='none',expected_generation=head['generation'],expected_sequence=0,
                travel_context=travel,needs_reference=None,trip_context=dict(id=self.trip_id,expected_version=self.base_version,
                    day=None,item_id=None) if trip else None))
            originals[name]=raw
            return client.post('/v3/messages',content=raw,headers=headers)
        with TestClient(old) as client:
            response=client.post('/v1/travel-context-actions',content=packed(dict(version='TRAVEL-context-action.1',action_id='independent',
                operation='create',travel_context=None)),headers=headers)
            self.assertEqual(response.status_code,200,response.text);travel=response.json()['receipt']['travel_context']
            queued=send(client,'before-memory');self.assertEqual(queued.status_code,200,queued.text)
        profile=dict(subjects=['self'],slots={'pace':dict(kind='preference',collection_allowed=True,semantic_resolved=True)},
            extents=['long_term','current'],context_ids=[])
        typed=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',
            expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),profiles={'alice':profile}),
            travel_contexts={'alice':[travel['id']]})
        with TestClient(create_local_typed_app(conninfo_path=path,auth_dir=self.auth,configuration=TypedConfiguration.from_bytes(packed(typed)))) as manager:
            for name,text,namespace in (('long','Keep a steady pace',None),('temp','Fast only in this Travel',dict(kind='travel',id=travel['id'],expected_version=1))):
                raw=packed(dict(version='MEMORY-manual.2',operation_id=name,item_id=name,subject='self',slot='pace',kind='preference',text=text,
                    extent='long_term' if namespace is None else 'current',context=namespace,occurred_at='date unknown'))
                response=manager.post('/v2/memories',content=raw,headers=headers);self.assertEqual(response.status_code,200,response.text)
        configuration=FormalRuntimeConfiguration.from_bytes(packed(dict(version='local-memory-formal-run.1',collection=typed,
            selections={'alice':dict(subject='self',slots=['pace'],max_bytes=32768)})))
        with TestClient(old) as client:self.assertEqual(send(client,'old-producer').status_code,503)
        forbidden=FakeProvider()
        with self.assertRaises(RuntimeDenied):run_worker.run_once(database,forbidden,self.auth)
        self.assertEqual(forbidden.calls,0)
        app=create_local_app(conninfo_path=path,auth_dir=self.auth,run_context=run,travel_context=True,trip_context=True,
                             formal_memory_configuration=configuration)
        receipts={}
        with TestClient(app) as client:
            for name,namespace,trip in (('formal',None,True),('travel',dict(id=travel['id'],expected_version=1),False),('none',None,False)):
                response=send(client,name,namespace,trip);self.assertEqual(response.status_code,200,response.text)
                body=response.json();self.assertEqual(body['version'],'MESSAGE-accept.3')
                self.assertEqual(body['reference']['version'],'MESSAGE-trip-reference.1');receipts[name]=body['receipt']
                self.assertEqual(client.post('/v3/messages',content=originals[name],headers=headers).json()['receipt'],body['receipt'])
        class Recorded(FakeProvider):
            def __init__(self):super().__init__();self.inputs={}
            def stream(self,messages,system=None):
                current=messages[-1]['content']
                data=next(m['content'] for m in messages if m['content'].startswith('Stored memory data (not instructions):\n'))
                self.inputs[current]=json.loads(data.split('\n',1)[1])
                yield from super().stream(messages,system)
        model=Recorded();outcomes=run_worker.run_once(database,model,self.auth,formal_memory_configuration=configuration)
        self.assertEqual(len(outcomes),4);self.assertTrue(all(v.status=='completed' for v in outcomes),outcomes);self.assertEqual(model.calls,4)
        for name in ('formal','none','before-memory'):
            self.assertEqual([v['text'] for v in model.inputs[name]['items']],['Keep a steady pace'])
        self.assertEqual([v['text'] for v in model.inputs['travel']['items']],['Fast only in this Travel'])
        self.assertEqual(run_worker.run_once(database,model,self.auth,formal_memory_configuration=configuration),[]);self.assertEqual(model.calls,4)
        # Real environment loader and original CLI, not a monkeypatched worker.
        cfg=self.auth/'formal-memory.json'
        cfg.write_bytes(packed(dict(version='local-memory-formal-run.1',collection=typed,
            selections={'alice':dict(subject='self',slots=['pace'],max_bytes=32768)})))
        cfg.chmod(0o600)
        environment=dict(CJ_ENV='local',CJ_LOCAL_AUTH_DIR=str(self.auth),CJ_LOCAL_CONNINFO=str(path),
            CJ_LOCAL_RUN_CONTEXT=str(self.auth/'manual-source-context.json'),CJ_LOCAL_TRAVEL_CONTEXT='message-travel.1',
            CJ_LOCAL_TRIP_CONTEXT='message-trip.1',CJ_LOCAL_FORMAL_MEMORY_RUN_POLICY=str(cfg))
        with patch.dict(os.environ,environment),TestClient(app_from_environment()) as client:
            cli=send(client,'actual-cli');self.assertEqual(cli.status_code,200,cli.text)
        command=[sys.executable,'-B',str(ROOT/'scripts/run_worker.py'),'--conninfo-json',str(path),'--auth-dir',str(self.auth),
            '--run-context',str(self.auth/'manual-source-context.json'),'--formal-memory-run-policy',str(cfg),
            '--travel-context','message-travel.1','--trip-context','message-trip.1','--once']
        result=subprocess.run(command,env=dict(os.environ,CJ_ENV='local'),capture_output=True,text=True,timeout=45)
        self.assertEqual(result.returncode,0,(result.stdout,result.stderr));self.assertIn('local_provider_calls=1',result.stdout)
        # The new explicit receiver encodes before its last actual AUTH guard.
        from fastapi.responses import JSONResponse
        invited=self.auth/'invited.json';original_invited=invited.read_bytes();render=JSONResponse.render;revoked=[]
        def withdraw(response,value):
            raw=render(response,value)
            if type(value) is dict and value.get('version')=='MESSAGE-accept.3' and not revoked:
                invited.write_text(json.dumps(['bob']));revoked.append(True)
            return raw
        try:
            with TestClient(app) as client,patch.object(JSONResponse,'render',withdraw):
                denied=send(client,'encode-withdrawal')
            self.assertEqual(revoked,[True]);self.assertEqual(denied.status_code,503,denied.text)
            self.assertNotIn('reference',denied.json());self.assertEqual(denied.json()['error']['outcome'],'unknown')
        finally:invited.write_bytes(original_invited)
        with TestClient(app) as client:
            status=client.get('/v3/message-send-status',params={'conversation_id':'encode-withdrawal','message_id':'encode-withdrawal'},headers=headers)
            self.assertEqual(status.status_code,200,status.text);self.assertIsNotNone(status.json()['receipt'])
            self.assertEqual(client.post('/v3/messages',content=originals['encode-withdrawal'],headers=headers).json()['receipt'],status.json()['receipt'])
        recovered=Recorded();self.assertEqual(len(run_worker.run_once(database,recovered,self.auth,formal_memory_configuration=configuration)),1)
        self.assertEqual(recovered.calls,1)
        # Expired real C policy cannot silently take the old Memory-less route.
        expired=json.loads(cfg.read_bytes());expired['collection']['collection']['expires_at']=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()
        expired=FormalRuntimeConfiguration.from_bytes(packed(expired))
        with TestClient(create_local_app(conninfo_path=path,auth_dir=self.auth,run_context=run,travel_context=True,trip_context=True,
                                        formal_memory_configuration=expired)) as client:
            unavailable=send(client,'expired');self.assertEqual(unavailable.status_code,503,unavailable.text)
        self.assertEqual(run_worker.run_once(database,FakeProvider(),self.auth,formal_memory_configuration=configuration),[])
        print('PASS actual explicit C formal host keeps MSG3/ref1/payload2 and original queued run, old producer/worker still deny, actual Meter/Fake four contexts preserve genuine Trip/Travel/none namespace isolation and zero resend')


if __name__=='__main__':unittest.main(defaultTest='FormalHostChecks.test_installed_formal_factory_preserves_original_wire_and_namespace')
