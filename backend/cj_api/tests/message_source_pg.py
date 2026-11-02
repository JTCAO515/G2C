"""#403 signed JWT + restricted PG; consent fixture is not C's actual authority."""
import base64
from contextlib import contextmanager
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import uuid
import psycopg
from fastapi.testclient import TestClient
from cj_api.local_app import app_from_environment, LocalDatabase, ISSUER, scope_for
from cj_api.local_worker_context import checker_for
from cj_api.message_source_routes import register_message_source_routes
from cj_message.auth_boundary import Boundary
from cj_message.domain import Cursor, Unavailable
from cj_message.source import SourcePermit, SourceQuery, VERSION

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts'))
import dev_auth
import migrate


class ConsentFixture:
    def __init__(self, database):
        self.database, self.after = database, None

    @contextmanager
    def hold(self, principal, scope, query):
        if scope != scope_for(principal.issuer, principal.subject): raise Unavailable()
        with self.database.connect(scope) as conn:
            conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,403))', (scope,))
            row = conn.execute('SELECT generation,epoch,enabled,source_version,withdrawal_epoch,after_sequence,through_sequence '
                'FROM source_consent_fixture WHERE scope=%s AND conversation_id=%s', (scope, query.conversation_id)).fetchone()
            if row is None or row[:5] != (query.generation, query.epoch, True, query.source_version, query.withdrawal_epoch) or not row[5] <= query.after < query.through <= row[6]: raise Unavailable()
            yield SourcePermit(Cursor(scope,query.conversation_id,query.generation,query.epoch,query.through,query.after),row[3],row[4])
            if self.after: self.after()


def exercise(auth, conninfo):
    config = json.loads(conninfo.read_text())
    dev_auth.init(auth, ['alice', 'bob'])
    tokens = {s: dev_auth.token(auth,s,30) for s in ('alice','bob')}
    headers = {s: {'Authorization':'Bearer '+tokens[s],'Content-Type':'application/octet-stream'} for s in tokens}
    with patch.dict(os.environ, {'CJ_LOCAL_AUTH_DIR':str(auth),'CJ_LOCAL_CONNINFO':str(conninfo)}):
        app, database = app_from_environment(), LocalDatabase(conninfo)
        boundary = Boundary(checker_for(auth),lambda p:database.message_repository(scope_for(p.issuer,p.subject)),lambda:uuid.uuid4().hex)
        policy = ConsentFixture(database)
        register_message_source_routes(app,boundary,policy)
        with psycopg.connect(**config) as conn:
            conn.execute('CREATE TABLE source_consent_fixture(scope text NOT NULL,conversation_id text NOT NULL,generation text NOT NULL,epoch bigint NOT NULL,enabled boolean NOT NULL,source_version bigint NOT NULL,withdrawal_epoch bigint NOT NULL,after_sequence bigint NOT NULL,through_sequence bigint NOT NULL,PRIMARY KEY(scope,conversation_id))')
            conn.execute('ALTER TABLE source_consent_fixture ENABLE ROW LEVEL SECURITY')
            conn.execute('ALTER TABLE source_consent_fixture FORCE ROW LEVEL SECURITY')
            conn.execute("CREATE POLICY own ON source_consent_fixture TO cj_m1_runtime USING(scope=nullif(current_setting('cj.message_scope',true),''))")
            conn.execute('GRANT SELECT ON source_consent_fixture TO cj_m1_runtime')
        alice = scope_for(ISSUER,'alice')
        def update(sql,*args):
            with psycopg.connect(**config) as conn:
                conn.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,403))',(alice,))
                conn.execute(sql,args)
        with TestClient(app) as client:
            def expect(response,status=200):
                assert response.status_code == status,(response.status_code,response.text)
                return response.json()
            def post(path,value,subject='alice',status=200):
                return expect(client.post(path,content=json.dumps(value).encode(),headers=headers[subject]),status)
            head = expect(client.put('/v1/conversations',params={'conversation_id':'chat'},headers=headers['alice']))
            expect(client.put('/v1/conversations',params={'conversation_id':'other'},headers=headers['bob']))
            def status(cid,subject='alice'):
                found={}
                def read(context):
                    found['context']=context
                    found['value']=context.source_status_v1(cid)
                    return b'materialized-source-status'
                boundary.with_history_context(tokens[subject],read)
                return found['value'],found['context']
            opened,expired_context=status('chat')
            assert opened.cursor==Cursor(alice,'chat',head['generation'],0,0,0) and opened.end is None and opened.conversation_type=='travel'
            try:expired_context.source_status_v1('chat')
            except RuntimeError:pass
            else:raise AssertionError('source status escaped its protected context')
            for cid in ('chat','missing'):
                try:status(cid,'bob')
                except Unavailable:pass
                else:raise AssertionError('foreign/absent conversation became open')
            from cj_message import source_status_v1
            actual_status=source_status_v1.SourceStatus
            def locked(*args):
                for sql in ('SELECT scope FROM cj_message_scope WHERE scope=%s FOR UPDATE NOWAIT',
                            "SELECT conversation_id FROM cj_message_chat WHERE scope=%s AND conversation_id='chat' FOR UPDATE NOWAIT"):
                    try:
                        with psycopg.connect(**config) as conn:conn.execute(sql,(alice,))
                    except psycopg.errors.LockNotAvailable:pass
                    else:raise AssertionError('source status did not retain canonical scope/chat locks')
                return actual_status(*args)
            with patch.object(source_status_v1,'SourceStatus',side_effect=locked):
                assert status('chat')[0]==opened
            with database.connect(alice) as conn:
                assert conn.execute("SELECT end_id,end_generation,end_epoch,end_sequence FROM cj_message_chat WHERE conversation_id='chat'").fetchone()==(None,None,None,None)
                assert conn.execute('SELECT count(*) FROM cj_message_receipt').fetchone()==(0,)
            # A structurally valid but false persisted end must fail, not become open.
            corrupt=expect(client.put('/v1/conversations',params={'conversation_id':'corrupt-end'},headers=headers['alice']))
            update('UPDATE cj_message_chat SET end_id=%s,end_generation=%s,end_epoch=0,end_sequence=0 WHERE scope=%s AND conversation_id=%s',
                   '0'*64,corrupt['generation'],alice,'corrupt-end')
            try:status('corrupt-end')
            except Unavailable:pass
            else:raise AssertionError('corrupt persisted end became open or a genuine signal')
            inactive=expect(client.put('/v1/conversations',params={'conversation_id':'inactive'},headers=headers['alice']))
            update('UPDATE cj_message_chat SET active=false WHERE scope=%s AND conversation_id=%s',alice,'inactive')
            try:status('inactive')
            except Unavailable:pass
            else:raise AssertionError('inactive conversation became open')
            originals = []
            for i in range(3):
                raw=json.dumps(dict(version='MESSAGE-send.1',conversation_id='chat',message_id=f'm{i}',text=f'synthetic {i}',trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=i)).encode()
                expect(client.post('/v1/messages',content=raw,headers=headers['alice'])); originals.append(raw)
            update('INSERT INTO source_consent_fixture VALUES(%s,%s,%s,0,false,1,1,0,3)',alice,'chat',head['generation'])
            query=dict(version=VERSION,conversation_id='chat',generation=head['generation'],epoch=0,after=0,through=3,source_version=1,withdrawal_epoch=1,mode='incremental')
            read='/internal/v1/message-source/read'
            post(read,query,status=503)
            update('UPDATE source_consent_fixture SET enabled=true,source_version=2 WHERE scope=%s',alice)
            query['source_version']=2
            value=post(read,query)
            assert [base64.b64decode(x['original_utf8_base64']) for x in value['messages']]==originals
            assert 'scope' not in value['cursor'] and value['end'] is None
            assert post(read,query,'bob',503)['error']==post(read,dict(query,conversation_id='missing'),'bob',503)['error']
            post(read,dict(query,owner='alice'),status=400)
            duplicate=json.dumps(query).encode()[:-1]+b',"source_version":2}'
            expect(client.post(read,content=duplicate,headers=headers['alice']),400)
            expect(client.post(read,content=json.dumps(query).encode('utf-16'),headers=headers['alice']),400)
            for change in ({'generation':'old'},{'epoch':1},{'through':4},{'source_version':1},{'withdrawal_epoch':2}): post(read,dict(query,**change),status=503)
            update('UPDATE source_consent_fixture SET enabled=false,source_version=3 WHERE scope=%s',alice)
            post(read,query,status=503)
            update('UPDATE source_consent_fixture SET enabled=true,source_version=4,withdrawal_epoch=2 WHERE scope=%s',alice)
            post(read,query,status=503)
            query.update(source_version=4,withdrawal_epoch=2);post(read,query)
            print('PASS signed API/runtime PG: default off, exact interval/UTF8, owner isolation, stale versions, disable/re-enable, withdrawal, caller-owner rejected')
            update('UPDATE cj_message_chat SET epoch=1 WHERE scope=%s AND conversation_id=%s',alice,'chat')
            post(read,query,status=503)
            update('UPDATE source_consent_fixture SET epoch=1,source_version=5 WHERE scope=%s',alice)
            query.update(epoch=1,source_version=5);post(read,query)
            def materialize(snapshot):
                with psycopg.connect(**config) as conn:
                    assert not conn.execute('SELECT pg_try_advisory_xact_lock(hashtextextended(%s,403))',(alice,)).fetchone()[0]
                return b'lock-held'
            assert boundary.with_history_context(tokens['alice'],lambda ctx:ctx.with_enabled_source(SourceQuery(**{k:v for k,v in query.items() if k!='version'}),policy,materialize))==b'lock-held'
            print('PASS database epoch invalidation; actual consent lock retained through final encoding')
            end=dict(version=VERSION,conversation_id='chat',generation=head['generation'],epoch=1,through=3,conversation_type='travel')
            post(read,dict(query,mode='conversation_end'),status=503)
            signal=post('/internal/v1/conversation-end',end)['end']
            ended,_=status('chat')
            assert ended.cursor==Cursor(alice,'chat',head['generation'],1,3,0)
            assert ended.end is not None and ended.end.end_id==signal['end_id']
            assert status('chat')[0]==ended
            invited_for_status=auth/'invited.json';saved_for_status=invited_for_status.read_bytes()
            def revoke_after_read(*args):
                invited_for_status.write_text(json.dumps(['bob']))
                return actual_status(*args)
            from cj_message.auth_boundary import AccessBlocked
            try:
                with patch.object(source_status_v1,'SourceStatus',side_effect=revoke_after_read):
                    try:status('chat')
                    except AccessBlocked:pass
                    else:raise AssertionError('source status escaped final fresh admission')
            finally:invited_for_status.write_bytes(saved_for_status)
            print('PASS source-status-v1 atomic owned head/explicit open/genuine end, no finish/write, current epoch, foreign/absent/inactive/corrupt denial, M/chat locks, callback lifetime and final fresh AUTH')
            assert post('/internal/v1/conversation-end',end)['end']==signal
            assert post(read,dict(query,mode='conversation_end'))['end']==signal
            post('/internal/v1/conversation-end',end,'bob',503)
            post('/internal/v1/conversation-end',dict(end,conversation_type='service'),status=400)
            expect(client.post('/v1/messages',content=originals[0],headers=headers['alice']))
            late=json.loads(originals[0]);late.update(message_id='late',expected_sequence=3)
            expect(client.post('/v1/messages',content=json.dumps(late).encode(),headers=headers['alice']),503)
            with database.connect(alice) as conn:
                assert conn.execute('SELECT current_user').fetchone()[0]=='cj_m1_runtime'
                assert conn.execute('SELECT count(*) FROM cj_message_receipt').fetchone()[0]==3
            for sql in ("UPDATE cj_message_chat SET conversation_type='service' WHERE scope=%s",'UPDATE cj_message_chat SET end_id=NULL,end_generation=NULL,end_epoch=NULL,end_sequence=NULL WHERE scope=%s'):
                try:
                    with database.connect(alice) as conn:conn.execute(sql,(alice,))
                except psycopg.Error:pass
                else:raise AssertionError('runtime bypassed end/service boundary')
            with database.connect(scope_for(ISSUER,'bob')) as conn:
                assert conn.execute('SELECT end_id FROM cj_message_chat WHERE scope=%s',(alice,)).fetchall()==[]
            try:
                with psycopg.connect(**config,autocommit=True) as conn:migrate.down(conn,migrate.load(),30)
            except psycopg.Error:pass
            else:raise AssertionError('down erased durable signal')
            print('PASS stable end/replay, no Trip, late send refused, original send reconciles, service/end-reset refusal, cross-owner RLS, populated down refusal')
            invited=auth/'invited.json';saved=invited.read_bytes()
            policy.after=lambda:invited.write_text(json.dumps(['bob']))
            try:assert 'messages' not in post(read,query,status=503)
            finally:invited.write_bytes(saved);policy.after=None
            print('PASS final fresh AUTH loss withholds already encoded private source bytes')


if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='g2c-source-auth-') as temp:
        exercise(Path(temp)/'auth',Path(os.environ['CJ_E2E_CONNINFO']))
