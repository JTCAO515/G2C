"""Signed DEVICE4 originals, actual scoped PG and provided-journal coverage.

Authenticated synthetic reports test the bridge, never native erasure.
"""
from pathlib import Path
from unittest.mock import patch
import json,os,sys,tempfile
import psycopg
from fastapi.testclient import TestClient
from cj_api.local_app import create_local_app,LocalDatabase,scope_for,ISSUER
from cj_api.local_cleanup import Configuration,Runtime
from cj_cleanup.core import encode,digest
from cj_cleanup.device_v4 import VERSION,TARGETS
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth,migrate


def exercise(root,path):
    config=json.loads(path.read_text());auth=root/'auth';dev_auth.init(auth,['four-a','four-b'])
    tokens={who:dev_auth.token(auth,who,30) for who in ('four-a','four-b')}
    with psycopg.connect(**config,autocommit=True) as audit:
        migrate.down(audit,migrate.load(),46);migrate.up(audit,migrate.load(),47)
    actual=json.loads((ROOT/'backend/storage-registry.json').read_bytes())
    provided=next(s for s in actual['stores'] if s['id']=='device-cache')
    assert tuple('device-cache/'+o['id'] for o in provided['objects'])==TARGETS
    assert len(TARGETS)==20 and len(set(TARGETS))==20
    family=next(o for o in provided['objects'] if o['id']=='memory-erasure-pending')
    assert 'M.erasure-v1 AND M.erasure-v1.CJMemoryErasureObservationsV1' in family['principal_binding']
    assert len(family['objects'])==2 and 'device-cache/memory-erasure-observations' not in TARGETS
    registry=root/'registry.json';inventory=TARGETS+('business/feedback-private-actions','business/cleanup-metadata')
    registry.write_bytes(encode(dict(version='device4-component',stores=[provided,
        dict(id='business',objects=[dict(id=n,cleanup_protocol='CLEANUP@1.1') for n in ('feedback-private-actions','cleanup-metadata')]),
        next(s for s in actual['stores'] if s['id']=='cleanup-control')])))
    options=Configuration({'four':b'explicit-synthetic-device4-key-000'},'four',3600,inventory,registry,control_records=True)
    app=create_local_app(conninfo_path=path,auth_dir=auth,cleanup_configuration=options)
    def snapshot():
        with psycopg.connect(**config) as c:
            return {t:c.execute('SELECT to_jsonb(t),xmin::text FROM '+t+' t ORDER BY to_jsonb(t)::text').fetchall()
                for t in ('cj_cleanup_device_binding','cj_cleanup_device_action','cj_cleanup_device_call','cj_cleanup_operation','cj_cleanup_step')}
    with TestClient(app) as client:
        def request(method,url,value=None,*,who='four-a',scheme='Bearer',credential=None,status=200,params=None,raw=None):
            headers={'Authorization':scheme+' '+(tokens[who] if credential is None else credential)}
            if method=='POST':headers['Content-Type']='application/octet-stream'
            r=client.request(method,url,content=(encode(value) if raw is None else raw) if method=='POST' else None,params=params,headers=headers)
            assert r.status_code==status,(method,url,r.status_code,status,r.text)
            return r.json()
        def register(action,who='four-a',version=VERSION):
            prefix='/v4' if version==VERSION else '/v3'
            return request('POST',prefix+'/cleanup-devices',dict(version=version,action_id=action,device_id='device-'+action,state_ref=digest(action.encode())),who=who)
        a=register('a');foreign=register('b','four-b');legacy=register('legacy','four-b','CLEANUP-DEVICE@3')
        for device,prefix,version in ((a,'/v4',VERSION),(legacy,'/v3','CLEANUP-DEVICE@3')):
            params=dict(action_id='a' if device is a else 'legacy',input_sha256=digest(encode(dict(version=version,action_id='a' if device is a else 'legacy',device_id='device-a' if device is a else 'device-legacy',state_ref=digest(b'a' if device is a else b'legacy')))))
            before=snapshot();got=request('GET',prefix+'/cleanup-device-registrations',params=params,who='four-a' if device is a else 'four-b')
            assert got['registration']['binding_id']==device['binding_id'] and snapshot()==before
        request('GET','/v3/cleanup-device-registrations',params=dict(action_id='a',input_sha256='0'*64),status=403)
        request('GET','/v4/cleanup-device-registrations',params=dict(action_id='a',input_sha256='0'*64),status=409)
        def call(device,action,reason='session_invalid',status=200):
            return request('POST','/v4/cleanup-device-calls',dict(version=VERSION,action_id=action,binding_id=device['binding_id'],reason=reason),scheme='Device',credential=device['device_token'],status=status)
        standalone=call(a,'expiry','offline_expired')['invocation']
        assert standalone['call']['targets']==['device-cache/offline-trip','device-cache/offline-write-residue','device-cache/offline-key-keychain']
        call(legacy,'wrong-version',status=403)
        # Real committed registration with a lost physical close ACK. Original
        # GET recovers the stored action; no second POST is issued.
        class CloseLost(psycopg.Connection):
            def close(self):
                live=not self.closed;super().close()
                if live:raise OSError('synthetic committed original close ACK lost')
        data=dict(version=VERSION,action_id='ack',device_id='device-ack',state_ref=digest(b'ack'))
        with patch.object(Runtime,'connect',lambda runtime:CloseLost.connect(**dict(config,user='cj_local_cleanup'))):
            request('POST','/v4/cleanup-devices',data,status=503)
        params=dict(action_id='ack',input_sha256=digest(encode(data)))
        before=snapshot();ack=request('GET','/v4/cleanup-device-registrations',params=params)['registration'];assert snapshot()==before
        assert ack['version']==VERSION
        for who in ('four-a','four-b'):
            request('POST','/v1/feedback',dict(action_id='private',problem='private component',expectation='',references=[]),who=who)
        operation=request('POST','/v1/account-cleanup-operations',dict(version='CLEANUP-API@1',action_id='account',binding_id=a['binding_id']))
        request('POST','/v1/account-cleanup-operations/'+operation['operation_id']+'/confirmation',dict(version='CLEANUP-API@1',registry_digest=operation['registry_digest'],confirmation='DELETE_ACCOUNT'))
        request('POST','/v1/feedback',dict(action_id='late',problem='late',expectation='',references=[]),status=503)
        request('POST','/v4/cleanup-devices',data|dict(action_id='late-registration'),status=403)
        with psycopg.connect(**config) as audit:
            assert audit.execute("SELECT action_id FROM cj_feedback_action WHERE action_id='late'").fetchall()==[]
        current=call(a,'retired')['invocation'];other=call(ack,'retired-ack')['invocation']
        assert current['call']['operation_id']==operation['operation_id'] and current['call']['targets']==list(TARGETS)
        action=dict(action_id='retired',input_sha256=digest(encode(dict(version=VERSION,action_id='retired',binding_id=a['binding_id'],reason='session_invalid'))))
        before=snapshot();recovered=request('GET','/v4/cleanup-device-call-actions',params=action,scheme='Device',credential=a['device_token']);assert snapshot()==before
        assert recovered['invocation']['request_digest']==current['request_digest']
        request('GET','/v3/cleanup-device-call-actions',params=action,scheme='Device',credential=a['device_token'],status=403)
        request('GET','/v4/cleanup-device-call-actions',params=action,scheme='Device',credential=ack['device_token'],status=403)
        assert request('GET','/v4/cleanup-device-call-actions',params=action,scheme='Device',credential=foreign['device_token'])['invocation'] is None
        def completion(data,device=a,status=200,prefix='/v2'):
            return request('GET',prefix+'/cleanup-device-completions/'+data['call']['invocation_id'],params=dict(request_digest=data['request_digest']),scheme='Device',credential=device['device_token'],status=status)
        assert completion(current)['content_status']=='unknown'
        completion(current,prefix='/v1',status=403);completion(current,device=foreign,status=403)
        assert completion(standalone,prefix='/v2')['content_status']=='not_applicable'
        def report(data,device,version=VERSION,prefix='/v4'):
            receipt=dict(version=version,action_id='report-'+device['binding_id'],operation_id=data['call']['operation_id'],invocation_id=data['call']['invocation_id'],binding_id=device['binding_id'],request_digest=data['request_digest'],outcome='confirmed')
            return request('POST',prefix+'/cleanup-device-receipts',receipt,scheme='Cleanup',credential=data['receipt_token'])
        report(current,a);assert completion(current)['content_status']=='unknown'
        report(other,ack);before=snapshot();done=completion(current);assert snapshot()==before
        assert done['version']=='CLEANUP-DEVICE-COMPLETION@2' and done['content_status']=='complete' and done['device_state']=='confirmed'
        # Bob's V4 group cannot cover his separate V3-only device/state group.
        bob=request('POST','/v1/account-cleanup-operations',dict(version='CLEANUP-API@1',action_id='bob-account',binding_id=foreign['binding_id']),who='four-b')
        request('POST','/v1/account-cleanup-operations/'+bob['operation_id']+'/confirmation',dict(version='CLEANUP-API@1',registry_digest=bob['registry_digest'],confirmation='DELETE_ACCOUNT'),who='four-b')
        bcall=call(foreign,'bob')['invocation'];report(bcall,foreign)
        old=request('POST','/v3/cleanup-device-calls',dict(version='CLEANUP-DEVICE@3',action_id='legacy-report',binding_id=legacy['binding_id'],reason='session_invalid'),scheme='Device',credential=legacy['device_token'])['invocation']
        report(old,legacy,'CLEANUP-DEVICE@3','/v3')
        assert completion(bcall,device=foreign)['content_status']=='unknown'
        with psycopg.connect(**dict(config,user='cj_local_cleanup')) as c:
            c.execute("SELECT set_config('cj.cleanup_subject',%s,true)",(foreign['scope_digest'],))
            assert c.execute('SELECT binding_id FROM cj_cleanup_device_binding WHERE binding_id=%s',(a['binding_id'],)).fetchall()==[]
        try:
            with psycopg.connect(**dict(config,user='cj_local_cleanup')) as c:
                c.execute("SELECT set_config('cj.cleanup_subject',%s,true)",(foreign['scope_digest'],))
                c.execute('INSERT INTO cj_cleanup_device_binding(subject_digest,binding_id,action_id,input_digest,device_id,state_ref,scope_digest,protocol) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',
                    (a['scope_digest'],'cross-binding','cross-action','0'*64,'cross-device','0'*64,a['scope_digest'],VERSION))
        except psycopg.errors.InsufficientPrivilege:pass
        else:raise AssertionError('private role crossed original owner on write')
        with psycopg.connect(**config) as c:
            assert c.execute("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname='cj_m1_runtime'").fetchone()==(False,False)
            assert c.execute("SELECT has_table_privilege('cj_m1_runtime','cj_cleanup_device_binding','DELETE'),has_table_privilege('cj_m1_runtime','cj_cleanup_device_binding','TRUNCATE'),pg_has_role('cj_m1_runtime','cj_local_cleanup','MEMBER')").fetchone()==(False,False,False)
        try:
            with LocalDatabase(path).connect(scope_for(ISSUER,'four-a')) as c:c.execute('SELECT * FROM cj_cleanup_device_binding')
        except psycopg.errors.InsufficientPrivilege:pass
        else:raise AssertionError('runtime obtained private cleanup metadata')
        try:
            with psycopg.connect(**config,autocommit=True) as c:migrate.down(c,migrate.load(),46)
        except psycopg.errors.RaiseException as e:assert 'original V4 device evidence retained' in str(e)
        else:raise AssertionError('V4 evidence rollback was destructive')
    print('PASS DEVICE4 signed originals/close-ACK recovery/20-target bridge/current account retirement/COMPLETION2 exact original read-only proof; V3-only device cannot cover added roots; M47 empty roundtrip and populated refusal; native physical erasure UNRUN')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='device4-') as folder:exercise(Path(folder),Path(os.environ['CJ_E2E_CONNINFO']))
