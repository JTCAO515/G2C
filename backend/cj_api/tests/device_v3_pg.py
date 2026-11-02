"""Actual first registration/call ACK loss and read-only original V3 recovery."""
from pathlib import Path
from unittest.mock import patch
import json,os,sys,tempfile,time
import psycopg
from fastapi.testclient import TestClient
from cj_api.local_app import create_local_app,LocalDatabase,scope_for,ISSUER
from cj_api.local_cleanup import Configuration,Runtime
from cj_cleanup.core import encode,digest
from cj_cleanup.device_v3 import VERSION,TARGETS
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth,migrate


def exercise(root,path):
    config=json.loads(path.read_text());auth=root/'auth';dev_auth.init(auth,['ack-a','ack-b'])
    tokens={who:dev_auth.token(auth,who,30) for who in ('ack-a','ack-b')}
    registry=root/'registry.json';target='business/feedback-private-actions'
    registry.write_bytes(encode(dict(version='device-ack-component',stores=[dict(id='business',objects=[dict(id='feedback-private-actions',cleanup_protocol='CLEANUP@1.1')])])))
    options=Configuration({'v3-test':b'explicit-device-v3-synthetic-key-0'},'v3-test',3600,(target,),registry)
    app=create_local_app(conninfo_path=path,auth_dir=auth,cleanup_configuration=options)
    real_connect=Runtime.connect
    def lost_ack(prefix):
        armed={'remaining':1}
        class Cursor:
            def __init__(self,raw,connection):self.raw,self.connection=raw,connection
            def __enter__(self):
                self.raw.__enter__()
                return self
            def __exit__(self,*args):return self.raw.__exit__(*args)
            def execute(self,sql,args=None):
                self.raw.execute(sql,args)
                if sql.startswith(prefix):self.connection.lost=True
                return self
            def fetchone(self):return self.raw.fetchone()
            def fetchall(self):return self.raw.fetchall()
            @property
            def rowcount(self):return self.raw.rowcount
            def close(self):return self.raw.close()
        class Connection:
            def __init__(self,raw):self.raw,self.lost=raw,False
            @property
            def autocommit(self):return self.raw.autocommit
            @property
            def info(self):return self.raw.info
            def cursor(self):return Cursor(self.raw.cursor(),self)
            def rollback(self):return self.raw.rollback()
            def close(self):return self.raw.close()
            def commit(self):
                self.raw.commit()
                if self.lost and armed['remaining']:
                    armed['remaining']-=1
                    raise OSError('synthetic original metadata ACK lost')
        return lambda runtime:Connection(real_connect(runtime))
    with TestClient(app) as client:
        def expect(response,status=200):
            assert response.status_code==status,('V3 HTTP status',response.status_code,status)
            return response.json()
        def post(url,value,*,who='ack-a',scheme='Bearer',credential=None,status=200,raw=None):
            return expect(client.post(url,content=encode(value) if raw is None else raw,
                headers={'Authorization':scheme+' '+(tokens[who] if credential is None else credential),'Content-Type':'application/octet-stream'}),status)
        def get(url,params,*,who='ack-a',scheme='Bearer',credential=None,status=200):
            return expect(client.get(url,params=params,headers={'Authorization':scheme+' '+(tokens[who] if credential is None else credential)}),status)
        legacy=post('/v2/cleanup-devices',dict(version='CLEANUP-DEVICE@2',action_id='legacy-reg',device_id='legacy',state_ref=digest(b'legacy')),who='ack-b')
        legacy_call=post('/v2/cleanup-device-calls',dict(version='CLEANUP-DEVICE@2',binding_id=legacy['binding_id'],reason='offline_expired'),scheme='Device',credential=legacy['device_token'])
        with psycopg.connect(**config,autocommit=True) as conn:
            binding_before=conn.execute('SELECT * FROM cj_cleanup_device_binding ORDER BY binding_id').fetchall()
            calls_before=conn.execute('SELECT * FROM cj_cleanup_device_call ORDER BY invocation_id').fetchall()
            migrate.down(conn,migrate.load(),38);migrate.up(conn,migrate.load(),39)
            assert conn.execute('SELECT * FROM cj_cleanup_device_binding ORDER BY binding_id').fetchall()==binding_before
            assert conn.execute('SELECT * FROM cj_cleanup_device_call ORDER BY invocation_id').fetchall()==calls_before
        registration=dict(version=VERSION,action_id='original-register',device_id='device-a',state_ref=digest(b'original-state'))
        original_raw=encode(registration)+b'\n';registration_sha=digest(original_raw)
        with patch.object(Runtime,'connect',lost_ack('INSERT INTO cj_cleanup_device_binding')):
            unknown=post('/v3/cleanup-devices',registration,raw=original_raw,status=503)
            assert unknown['error']['outcome']=='unknown'
        # No binding ID was consumed from the failed POST. Only client original
        # action/raw digest is used by this GET; it never calls POST again.
        lookup=dict(action_id=registration['action_id'],input_sha256=registration_sha)
        original=get('/v3/cleanup-device-registrations',lookup)['registration']
        assert original['version']==VERSION and original['binding_id']!='original-register'
        assert get('/v3/cleanup-device-registrations',lookup,who='ack-b')['registration'] is None
        get('/v3/cleanup-device-registrations',lookup|dict(input_sha256='0'*64),status=409)
        assert get('/v3/cleanup-device-registrations',lookup|dict(action_id='not-written'))['registration'] is None
        second=post('/v3/cleanup-devices',registration|dict(action_id='second-device',device_id='device-a2',state_ref=digest(b'second-state')))
        foreign=post('/v3/cleanup-devices',registration|dict(action_id='foreign-device',device_id='device-b'),who='ack-b')
        post('/v1/feedback',dict(action_id='feedback',problem='private original',expectation='',references=[]))
        first_call=dict(version=VERSION,action_id='original-call',binding_id=original['binding_id'],reason='offline_expired')
        call_raw=encode(first_call)+b' ';call_sha=digest(call_raw)
        with patch.object(Runtime,'connect',lost_ack('INSERT INTO cj_cleanup_device_action')):
            post('/v3/cleanup-device-calls',first_call,scheme='Device',credential=original['device_token'],raw=call_raw,status=503)
        prepared=post('/v1/account-cleanup-operations',dict(version='CLEANUP-API@1',action_id='account',binding_id=original['binding_id']))
        confirmed=post('/v1/account-cleanup-operations/'+prepared['operation_id']+'/confirmation',dict(version='CLEANUP-API@1',registry_digest=prepared['registry_digest'],confirmation='DELETE_ACCOUNT'))
        assert confirmed['business_access']=='revoked'
        key=dict(action_id='original-call',input_sha256=call_sha)
        recovered=get('/v3/cleanup-device-call-actions',key,scheme='Device',credential=original['device_token'])
        invocation=recovered['invocation'];assert invocation['call']['operation_id'].startswith('device-')
        assert invocation['call']['reason']=='offline_expired'
        assert invocation['call']['targets']==['device-cache/offline-trip','device-cache/offline-write-residue','device-cache/offline-key-keychain']
        assert post('/v3/cleanup-device-calls',first_call,scheme='Device',credential=original['device_token'],raw=call_raw)['invocation']['request_digest']==invocation['request_digest']
        get('/v3/cleanup-device-call-actions',key,scheme='Device',credential=second['device_token'],status=403)
        assert get('/v3/cleanup-device-call-actions',key,scheme='Device',credential=foreign['device_token'])['invocation'] is None
        get('/v3/cleanup-device-call-actions',key,scheme='Device',credential=legacy['device_token'],status=403)
        get('/v3/cleanup-device-call-actions',key|dict(input_sha256='0'*64),scheme='Device',credential=original['device_token'],status=409)
        before=None
        with psycopg.connect(**config) as conn:before=conn.execute('SELECT count(*) FROM cj_cleanup_device_action').fetchone()[0]
        assert get('/v3/cleanup-device-call-actions',key|dict(action_id='never-posted'),scheme='Device',credential=original['device_token'])['invocation'] is None
        with psycopg.connect(**config) as conn:assert conn.execute('SELECT count(*) FROM cj_cleanup_device_action').fetchone()[0]==before
        current=post('/v3/cleanup-device-calls',first_call|dict(action_id='account-call',reason='session_invalid'),scheme='Device',credential=original['device_token'])['invocation']
        assert current['call']['operation_id']==prepared['operation_id'] and current['call']['targets']==list(TARGETS) and len(TARGETS)==19
        receipt=dict(version=VERSION,action_id='report',operation_id=current['call']['operation_id'],invocation_id=current['call']['invocation_id'],binding_id=original['binding_id'],request_digest=current['request_digest'],outcome='unknown')
        post('/v3/cleanup-device-receipts',receipt,scheme='Cleanup',credential=current['receipt_token'])
        observed=get('/v3/cleanup-device-calls/'+current['call']['invocation_id'],{},scheme='Device',credential=original['device_token'])
        assert observed['state']=='unknown' and observed['request_digest']==current['request_digest']
        try:
            with LocalDatabase(path).connect(scope_for(ISSUER,'ack-b')) as conn:conn.execute('SELECT * FROM cj_cleanup_device_action')
        except psycopg.errors.InsufficientPrivilege:pass
        else:raise AssertionError('runtime acquired private action metadata privilege')
        with psycopg.connect(**dict(config,user='cj_local_cleanup')) as conn:
            conn.execute("SELECT set_config('cj.cleanup_subject',%s,true)",(foreign['scope_digest'],))
            assert conn.execute("SELECT action_id FROM cj_cleanup_device_action WHERE subject_digest=%s",(original['scope_digest'],)).fetchall()==[]
        try:
            with psycopg.connect(**dict(config,user='cj_local_cleanup')) as conn:
                conn.execute("SELECT set_config('cj.cleanup_subject',%s,true)",(foreign['scope_digest'],))
                conn.execute('INSERT INTO cj_cleanup_device_action VALUES(%s,%s,%s,%s,%s)',
                    (original['scope_digest'],'foreign-write','0'*64,original['binding_id'],current['call']['invocation_id']))
        except psycopg.errors.InsufficientPrivilege:pass
        else:raise AssertionError('private role crossed its bound subject on write')
        try:
            with psycopg.connect(**config,autocommit=True) as conn:migrate.down(conn,migrate.load(),38)
        except psycopg.errors.RaiseException as error:assert 'original V3 device action evidence retained' in str(error)
        else:raise AssertionError('down lost V3 original actions')
        print('PASS real first registration/call COMMIT-ACK loss with only original client action/hash GET recovery; atomic sticky original across account fence, cross-owner/binding/version/digest refusals, null read no writes, 19-target V3, V1/V2 preservation and V3 data rollback refusal; native erasure UNRUN')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='device-v3-') as folder:exercise(Path(folder),Path(os.environ['CJ_E2E_CONNINFO']))
