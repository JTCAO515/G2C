"""Actual signed device V2 transport; native file erasure remains A's evidence."""
import json,os,sys,tempfile,time
from pathlib import Path
import psycopg
from fastapi.testclient import TestClient
from cj_api.local_app import create_local_app
from cj_api.local_cleanup import Configuration
from cj_cleanup.core import encode,digest
from cj_cleanup.device_bridge import TARGETS as V1_TARGETS
from cj_cleanup.device_v2 import TARGETS,VERSION
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth,migrate


def exercise(root,conninfo):
    auth=root/'auth';dev_auth.init(auth,['device-owner','device-other','legacy-down'])
    tokens={s:dev_auth.token(auth,s,30) for s in ('device-owner','device-other','legacy-down')}
    inventory=('business/feedback-private-actions','business/cleanup-metadata',*TARGETS)
    raw=encode(dict(version='device-v2-transport-component',stores=[dict(id='business',objects=[
        dict(id='feedback-private-actions',cleanup_protocol='CLEANUP@1.1'),dict(id='cleanup-metadata',cleanup_protocol='CLEANUP@1.1')]),
        dict(id='device-cache',objects=[dict(id=t.split('/')[1],cleanup_protocol='CLEANUP@1.1') for t in TARGETS])]))
    registry=root/'registry.json';registry.write_bytes(raw)
    config=Configuration({'device-v2':b'explicit-synthetic-v2-device-key-0'},'device-v2',3600,inventory,registry,clock=time.time)
    app=create_local_app(conninfo_path=conninfo,auth_dir=auth,cleanup_configuration=config)
    with TestClient(app) as client:
        def expect(response,status=200):
            assert response.status_code==status,('device bridge HTTP status',response.status_code,status)
            return response.json()
        def post(path,value,*,scheme='Bearer',credential=tokens['device-owner'],status=200):
            return expect(client.post(path,content=encode(value),headers={'Authorization':scheme+' '+credential,'Content-Type':'application/octet-stream'}),status)
        def query(path,scheme,credential):return expect(client.get(path,headers={'Authorization':scheme+' '+credential}))
        # V1 is the inherited schema, not new V2 data. Dropping a constant-V1
        # protocol column must preserve every legacy byte, including lost ACKs.
        legacy=post('/v1/cleanup-devices',dict(version='CLEANUP-DEVICE@1',action_id='legacy-register',device_id='legacy',state_ref=digest(b'legacy-state')),
                    credential=tokens['legacy-down'])
        legacy_call=post('/v1/cleanup-device-calls',dict(version='CLEANUP-DEVICE@1',binding_id=legacy['binding_id'],reason='offline_expired'),
                         scheme='Device',credential=legacy['device_token'])
        options=json.loads(conninfo.read_text())
        def inherited(conn):
            return (conn.execute('SELECT binding_id,subject_digest,action_id,input_digest,device_id,state_ref,scope_digest,created_at FROM cj_cleanup_device_binding ORDER BY binding_id').fetchall(),
                    conn.execute('SELECT * FROM cj_cleanup_device_call ORDER BY invocation_id').fetchall())
        with psycopg.connect(**options,autocommit=True) as conn:
            before=inherited(conn);assert before[0] and before[1]
            migrate.down(conn,migrate.load(),37)
            assert inherited(conn)==before
            migrate.up(conn,migrate.load(),38)
            assert inherited(conn)==before
            assert conn.execute('SELECT DISTINCT protocol FROM cj_cleanup_device_binding').fetchall()==[('CLEANUP-DEVICE@1',)]
        assert query('/v1/cleanup-device-calls/'+legacy_call['call']['invocation_id'],'Device',legacy['device_token'])['call']==legacy_call['call']
        old,new=[],[]
        for index in range(2):
            body=dict(action_id='register-v1-'+str(index),device_id='device-'+str(index),state_ref=digest(('state-'+str(index)).encode()))
            original=post('/v1/cleanup-devices',dict(version='CLEANUP-DEVICE@1',**body));old.append(original)
            post('/v1/cleanup-devices',dict(version=VERSION,**body),status=400)
            post('/v2/cleanup-devices',dict(version=VERSION,**body),status=409)
            upgraded=post('/v2/cleanup-devices',dict(version=VERSION,**(body|dict(action_id='register-v2-'+str(index)))));new.append(upgraded)
            assert upgraded['version']==VERSION and upgraded['binding_id']!=original['binding_id']
            assert post('/v2/cleanup-devices',dict(version=VERSION,**(body|dict(action_id='register-v2-'+str(index)))))['binding_id']==upgraded['binding_id']
            assert post('/v1/cleanup-devices',dict(version='CLEANUP-DEVICE@1',**body))['binding_id']==original['binding_id']
        for prefix,version,device in (('/v2',VERSION,old[0]),('/v1','CLEANUP-DEVICE@1',new[0])):
            post(prefix+'/cleanup-device-calls',dict(version=version,binding_id=device['binding_id'],reason='session_invalid'),
                 scheme='Device',credential=device['device_token'],status=403)
        post('/v2/cleanup-device-calls',dict(version=VERSION,binding_id=new[0]['binding_id'],reason='session_invalid',targets=['untrusted']),
             scheme='Device',credential=new[0]['device_token'],status=400)
        post('/v1/feedback',dict(action_id='original-feedback',problem='private original',expectation='',references=[]))
        prepared=post('/v1/account-cleanup-operations',dict(version='CLEANUP-API@1',action_id='original-account',binding_id=new[0]['binding_id']))
        operation=prepared['operation_id'];url='/v1/account-cleanup-operations/'+operation
        waiting=post(url+'/confirmation',dict(version='CLEANUP-API@1',registry_digest=prepared['registry_digest'],confirmation='DELETE_ACCOUNT'))
        assert waiting['status']!='complete' and waiting['online_status']=='unknown'
        calls=[]
        def call(device,prefix,version):
            return post(prefix+'/cleanup-device-calls',dict(version=version,binding_id=device['binding_id'],reason='session_invalid'),
                        scheme='Device',credential=device['device_token'])
        def report(value,prefix,version,action,outcome='confirmed',status=200):
            c=value['call']
            return post(prefix+'/cleanup-device-receipts',dict(version=version,action_id=action,operation_id=c['operation_id'],
                invocation_id=c['invocation_id'],binding_id=c['binding_id'],request_digest=value['request_digest'],outcome=outcome),
                scheme='Cleanup',credential=value['receipt_token'],status=status)
        for index,device in enumerate(old):
            value=call(device,'/v1','CLEANUP-DEVICE@1');calls.append(value)
            assert value['call']['version']=='CLEANUP-DEVICE@1' and value['call']['targets']==list(V1_TARGETS)
            report(value,'/v1','CLEANUP-DEVICE@1','old-report-'+str(index))
        observed=query(url,'Cleanup',prepared['progress_token'])
        additions=set(TARGETS)-set(V1_TARGETS)
        assert all(s['state']!='confirmed' for s in observed['steps'] if s['target'] in additions)
        assert observed['online_status']!='complete'
        first=call(new[0],'/v2',VERSION)
        assert first['call']['version']==VERSION and first['call']['targets']==list(TARGETS) and len(TARGETS)==13
        post('/v2/cleanup-device-receipts',dict(version=VERSION,action_id='wrong-request',operation_id=operation,
            invocation_id=first['call']['invocation_id'],binding_id=new[0]['binding_id'],request_digest='0'*64,outcome='confirmed'),
            scheme='Cleanup',credential=first['receipt_token'],status=403)
        report(first,'/v2',VERSION,'v2-report-first')
        assert query(url,'Cleanup',prepared['progress_token'])['online_status']!='complete'
        second=call(new[1],'/v2',VERSION)
        report(second,'/v2',VERSION,'v2-pending-second',outcome='unknown')
        original=query('/v2/cleanup-device-calls/'+second['call']['invocation_id'],'Device',new[1]['device_token'])
        assert original['state']=='unknown' and original['request_digest']==second['request_digest']
        assert call(new[1],'/v2',VERSION)['call']['invocation_id']==second['call']['invocation_id']
        accepted=report(second,'/v2',VERSION,'v2-final-second')
        assert report(second,'/v2',VERSION,'v2-final-second')['receipt_digest']==accepted['receipt_digest']
        report(second,'/v2',VERSION,'v2-final-second',outcome='failed',status=409)
        complete=query(url,'Cleanup',prepared['progress_token'])
        assert complete['online_status']=='complete' and complete['status']!='complete'
        assert all(s['state']=='confirmed' for s in complete['steps'])
        for index,value in enumerate(calls):
            replay=query('/v1/cleanup-device-calls/'+value['call']['invocation_id'],'Device',old[index]['device_token'])
            assert replay['request_digest']==value['request_digest'] and replay['call']==value['call']
        other=post('/v2/cleanup-devices',dict(version=VERSION,action_id='other-register',device_id='other',state_ref=digest(b'other-state')),credential=tokens['device-other'])
        offline=post('/v2/cleanup-device-calls',dict(version=VERSION,binding_id=other['binding_id'],reason='offline_expired'),scheme='Device',credential=other['device_token'])
        assert offline['call']['targets']==['device-cache/offline-trip']
        with psycopg.connect(**json.loads(conninfo.read_text())) as conn:
            assert conn.execute('SELECT plan_bytes FROM cj_cleanup_request WHERE operation_id=%s',(operation,)).fetchone()==(None,)
            retained=conn.execute('SELECT binding_id,protocol FROM cj_cleanup_device_binding ORDER BY binding_id').fetchall()
        try:
            with psycopg.connect(**json.loads(conninfo.read_text()),autocommit=True) as conn:migrate.down(conn,migrate.load(),37)
        except psycopg.errors.RaiseException as error:
            assert 'device bridge contains original binding/call evidence' in str(error)
        else:raise AssertionError('M38 down discarded original device version/state')
        with psycopg.connect(**json.loads(conninfo.read_text())) as conn:
            assert conn.execute('SELECT binding_id,protocol FROM cj_cleanup_device_binding ORDER BY binding_id').fetchall()==retained
        print('PASS actual V2 version enrollment/original bytes, inherited V1 data down/up unchanged, V2 data down refusal, cross-version/extra-target denial, V1 cannot confirm new targets, same-device/state reports and other-device pending, UNKNOWN original report recovery, final metadata redaction; native erasure UNRUN')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='g2c-device-v2-') as temp:exercise(Path(temp),Path(os.environ['CJ_E2E_CONNINFO']))
