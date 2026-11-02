"""#27 actual local HTTP + signature + restricted PG, no real account/device claims."""
import json,os,sys,tempfile,time
from pathlib import Path
from fastapi.testclient import TestClient
import psycopg
from cj_api.local_app import create_local_app,LocalDatabase,ISSUER,scope_for
from cj_api.local_cleanup import Configuration
from cj_cleanup.core import encode,digest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
import dev_auth,migrate


def exercise(root,conninfo):
    config=json.loads(conninfo.read_text());auth=root/'auth';dev_auth.init(auth,['alice','bob'])
    tokens={s:dev_auth.token(auth,s,30) for s in ('alice','bob')}
    headers={s:{'Authorization':'Bearer '+t,'Content-Type':'application/octet-stream'} for s,t in tokens.items()}
    # Component inventory is explicit: actual feedback domain only. This is not a
    # false whole-registry/C/A completion claim; the default full inventory blocks.
    target='business/feedback-private-actions';registry=root/'registry.json'
    registry.write_bytes(encode(dict(version='gateway-local-proof',stores=[dict(id='business',objects=[
        dict(id='feedback-private-actions',cleanup_protocol='CLEANUP@1.1',objects=['cj_feedback_action','cj_feedback_scope'])])])))
    options=Configuration({'test-cleanup':b'synthetic-local-cleanup-key-00000'},'test-cleanup',3600,(target,),registry,clock=time.time)
    app=create_local_app(conninfo_path=conninfo,auth_dir=auth,cleanup_configuration=options)
    with TestClient(app) as client:
        def expect(response,code=200):
            assert response.status_code==code,('unexpected HTTP status',response.status_code)
            return response.json()
        def post(path,value,who='alice',code=200,scheme=None,token=None):
            h=headers[who] if scheme is None else {'Authorization':scheme+' '+token,'Content-Type':'application/octet-stream'}
            return expect(client.post(path,content=encode(value),headers=h),code)
        device={}
        for who in ('alice','bob'):
            post('/v1/feedback',dict(action_id='feedback',problem='synthetic '+who,expectation='',references=[]),who)
            device[who]=post('/v1/cleanup-devices',dict(version='CLEANUP-DEVICE@1',action_id='register',device_id=who+'-device',state_ref=digest(who.encode())),who)
        body=dict(version='CLEANUP-API@1',action_id='prepare',binding_id=device['alice']['binding_id'])
        prepared=post('/v1/account-cleanup-operations',body)
        assert post('/v1/account-cleanup-operations',body)['operation_id']==prepared['operation_id']
        assert prepared['phase']=='prepared' and prepared['operation_id']!='prepare'
        op=prepared['operation_id'];cap=prepared['progress_token']
        progress_url='/v1/account-cleanup-operations/'+op
        recovered=expect(client.get('/v1/account-cleanup-preparations?action_id=prepare',headers=headers['alice']))
        assert recovered['preparation']['operation_id']==op
        assert expect(client.get('/v1/account-cleanup-preparations?action_id=prepare',headers=headers['bob']))['preparation'] is None
        spare=post('/v1/account-cleanup-operations',body|dict(action_id='spare'))
        before=expect(client.get(progress_url,headers={'Authorization':'Cleanup '+cap}))
        assert before['status']=='awaiting_confirmation'
        post(progress_url+'/confirmation',dict(version='CLEANUP-API@1',registry_digest=prepared['registry_digest'],confirmation='wrong'),code=403)
        post(progress_url+'/confirmation',dict(version='CLEANUP-API@1',registry_digest=prepared['registry_digest'],confirmation='DELETE_ACCOUNT'),'bob',403)
        result=post(progress_url+'/confirmation',dict(version='CLEANUP-API@1',registry_digest=prepared['registry_digest'],confirmation='DELETE_ACCOUNT'))
        assert result['business_access']=='revoked' and result['online_status']=='complete' and result['status']!='complete'
        expect(client.get('/v1/feedback-action-receipts?action_id=feedback',headers=headers['alice']),503)
        post('/v1/feedback',dict(action_id='late',problem='late',expectation='',references=[]),code=503)
        post('/v1/cleanup-devices',dict(version='CLEANUP-DEVICE@1',action_id='new-device',device_id='late',state_ref='0'*64),code=403)
        expect(client.get(progress_url,headers=headers['alice']),401)
        final=expect(client.get(progress_url,headers={'Authorization':'Cleanup '+cap}))
        assert final['operation_id']==op and final['online_status']=='complete'
        expect(client.get('/v1/account-cleanup-operations/other',headers={'Authorization':'Cleanup '+cap}),403)
        expect(client.get('/v1/account-cleanup-operations/'+spare['operation_id'],headers={'Authorization':'Cleanup '+spare['progress_token']}),403)
        expect(client.get(progress_url,headers={'Authorization':'Cleanup '+('A' if cap[0]!='A' else 'B')+cap[1:]}),403)
        post(progress_url+'/confirmation',dict(version='CLEANUP-API@1',registry_digest=prepared['registry_digest'],confirmation='DELETE_ACCOUNT'),code=403)
        assert expect(client.get('/v1/feedback-action-receipts?action_id=feedback',headers=headers['bob']))['receipt']['status']=='submitted'
        print('PASS actual original create/confirm HTTP, server ID/idempotence, explicit confirmation/owner gate, revocation denies ordinary API, exact original restricted progress and other account preserved')
        call=post('/v1/cleanup-device-calls',dict(version='CLEANUP-DEVICE@1',binding_id=device['alice']['binding_id'],reason='session_invalid'),scheme='Device',token=device['alice']['device_token'])
        assert call['call']['operation_id']==op and call['call']['reason']=='account_cleanup'
        assert call['call']['state_ref']==digest(b'alice') and call['call']['business_access']=='not_granted'
        queried=expect(client.get('/v1/cleanup-device-calls/'+call['call']['invocation_id'],headers={'Authorization':'Device '+device['alice']['device_token']}))
        assert queried['request_digest']==call['request_digest'] and queried['state']=='pending'
        receipt=dict(version='CLEANUP-DEVICE@1',action_id='device-result',operation_id=op,invocation_id=call['call']['invocation_id'],
            binding_id=device['alice']['binding_id'],request_digest=call['request_digest'],outcome='confirmed')
        ack=post('/v1/cleanup-device-receipts',receipt,scheme='Cleanup',token=call['receipt_token'])
        assert ack['state']=='confirmed'
        assert post('/v1/cleanup-device-receipts',receipt,scheme='Cleanup',token=call['receipt_token'])['receipt_digest']==ack['receipt_digest']
        post('/v1/cleanup-device-receipts',receipt|dict(request_digest='0'*64),scheme='Cleanup',token=call['receipt_token'],code=403)
        post('/v1/cleanup-device-receipts',receipt|dict(outcome='failed'),scheme='Cleanup',token=call['receipt_token'],code=409)
        invalidation=post('/v1/cleanup-device-calls',dict(version='CLEANUP-DEVICE@1',binding_id=device['bob']['binding_id'],reason='offline_expired'),
                          scheme='Device',token=device['bob']['device_token'])
        assert invalidation['call']['operation_id'].startswith('device-') and invalidation['call']['targets']==['device-cache/offline-trip']
        assert expect(client.get('/v1/feedback-action-receipts?action_id=feedback',headers=headers['bob']))['receipt'] is not None
        with psycopg.connect(**config) as conn:
            assert conn.execute('SELECT count(*) FROM cj_feedback_action WHERE scope=%s',(scope_for(ISSUER,'alice'),)).fetchone()[0]==0
            assert conn.execute('SELECT count(*) FROM cj_account_fence').fetchone()[0]==1
        print('PASS authenticated device original invocation/report bridge, replay/conflict/wrong digest, account and reconnect-only invalidation, no other-device/backup completion claim')
        try:
            with psycopg.connect(**config,autocommit=True) as conn:migrate.down(conn,migrate.load(),34)
        except psycopg.Error:pass
        else:raise AssertionError('down discarded account/device original metadata')
        print('PASS nonempty down refuses retained fence/original device receipts')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='g2c-account-gateway-') as temp:
        exercise(Path(temp),Path(os.environ['CJ_E2E_CONNINFO']))
