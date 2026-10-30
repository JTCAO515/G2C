"""#273 identity/API/schema slice. All input is synthetic; real private PG/M1 role.

No external API, model, account, cloud, fee or existing credential is used.
"""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from unittest.mock import patch

import psycopg
from fastapi.testclient import TestClient
from cj_api.local_app import app_from_environment, LocalDatabase, ISSUER, scope_for
from cj_message.domain import CommitUnknown, SequenceConflict
from cj_message.postgres import Repository
from cj_message.travel import ABI, Service
from cj_api.generated import TravelActionResponse, TravelActionQueryResponse, TravelContextReadResponse
import local_history_pg as harness


def exercise(auth, conninfo):
    harness.dev_auth.init(auth, ['alice', 'bob'])
    config = json.loads(conninfo.read_text())
    headers = {s: {'Authorization': 'Bearer '+harness.dev_auth.token(auth, s, 30)} for s in ('alice','bob')}
    scope = scope_for(ISSUER, 'alice')
    def raw(a, op='create', ref=None):
        return json.dumps(dict(version='TRAVEL-context-action.1',action_id=a,operation=op,travel_context=ref)).encode()
    def ref(c): return {'id':c['id'],'expected_version':c['version']}
    def expect(response, code=200, model=None):
        value = harness.expect(response,code)
        if model is not None: model.model_validate_json(response.content,strict=True)
        return value
    env={'CJ_LOCAL_AUTH_DIR':str(auth),'CJ_LOCAL_CONNINFO':str(conninfo)}
    with patch.dict(os.environ, env):
        app=app_from_environment()
        with TestClient(app) as client:
            def post(body, subject='alice', code=200):
                return expect(client.post('/v1/travel-context-actions',content=body,
                    headers={**headers[subject],'Content-Type':'application/octet-stream'}),code,
                    TravelActionResponse if code==200 else None)
            original=raw('create-a'); accepted=post(original)['receipt']; c=accepted['travel_context']
            assert c['version']==1 and c['active'] is True
            assert post(original)['receipt']==accepted
            post(original+b' ',code=409)
            saved=expect(client.get('/v1/travel-contexts/'+c['id'],headers=headers['alice']),model=TravelContextReadResponse)
            assert saved['travel_context']['id']==c['id'] and saved['travel_context']['created_at']
            wrong=expect(client.get('/v1/travel-contexts/'+c['id'],headers=headers['bob']),503)
            missing=expect(client.get('/v1/travel-contexts/'+'0'*32,headers=headers['bob']),503)
            assert wrong['error']==missing['error']
            assert expect(client.get('/v1/travel-context-actions/create-a',headers=headers['bob']),model=TravelActionQueryResponse)['receipt'] is None
            post(raw('foreign','advance',ref(c)),subject='bob',code=503)
            newer=post(raw('advance','advance',ref(c)))['receipt']['travel_context']
            assert newer['id']==c['id'] and newer['version']==2
            stale=post(raw('stale','advance',ref(c)),code=409)
            assert stale['error']['code']=='TRAVEL_CONTEXT_CONFLICT'
            final=post(raw('deactivate','deactivate',ref(newer)))['receipt']['travel_context']
            assert final['version']==3 and final['active'] is False
            post(raw('reactivation','advance',ref(final)),code=409)
            assert post(original)['receipt']==accepted
            expect(client.post('/v1/travel-context-actions',content=original,headers={'Content-Type':'application/octet-stream'}),401)
            post(raw('bad')[:-1]+b',"owner":"bob"}',code=400)
            expect(client.get('/v1/travel-context-actions/create-a?owner=bob',headers=headers['alice']),400)
            expect(client.post('/v1/travel-context-actions',content=b'x'*16385,
                headers={**headers['alice'],'Content-Type':'application/octet-stream'}),413)
        with TestClient(app_from_environment()) as reopened:
            assert expect(reopened.get('/v1/travel-context-actions/create-a',headers=headers['alice']))['receipt']==accepted
            assert expect(reopened.get('/v1/travel-contexts/'+c['id'],headers=headers['alice']))['travel_context']['version']==3
        database=LocalDatabase(conninfo)
        # Real concurrent CAS on one original identity, not synthetic callback state.
        service=Service(Repository(lambda:database.connect(scope),scope))
        racing=json.loads(service.apply(raw('race-create')))['travel_context']
        def advance(a):
            try: return json.loads(service.apply(raw(a,'advance',ref(racing))))
            except SequenceConflict: return None
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(advance,['race-1','race-2']))
        assert sum(x is not None for x in results)==1
        # Actual commit succeeds but acknowledgement is lost. Reconciliation uses
        # original action/bytes through a new connection; no new ID or transition.
        class LostAck:
            def __init__(self,connection): self.connection=connection
            def __getattr__(self,name): return getattr(self.connection,name)
            def commit(self):
                self.connection.commit()
                raise OSError('synthetic lost acknowledgement')
        def lost_repository(connect, bound_scope, **kwargs):
            return Repository(lambda:LostAck(connect()),bound_scope,**kwargs)
        with TestClient(app_from_environment()) as client:
            with patch('cj_api.local_app.MessageRepository',side_effect=lost_repository):
                result=expect(client.post('/v1/travel-context-actions',content=raw('lost-ack'),
                    headers={**headers['alice'],'Content-Type':'application/octet-stream'}),503)
                assert result['error']['code']=='TRAVEL_CONTEXT_OUTCOME_UNKNOWN'
                assert result['error']['recovery']=='reconcile_original'
        original_ack=service.query_action('lost-ack')
        assert original_ack is not None and service.apply(raw('lost-ack'))==original_ack
        class ReturnRevoked(LostAck):
            def commit(self):
                self.connection.commit()
                (auth/'invited.json').write_text(json.dumps(['bob']))
        def revoke_repository(connect,bound_scope,**kwargs):
            return Repository(lambda:ReturnRevoked(connect()),bound_scope,**kwargs)
        try:
            with TestClient(app_from_environment()) as client:
                with patch('cj_api.local_app.MessageRepository',side_effect=revoke_repository):
                    result=expect(client.post('/v1/travel-context-actions',content=raw('return-revoked'),
                        headers={**headers['alice'],'Content-Type':'application/octet-stream'}),503)
                    assert result['error']['code']=='TRAVEL_CONTEXT_OUTCOME_UNKNOWN'
        finally:
            (auth/'invited.json').write_text(json.dumps(['alice','bob']))
        assert service.query_action('return-revoked') is not None
        with psycopg.connect(**config,autocommit=True) as admin:
            assert admin.execute('SELECT count(*) FROM cj_message_chat').fetchone()[0]==0
            assert admin.execute('SELECT count(*) FROM cj_run_record').fetchone()[0]==0
            assert admin.execute('SELECT count(*) FROM cj_trip_record').fetchone()[0]==0
            assert admin.execute('SELECT count(*) FROM cj_usage_ledger_candidate').fetchone()[0]==0
            assert admin.execute('SELECT count(*) FROM cj_needs_record').fetchone()[0]==0
            assert admin.execute("SELECT count(*) FROM cj_travel_context_action WHERE action_id='lost-ack'").fetchone()[0]==1
            # Profile is operator-only; no pending originals exist in this scope.
            admin.execute("INSERT INTO cj_local_run_protection VALUES(%s,'local-budget-needs.1')",(scope,))
            admin.execute("INSERT INTO cj_local_metered_profile VALUES(%s,'registered-exit.1')",(scope,))
            admin.execute("INSERT INTO cj_message_context_profile VALUES(%s,'message-travel.1')",(scope,))
            roleconfig=dict(config,user='cj_m1_runtime')
            with psycopg.connect(**roleconfig,autocommit=True) as runtime:
                with runtime.transaction():
                    runtime.execute("SELECT set_config('cj.message_scope',%s,true)",(scope,))
                    assert runtime.execute('SELECT count(*) FROM cj_message_context_profile').fetchone()[0]==1
                    assert runtime.execute('SELECT count(*) FROM cj_message_scope').fetchone()[0]==0
                    runtime.execute("SELECT set_config('cj.message_context_abi',%s,true)",(ABI,))
                    assert runtime.execute('SELECT count(*) FROM cj_message_scope').fetchone()[0]==1
                    assert runtime.execute('SELECT count(*) FROM cj_travel_context').fetchone()[0]==4
                    assert runtime.execute("SELECT count(*) FROM cj_travel_context WHERE scope=%s",(scope_for(ISSUER,'bob'),)).fetchone()[0]==0
                    for sql in ('DELETE FROM cj_travel_context','TRUNCATE cj_travel_context',
                                "UPDATE cj_travel_context_action SET operation='create'",
                                "INSERT INTO cj_message_context_profile VALUES('foreign','message-travel.1')"):
                        try:
                            with runtime.transaction(): runtime.execute(sql)
                        except psycopg.errors.InsufficientPrivilege: pass
                        else: raise AssertionError('unexpected runtime permission')
                    try:
                        with runtime.transaction():
                            runtime.execute("INSERT INTO cj_travel_context VALUES(%s,%s,1,true,'foreign',now())",(scope_for(ISSUER,'bob'),'b'*32))
                    except psycopg.errors.InsufficientPrivilege: pass
                    else: raise AssertionError('cross-owner context insertion accepted')
                # Same physical connection retains no LOCAL owner or ABI after commit.
                assert runtime.execute('SELECT count(*) FROM cj_travel_context').fetchone()[0]==0
                assert runtime.execute('SELECT count(*) FROM cj_message_context_profile').fetchone()[0]==0
                try:
                    with runtime.transaction():
                        runtime.execute("SELECT set_config('cj.message_scope',%s,true),set_config('cj.message_context_abi',%s,true)",(scope,ABI))
                        raise RuntimeError('synthetic rollback')
                except RuntimeError: pass
                assert runtime.execute('SELECT count(*) FROM cj_travel_context').fetchone()[0]==0
            try: harness.migrate.down(admin,harness.migrate.load(),17)
            except psycopg.errors.RaiseException: pass
            else: raise AssertionError('populated down accepted')
            assert 18 in harness.migrate.applied(admin)
    print('PASS synthetic identity API: canonical signed admission, no chat/Trip/Meter dependency, original bytes/CAS/owner, rebuild, concurrent CAS, lost ACK, RLS/ACL/LOCAL reuse, populated down refusal')
    print('UNRUN: MESSAGE-send.2 acceptance and final worker travel leases (next #273 slice); C/A typed business integration; all real external services')


if __name__=='__main__':
    harness.exercise=exercise
    harness.main()
