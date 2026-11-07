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
    config=json.loads(conninfo.read_text());auth=root/'auth';dev_auth.init(auth,['alice','bob','metadata-owner'])
    tokens={s:dev_auth.token(auth,s,30) for s in ('alice','bob','metadata-owner')}
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
        # Persistent DB data is a boundary: altered original plan bytes cannot
        # be served or confirmed under the original digest.
        with psycopg.connect(**config) as conn:
            saved=conn.execute('SELECT plan_bytes FROM cj_cleanup_request WHERE operation_id=%s',(spare['operation_id'],)).fetchone()[0]
            conn.execute('UPDATE cj_cleanup_request SET plan_bytes=%s WHERE operation_id=%s',(b'{}',spare['operation_id']))
        expect(client.get('/v1/account-cleanup-preparations?action_id=spare',headers=headers['alice']),503)
        with psycopg.connect(**config) as conn:
            conn.execute('UPDATE cj_cleanup_request SET plan_bytes=%s WHERE operation_id=%s',(saved,spare['operation_id']))
        before=expect(client.get(progress_url,headers={'Authorization':'Cleanup '+cap}))
        assert before['status']=='awaiting_confirmation'
        post(progress_url+'/confirmation',dict(version='CLEANUP-API@1',registry_digest=prepared['registry_digest'],confirmation='wrong'),code=403)
        post(progress_url+'/confirmation',dict(version='CLEANUP-API@1',registry_digest=prepared['registry_digest'],confirmation='DELETE_ACCOUNT'),'bob',403)
        from cj_api.local_account_admission_v2 import (
            account_checker_for, permit_retirement_read_lease, retirement_read_operation,
        )
        from cj_auth.interfaces import AdmissionStatus
        from unittest.mock import patch
        database=LocalDatabase(conninfo)
        independent=account_checker_for(auth,database)
        opened=[]
        original_open=database._open_runtime_connection

        def record_checkout():
            connection=original_open()
            opened.append(connection)
            return connection

        with patch.object(database,'_open_runtime_connection',side_effect=record_checkout):
            with permit_retirement_read_lease(database,lambda:None),retirement_read_operation():
                assert independent.check(tokens['alice']).status is AdmissionStatus.ALLOWED
                assert independent.check(tokens['bob']).status is AdmissionStatus.UNKNOWN
                result=post(progress_url+'/confirmation',dict(version='CLEANUP-API@1',
                            registry_digest=prepared['registry_digest'],confirmation='DELETE_ACCOUNT'))
                assert independent.check(tokens['alice']).status is AdmissionStatus.DENIED
                assert len(opened)==1 and not opened[0].closed
            assert opened[0].closed
        print('PASS retirement read lease uses one physical connection, rejects foreign scope and sees freshly committed retirement')
        assert result['business_access']=='revoked' and result['online_status']=='complete' and result['status']!='complete'
        # Public C owner seam: the fence came from the actual signed confirmation.
        # Its isolated assertion also works in a genuinely read-only transaction.
        from cj_cleanup.store import require_account_retirement
        from cj_cleanup.hooks_v1_1 import HookRequest
        from cj_cleanup.core import Denied
        with psycopg.connect(**config) as audit:
            raw=audit.execute('SELECT request_bytes FROM cj_cleanup_step WHERE subject_digest=%s AND operation_id=%s AND target=%s',
                (device['alice']['scope_digest'],op,target)).fetchone()[0]
            original_request=HookRequest.from_bytes(bytes(raw))
            counts=audit.execute('SELECT (SELECT count(*) FROM cj_account_fence),(SELECT count(*) FROM cj_cleanup_operation),(SELECT count(*) FROM cj_cleanup_domain_result)').fetchone()
        def assertion(subject,request):
            with psycopg.connect(**dict(config,user='cj_local_cleanup',options='-c default_transaction_read_only=on')) as readonly:
                assert readonly.execute('SHOW transaction_read_only').fetchone()==('on',)
                readonly.execute("SELECT set_config('cj.cleanup_subject',%s,true),set_config('cj.cleanup_operation',%s,true)",(subject,op))
                with readonly.cursor() as cursor:return require_account_retirement(cursor,request)
        assert assertion(original_request.subject_digest,original_request) is None
        wire=json.loads(original_request.original_utf8)
        negatives=[(original_request.subject_digest,wire|dict(operation_id=spare['operation_id'])),
            (device['bob']['scope_digest'],wire),
            (device['bob']['scope_digest'],wire|dict(subject_digest=device['bob']['scope_digest'])),
            (original_request.subject_digest,wire|dict(selection=dict(kind='diagnostics',before_unix=0)))]
        for bound_subject,value in negatives:
            try:assertion(bound_subject,HookRequest.from_bytes(encode(value)))
            except Denied:pass
            else:raise AssertionError('public retirement assertion accepted absent/foreign/wrong-operation/wrong-purpose fence')
        with psycopg.connect(**config) as audit:
            assert audit.execute('SELECT (SELECT count(*) FROM cj_account_fence),(SELECT count(*) FROM cj_cleanup_operation),(SELECT count(*) FROM cj_cleanup_domain_result)').fetchone()==counts
        print('PASS public account-retirement helper: actual signed-confirmation fence, readonly success/None, no writes, absent/foreign/original-operation/purpose negatives; B hooks also compose it after require_intent')
        assert independent.check(tokens['alice']).status is AdmissionStatus.DENIED
        assert independent.check(tokens['bob']).status is AdmissionStatus.ALLOWED
        with patch.object(LocalDatabase,'connect',side_effect=RuntimeError('injected storage uncertainty')):
            assert independent.check(tokens['bob']).status is AdmissionStatus.UNKNOWN
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
        # Full real inventory has actual missing C/external owner hooks: it
        # must remain prepared/blocked, with neither revocation nor deletion.
        inventory=('business/message','business/usage','business/memory-authoritative','business/trip-authoritative',
            'business/needs-current-planning','business/feedback-private-actions','business/cleanup-metadata',
            'business/memory-management-actions','checkpoints/run','memory-derived',
            'device-cache/encrypted-message-file','device-cache/sdk-session-keychain','device-cache/message-key-keychain',
            'device-cache/trip-pending-file','device-cache/offline-trip','device-cache/feedback-pending',
            'device-cache/feedback-key-keychain','device-cache/memory-manual-pending','device-cache/memory-lifecycle-pending',
            'device-cache/memory-typed-pending','device-cache/memory-key-keychain','device-cache/needs-pending',
            'device-cache/needs-key-keychain','device-cache/memory-history-pending','device-cache/trip-scoped-pending',
            'device-cache/needs-planning-pending','device-cache/trip-key-keychain','device-cache/offline-key-keychain',
            'device-cache/offline-write-residue','external-processing')
        from dataclasses import replace
        full=create_local_app(conninfo_path=conninfo,auth_dir=auth,cleanup_configuration=replace(options,
            inventory=inventory,registry_path=ROOT/'backend/storage-registry.json'))
        with TestClient(full) as full_client:
            fresh=expect(full_client.post('/v1/account-cleanup-operations',headers=headers['bob'],content=encode(
                dict(version='CLEANUP-API@1',action_id='unready-full',binding_id=device['bob']['binding_id']))))
            blocked=expect(full_client.post('/v1/account-cleanup-operations/'+fresh['operation_id']+'/confirmation',headers=headers['bob'],content=encode(
                dict(version='CLEANUP-API@1',registry_digest=fresh['registry_digest'],confirmation='DELETE_ACCOUNT'))))
            assert blocked['status']=='blocked' and blocked['phase']=='prepared' and blocked['business_access']=='unchanged'
            assert expect(full_client.get('/v1/feedback-action-receipts?action_id=feedback',headers=headers['bob']))['receipt'] is not None
        from cj_cleanup.device_bridge import TARGETS
        actual=json.loads((ROOT/'backend/storage-registry.json').read_bytes())
        entries=next(store for store in actual['stores'] if store['id']=='device-cache')['objects']
        assert TARGETS==('device-cache/encrypted-message-file','device-cache/sdk-session-keychain',
            'device-cache/message-key-keychain','device-cache/trip-pending-file','device-cache/offline-trip',
            'device-cache/feedback-pending','device-cache/feedback-key-keychain')
        from cj_cleanup.device_v2 import TARGETS as V2_TARGETS
        assert set(V2_TARGETS)=={'device-cache/'+entry['id'] for entry in entries if 'CLEANUP-DEVICE@2' in entry['device_versions']} and len(V2_TARGETS)==13
        from cj_cleanup.device_v3 import TARGETS as V3_TARGETS
        assert set(V3_TARGETS)=={'device-cache/'+entry['id'] for entry in entries if 'CLEANUP-DEVICE@3' in entry['device_versions']} and len(V3_TARGETS)==19
        from cj_cleanup.device_v4 import TARGETS as V4_TARGETS
        assert set(V4_TARGETS)=={'device-cache/'+entry['id'] for entry in entries} and len(V4_TARGETS)==21
        print('PASS corrupted original plan rejects; actual full inventory missing owner hooks blocks before retirement; all device call targets registered')
        # Actual HTTP metadata finalization after the original device report:
        # erase the private scope plan, retain only bounded progress/fences.
        meta_registry=root/'metadata-registry.json'
        meta_inventory=(target,'business/cleanup-metadata',*TARGETS)
        meta_registry.write_bytes(encode(dict(version='metadata-bridge-proof',stores=[
            dict(id='business',objects=[dict(id=n.split('/')[1],cleanup_protocol='CLEANUP@1.1') for n in meta_inventory[:2]]),
            dict(id='device-cache',objects=[dict(id=n.split('/')[1],cleanup_protocol='CLEANUP@1.1') for n in TARGETS])
        ])))
        meta_options=replace(options,inventory=meta_inventory,registry_path=meta_registry)
        meta_app=create_local_app(conninfo_path=conninfo,auth_dir=auth,cleanup_configuration=meta_options)
        with TestClient(meta_app) as mc:
            def mp(url,body,scheme='Bearer',credential=tokens['metadata-owner']):
                return expect(mc.post(url,content=encode(body),headers={'Authorization':scheme+' '+credential,'Content-Type':'application/octet-stream'}))
            md=mp('/v1/cleanup-devices',dict(version='CLEANUP-DEVICE@1',action_id='register',device_id='meta-device',state_ref=digest(b'meta-state')))
            mp('/v1/feedback',dict(action_id='meta-feedback',problem='private original',expectation='',references=[]))
            prepared_meta=mp('/v1/account-cleanup-operations',dict(version='CLEANUP-API@1',action_id='meta-prepare',binding_id=md['binding_id']))
            meta_op=prepared_meta['operation_id'];meta_url='/v1/account-cleanup-operations/'+meta_op
            awaiting=mp(meta_url+'/confirmation',dict(version='CLEANUP-API@1',registry_digest=prepared_meta['registry_digest'],confirmation='DELETE_ACCOUNT'))
            assert awaiting['online_status']=='unknown' and any(s['state']=='pending' for s in awaiting['steps'] if s['target']=='business/cleanup-metadata')
            dc=mp('/v1/cleanup-device-calls',dict(version='CLEANUP-DEVICE@1',binding_id=md['binding_id'],reason='session_invalid'),'Device',md['device_token'])
            assert set(dc['call']['targets'])==set(TARGETS)
            dr=dict(version='CLEANUP-DEVICE@1',action_id='meta-report',operation_id=meta_op,invocation_id=dc['call']['invocation_id'],binding_id=md['binding_id'],request_digest=dc['request_digest'],outcome='confirmed')
            assert mp('/v1/cleanup-device-receipts',dr,'Cleanup',dc['receipt_token'])['state']=='confirmed'
            final_meta=expect(mc.get(meta_url,headers={'Authorization':'Cleanup '+prepared_meta['progress_token']}))
            assert final_meta['online_status']=='complete' and final_meta['status']!='complete'
            with psycopg.connect(**config) as conn:
                assert conn.execute('SELECT plan_bytes FROM cj_cleanup_request WHERE operation_id=%s',(meta_op,)).fetchone()==(None,)
                assert conn.execute('SELECT plan_bytes FROM cj_cleanup_operation WHERE operation_id=%s',(meta_op,)).fetchone()==(None,)
                assert conn.execute('SELECT count(*) FROM cj_feedback_action WHERE scope=%s',(scope_for(ISSUER,'metadata-owner'),)).fetchone()[0]==0
            from cj_api.local_cleanup import Runtime
            from cj_api.local_worker_context import checker_for
            runtime=Runtime(LocalDatabase(conninfo),meta_options,scope_for)
            claims=runtime.issuer.verify(prepared_meta['progress_token'],purpose='progress',operation_id=meta_op)
            resumed=runtime.host_gateway(checker_for(auth)).resume(claims.subject_digest,meta_op)
            assert resumed['online_status']=='complete' and resumed['status']!='complete'
            assert mp('/v1/cleanup-device-receipts',dr,'Cleanup',dc['receipt_token'])['state']=='confirmed'
        print('PASS real original HTTP/device/metadata chain: all seven registered device report hooks, same-transaction private plan erasure, restricted progress and host recovery after redaction')
        try:
            with psycopg.connect(**config,autocommit=True) as conn:migrate.down(conn,migrate.load(),34)
        except psycopg.Error:pass
        else:raise AssertionError('down discarded account/device original metadata')
        print('PASS nonempty down refuses retained fence/original device receipts')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='g2c-account-gateway-') as temp:
        exercise(Path(temp),Path(os.environ['CJ_E2E_CONNINFO']))
