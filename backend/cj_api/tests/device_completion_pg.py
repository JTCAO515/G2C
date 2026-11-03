"""Actual signed API/limited PG completion observation; native erase is not faked."""
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
import json,os,sys,tempfile,time
import psycopg
from fastapi.testclient import TestClient
from cj_api.local_app import create_local_app,LocalDatabase,scope_for
from cj_api.local_cleanup import Configuration,Runtime
from cj_api.local_worker_context import checker_for
from cj_cleanup.core import encode,digest
from cj_cleanup.capabilities import CapabilityUnavailable
from cj_cleanup.postgres import Unavailable

ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth


def exercise(root,path):
    config=json.loads(path.read_text());auth=root/'auth';dev_auth.init(auth,['completion-a','completion-b'])
    tokens={s:dev_auth.token(auth,s,30) for s in ('completion-a','completion-b')};now=[time.time()]
    controls=next(s for s in json.loads((ROOT/'backend/storage-registry.json').read_text())['stores'] if s['id']=='cleanup-control')
    inventory=('device-cache/sdk-session-keychain','business/cleanup-metadata','business/feedback-private-actions')
    registry=root/'registry.json';registry.write_bytes(encode(dict(version='completion-component',stores=[
        dict(id='device-cache',objects=[dict(id='sdk-session-keychain',cleanup_protocol='CLEANUP@1.1')]),
        dict(id='business',objects=[dict(id=name,cleanup_protocol='CLEANUP@1.1') for name in ('cleanup-metadata','feedback-private-actions')]),controls])))
    options=Configuration({'proof':b'explicit-synthetic-completion-key00'},'proof',3600,inventory,registry,
        clock=lambda:now[0],control_records=True)
    app=create_local_app(conninfo_path=path,auth_dir=auth,cleanup_configuration=options)
    runtime=Runtime(LocalDatabase(path),options,scope_for);gateway=runtime.host_gateway(checker_for(auth))
    tables=('cj_cleanup_operation','cj_cleanup_step','cj_cleanup_domain_result','cj_cleanup_request',
        'cj_account_fence','cj_cleanup_device_binding','cj_cleanup_device_call','cj_cleanup_device_action','cj_cleanup_account_gate')
    def snapshot():
        with psycopg.connect(**config) as audit:
            return {table:audit.execute('SELECT to_jsonb(t),xmin::text FROM '+table+' t ORDER BY to_jsonb(t)::text').fetchall() for table in tables}
    with TestClient(app) as client:
        def post(url,value,who='completion-a',scheme='Bearer',credential=None,raw=None):
            response=client.post(url,content=encode(value) if raw is None else raw,
                headers={'Authorization':scheme+' '+(credential or tokens[who]),'Content-Type':'application/octet-stream'})
            assert response.status_code==200,('completion fixture POST',response.status_code,response.text)
            return response.json()
        devices={}
        for key,who in (('initiator','completion-a'),('remote','completion-a'),('bob','completion-b')):
            devices[key]=post('/v3/cleanup-devices',dict(version='CLEANUP-DEVICE@3',action_id='register-'+key,
                device_id='device-'+key,state_ref=digest(key.encode())),who)
        remote=devices['remote'];cap=remote['device_token']
        post('/v1/feedback',dict(action_id='private-feedback',problem='component content to erase',expectation='',references=[]))
        def call(device,action,reason='session_invalid'):
            return post('/v3/cleanup-device-calls',dict(version='CLEANUP-DEVICE@3',action_id=action,
                binding_id=device['binding_id'],reason=reason),scheme='Device',credential=device['device_token'])['invocation']
        standalone=call(remote,'offline-original','offline_expired')
        operation=post('/v1/account-cleanup-operations',dict(version='CLEANUP-API@1',action_id='original-account',binding_id=devices['initiator']['binding_id']))
        post('/v1/account-cleanup-operations/'+operation['operation_id']+'/confirmation',dict(version='CLEANUP-API@1',
            registry_digest=operation['registry_digest'],confirmation='DELETE_ACCOUNT'))
        original={key:call(devices[key],'account-'+key) for key in ('initiator','remote')}
        current=original['remote'];invocation=current['call']['invocation_id'];request=current['request_digest']
        url='/v1/cleanup-device-completions/'+invocation
        def read(status=200,credential=cap,scheme='Device',digest_value=request,target=url):
            response=client.get(target,params={'request_digest':digest_value},headers={'Authorization':scheme+' '+credential})
            assert response.status_code==status,('completion GET',response.status_code,status,response.text)
            return response.json()
        before=snapshot();pending=read();assert snapshot()==before
        assert pending['content_status']=='unknown' and pending['device_state']=='pending'
        assert pending['binding_id']==remote['binding_id']!=operation['binding_id']
        assert pending['operation_id']==operation['operation_id'] and pending['control_record_protocol']=='CLEANUP-CONTROL-RECORDS@1'
        assert pending['business_access']=='not_granted' and 'steps' not in pending and 'devices' not in pending
        for credential in (devices['initiator']['device_token'],devices['bob']['device_token'],operation['progress_token'],current['receipt_token'],cap[:-2]+'xx'):
            read(403,credential=credential)
        read(401,credential=tokens['completion-a'],scheme='Bearer');read(403,digest_value='0'*64)
        missing='/v1/cleanup-device-completions/device-'+('0'*64);read(403,target=missing)
        response=client.get(url,params={'request_digest':request,'operation_id':operation['operation_id']},headers={'Authorization':'Device '+cap})
        assert response.status_code==400
        stale=read(target='/v1/cleanup-device-completions/'+standalone['call']['invocation_id'],digest_value=standalone['request_digest'])
        assert stale['reason']=='offline_expired' and stale['content_status']=='not_applicable' and stale['registry_digest'] is None
        assert stale['operation_id']==standalone['call']['operation_id']!=operation['operation_id']
        receipts={}
        for key in ('initiator','remote'):
            data=original[key];value=dict(version='CLEANUP-DEVICE@3',action_id='report-'+key,operation_id=operation['operation_id'],
                invocation_id=data['call']['invocation_id'],binding_id=devices[key]['binding_id'],request_digest=data['request_digest'],outcome='confirmed')
            raw=encode(value)+b'\n';receipts[key]=digest(raw)
            post('/v3/cleanup-device-receipts',value,scheme='Cleanup',credential=data['receipt_token'],raw=raw)
            if key=='initiator':assert read()['content_status']=='unknown'
        before=snapshot();complete=read();again=read();assert snapshot()==before
        assert complete['content_status']=='complete' and complete['device_state']=='confirmed',complete
        assert complete['receipt_digest']==receipts['remote'] and complete['request_digest']==request
        assert complete['registry_digest']==operation['registry_digest'] and complete['complete_scope']=='frozen_online_domains_only'
        assert {k:v for k,v in complete.items() if k!='request_id'}=={k:v for k,v in again.items() if k!='request_id'}
        assert all(secret not in json.dumps(complete) for secret in (cap,operation['progress_token'],tokens['completion-a']))
        with psycopg.connect(**config) as audit:
            targets=audit.execute('SELECT targets FROM cj_cleanup_operation WHERE subject_digest=%s AND operation_id=%s',
                (remote['scope_digest'],operation['operation_id'])).fetchone()[0]
            audit.execute('UPDATE cj_cleanup_operation SET targets=%s::jsonb WHERE subject_digest=%s AND operation_id=%s',
                (json.dumps([inventory[0]]),remote['scope_digest'],operation['operation_id']))
        read(503)
        with psycopg.connect(**config) as audit:
            audit.execute('UPDATE cj_cleanup_operation SET targets=%s::jsonb WHERE subject_digest=%s AND operation_id=%s',
                (json.dumps(targets),remote['scope_digest'],operation['operation_id']))
        store=runtime.by_subject(remote['scope_digest']).store
        with store.snapshot(operation['operation_id']) as cursor:
            assert cursor.execute('SHOW transaction_read_only').fetchone()==('on',)
            assert cursor.execute('SHOW transaction_isolation').fetchone()==('repeatable read',)
            try:
                with cursor.connection.transaction():cursor.execute('UPDATE cj_cleanup_operation SET blocked=blocked')
            except psycopg.errors.ReadOnlySqlTransaction:pass
            else:raise AssertionError('completion snapshot accepted a mutation')
        # Actual persisted corruption is not a generic complete fallback.
        with psycopg.connect(**config) as audit:
            saved=audit.execute('SELECT invocation_id,request_digest,receipt_bytes FROM cj_cleanup_domain_result WHERE subject_digest=%s AND operation_id=%s AND invocation_id=(SELECT invocation_id FROM cj_cleanup_step WHERE subject_digest=%s AND operation_id=%s AND target=%s)',
                (remote['scope_digest'],operation['operation_id'],remote['scope_digest'],operation['operation_id'],inventory[0])).fetchone()
            audit.execute('DELETE FROM cj_cleanup_domain_result WHERE subject_digest=%s AND operation_id=%s AND invocation_id=%s',(remote['scope_digest'],operation['operation_id'],saved[0]))
        assert read()['content_status']=='unknown'
        with psycopg.connect(**config) as audit:
            audit.execute('INSERT INTO cj_cleanup_domain_result VALUES(%s,%s,%s,%s,%s)',(remote['scope_digest'],operation['operation_id'],*saved))
        assert read()['content_status']=='complete'
        original_registry=registry.read_bytes()
        def changed(value):registry.write_bytes(original_registry+b'\n');return encode(value)
        try:
            try:gateway.device_completion(cap,invocation,request,changed)
            except Unavailable:pass
            else:raise AssertionError('projection-time registry drift leaked complete')
        finally:registry.write_bytes(original_registry)
        base_time=now[0]
        def expire(value):now[0]+=3601;return encode(value)
        try:
            try:gateway.device_completion(cap,invocation,request,expire)
            except CapabilityUnavailable:pass
            else:raise AssertionError('projection-time expiry leaked complete')
            read(403)
        finally:now[0]=base_time
        def close_connection(action):
            class Connection(psycopg.Connection):
                def close(self):
                    active=not self.closed
                    super().close()
                    if active:action()
            return lambda:Connection.connect(**dict(config,user='cj_local_cleanup'))
        try:
            with patch.object(runtime,'connect',close_connection(lambda:now.__setitem__(0,base_time+3601))):
                try:gateway.device_completion(cap,invocation,request,encode)
                except CapabilityUnavailable:pass
                else:raise AssertionError('close-time expiry leaked complete')
        finally:now[0]=base_time
        try:
            with patch.object(runtime,'connect',close_connection(lambda:registry.write_bytes(original_registry+b'\n'))):
                try:gateway.device_completion(cap,invocation,request,encode)
                except Unavailable:pass
                else:raise AssertionError('close-time registry drift leaked complete')
        finally:registry.write_bytes(original_registry)
        wrong=Runtime(LocalDatabase(path),replace(options,keys={'proof':b'other-explicit-synthetic-key-0000'}),scope_for).host_gateway(checker_for(auth))
        try:wrong.device_completion(cap,invocation,request,encode)
        except CapabilityUnavailable:pass
        else:raise AssertionError('wrong key accepted completion credential')
        assert client.get('/v1/account-cleanup-operations/'+operation['operation_id'],headers={'Authorization':'Device '+cap}).status_code==401
    print('PASS actual remote V3 original-call completion API, no initiating progress credential, 3 explicit component content targets/5 registered controls, real feedback erasure/atomic domain results/readonly repeatable snapshot and zero GET mutations; wrong owner/binding/purpose/hash/key/expiry/registry/corruption refuse; standalone original is sticky. Native control erasure/whole-App/backup UNRUN')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='device-completion-') as folder:exercise(Path(folder),Path(os.environ['CJ_E2E_CONNINFO']))
