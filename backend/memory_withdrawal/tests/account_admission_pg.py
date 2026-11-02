"""C public factories consume real runtime account retirement before erasure."""
from datetime import datetime,timedelta,timezone
import json,os,sys,tempfile,time
from pathlib import Path
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient
from cj_api.local_app import create_local_app,LocalDatabase,ISSUER,scope_for
from cj_api.local_cleanup import Configuration
from cj_api.local_run_context import load_run_context
from cj_cleanup.core import encode,digest
from cj_memory.typed_api import create_local_typed_app
from cj_memory.typed_local import TypedConfiguration
from cj_trip.confirmation import ConfirmationSigner
from cj_trip.local_manual_app import create_local_manual_app
from cj_trip.local_structured_read import create_local_structured_read_app
from cj_trip.local_needs_app import create_local_needs_app
from cj_trip.local_place_manual import create_local_place_manual_app

ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth,migrate,pg_suites


def exercise(root,path):
    auth=root/'auth';subjects=('retire-alice','retire-bob');dev_auth.init(auth,subjects)
    tokens={who:dev_auth.token(auth,who,30) for who in subjects}
    headers={who:{'Authorization':'Bearer '+token,'Content-Type':'application/octet-stream'} for who,token in tokens.items()}
    now=int(time.time());quota=root/'quota.json'
    quota.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',history=[],current=dict(
        meter=dict(unit='provider_call',budget=10,period_start=now-60,period_end=now+3600,max_steps=10,max_tools=5,max_output=20000,max_seconds=600),
        output_limits=dict(model=3000,tool=3000,memory=3000)))))
    run=load_run_context(quota)
    profile=dict(subjects=['self'],slots={'diet.spicy':dict(kind='preference',collection_allowed=True,semantic_resolved=True)},extents=['long_term'],context_ids=[])
    configuration=TypedConfiguration.from_bytes(encode(dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',
        expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),profiles={who:profile for who in subjects}),
        travel_contexts={who:[] for who in subjects})))
    memory=create_local_typed_app(conninfo_path=path,auth_dir=auth,configuration=configuration)
    signer=ConfirmationSigner(b'synthetic-c-account-retirement-key-only')
    common=dict(conninfo_path=path,auth_dir=auth,run_context=run)
    probes=[(create_local_manual_app(**common,confirmation_signer=signer),'/v3/trip-structured',{'trip_id':'missing'}),
        (create_local_structured_read_app(**common),'/v1/trip-structured-list',{}),
        (create_local_needs_app(**common,confirmation_signer=signer),'/v4/trip-structured',{'trip_id':'missing'}),
        (create_local_place_manual_app(**common,confirmation_signer=signer),'/v2/trip-needs-edits',{'request_id':'missing'})]
    def expect(response,code=200):
        assert response.status_code==code,(response.status_code,response.text)
        return response.json()
    with TestClient(memory) as client:
        for who in subjects:
            raw=encode(dict(version='MEMORY-manual.2',operation_id='save',item_id='saved-item',subject='self',slot='diet.spicy',
                kind='preference',text='Retained canonical '+who,extent='long_term',context=None,occurred_at='date unknown'))
            expect(client.post('/v2/memories',content=raw,headers=headers[who]))
            expect(client.get('/v2/memory-items',params={'item_id':'saved-item'},headers=headers[who]))
        for app,url,params in probes:
            with TestClient(app) as other:
                for who in subjects:expect(other.get(url,params=params,headers=headers[who]))
        # Actual B signature/API component retires the account, but erases only
        # its provided feedback target. C content remains for the gate audit.
        registry=root/'registry.json'
        registry.write_bytes(encode(dict(version='c-retirement-component',stores=[dict(id='business',objects=[
            dict(id='feedback-private-actions',cleanup_protocol='CLEANUP@1.1',objects=['cj_feedback_action','cj_feedback_scope'])])])))
        options=Configuration({'local':b'synthetic-c-retirement-cleanup-key-only'},'local',3600,
            ('business/feedback-private-actions',),registry,clock=time.time)
        gateway=create_local_app(conninfo_path=path,auth_dir=auth,cleanup_configuration=options)
        with TestClient(gateway) as gc:
            def post(url,value):return expect(gc.post(url,content=encode(value),headers=headers['retire-alice']))
            post('/v1/feedback',dict(action_id='feedback',problem='fixture',expectation='',references=[]))
            device=post('/v1/cleanup-devices',dict(version='CLEANUP-DEVICE@1',action_id='device',device_id='local-device',state_ref=digest(b'local-state')))
            prepared=post('/v1/account-cleanup-operations',dict(version='CLEANUP-API@1',action_id='prepare',binding_id=device['binding_id']))
            result=post('/v1/account-cleanup-operations/'+prepared['operation_id']+'/confirmation',dict(version='CLEANUP-API@1',
                registry_digest=prepared['registry_digest'],confirmation='DELETE_ACCOUNT'))
            assert result['business_access']=='revoked' and result['status']!='complete'
        denied=expect(client.get('/v2/memory-items',params={'item_id':'saved-item'},headers=headers['retire-alice']),403)
        assert denied['error']['code']=='ACCESS_DENIED'
        expect(client.get('/v2/memory-items',params={'item_id':'saved-item'},headers=headers['retire-bob']))
        expect(client.post('/v2/memory-management-actions',content=encode(dict(version='MEMORY-management.2',action_id='late',operation='pause',
            item_id='saved-item',expected_version=1,expected_source_version=1)),headers=headers['retire-alice']),403)
        for app,url,params in probes:
            with TestClient(app) as other:
                expect(other.get(url,params=params,headers=headers['retire-alice']),503)
                expect(other.get(url,params=params,headers=headers['retire-bob']))
        with patch.object(LocalDatabase,'connect',side_effect=RuntimeError('synthetic runtime account lookup unavailable')):
            unknown=expect(client.get('/v2/memory-items',params={'item_id':'saved-item'},headers=headers['retire-bob']),503)
            assert unknown['error']['code']=='ACCESS_UNKNOWN'
    # The retired runtime view is intentionally fenced. Inspect physical rows
    # through the task-private initializer for this audit, never the app path.
    with psycopg.connect(**json.loads(path.read_text())) as conn:
        for who in subjects:
            scope=scope_for(ISSUER,who)
            assert conn.execute('SELECT count(*) FROM cj_memory_item WHERE scope=%s',(scope,)).fetchone()==(1,)
            assert conn.execute('SELECT count(*) FROM cj_memory_source WHERE scope=%s',(scope,)).fetchone()==(1,)
    print('PASS actual signed B account retirement before C physical erasure: standalone typed Memory/manual/structured/NEEDS/place readers deny retired token, Bob remains allowed, lookup uncertainty UNKNOWN; canonical C rows intentionally retained, whole cleanup UNRUN')


if __name__=='__main__':
    with patch.dict(os.environ,{'CJ_ENV':'local'}),tempfile.TemporaryDirectory(prefix='c-retirement-') as folder:
        with pg_suites.cluster('c_account_admission',port=55519,role='cj_c_retirement',socket=f'/tmp/cj-c-retire-{os.getpid()}') as config:
            with psycopg.connect(**config,autocommit=True) as conn:
                chain=migrate.load();migrate.up(conn,chain,chain[-1]['version'])
            root=Path(folder);path=root/'conninfo.json';path.write_text(json.dumps(config));path.chmod(0o600)
            exercise(root,path)
