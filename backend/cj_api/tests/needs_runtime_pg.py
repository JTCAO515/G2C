"""Actual canonical NEEDS API/model/PG, immutable originals and publication ordering."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from unittest.mock import patch

from fastapi.testclient import TestClient
import psycopg
from cj_agent.provider import ProviderUnknown
from cj_api.local_app import app_from_environment,LocalDatabase,ISSUER,scope_for
from cj_api.local_needs import protected_reader
from cj_api.local_needs_preview import LocalNeedsPreview,SyntheticNeedsModel
from cj_api.local_worker_context import checker_for
from cj_message.needs_binding import needs_scope_for
from cj_message.travel import ABI
from cj_needs.contract_v1 import encode_snapshot,decode_snapshot
from cj_needs.runtime import RuntimeRepository
from cj_usage.core import Meter
import local_history_pg as harness
from registered_host_support import RegisteredHost
import migrate

SOURCE='We are 3; budget USD 1000.50 per person; paid USD 200; excludes international airfare; arrival 2026-11-02 09:30 Asia/Shanghai; fixed appointment for party 2026-11-03 10:00 Asia/Shanghai; this trip mother has a leg injury; remember I always avoid spicy'


def manual(action,record,version,changes,source='用户核对 / user checked'):
    return json.dumps(dict(action_id=action,needs_id=record,expected_version=version,
        source=dict(kind='manual',text=source),changes=changes),ensure_ascii=False,separators=(',',':')).encode()


def post(client,host,subject,raw,code=200):
    return harness.expect(client.post('/v1/needs-actions',content=raw,
        headers={**host.headers[subject],'Content-Type':'application/octet-stream'}),code)


def detail(client,host,subject,record):
    return harness.expect(client.get('/v1/needs',params={'needs_id':record},headers=host.headers[subject]))['needs']


def schema_gates(conninfo):
    entries=migrate.load()
    entry=next(e for e in entries if e['name']=='needs_runtime_write')
    with psycopg.connect(**json.loads(conninfo.read_text()),autocommit=True) as conn:
        migrate.down(conn,entries,entry['version']-1)
        assert not conn.execute("SELECT has_column_privilege('cj_m1_runtime','cj_needs_record','content','UPDATE')").fetchone()[0]
        migrate.up(conn,entries,entries[-1]['version'])
        for table in ('cj_needs_scope','cj_needs_record','cj_needs_revision'):
            assert conn.execute('SELECT relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=%s::regclass',(table,)).fetchone()==(True,True)
            assert not conn.execute("SELECT has_table_privilege('cj_m1_runtime',%s,'DELETE') OR has_table_privilege('cj_m1_runtime',%s,'TRUNCATE')",(table,table)).fetchone()[0]
        assert not conn.execute("SELECT has_column_privilege('cj_m1_runtime','cj_needs_revision','content','UPDATE') OR has_column_privilege('cj_m1_runtime','cj_needs_revision','recorded_at','INSERT')").fetchone()[0]
        assert not conn.execute("SELECT has_column_privilege('cj_m1_runtime','cj_needs_record','scope','UPDATE') OR has_column_privilege('cj_m1_runtime','cj_needs_record','needs_id','UPDATE') OR has_column_privilege('cj_m1_runtime','cj_needs_scope','scope','UPDATE')").fetchone()[0]


def behavior(auth,conninfo):
    import run_worker
    subjects=['english','chinese','bob','ack','limit','cancel','unknown','writer-first','publish-first','cli','output','revoked']
    host=RegisteredHost(auth,conninfo,{s:(8,2,50000) for s in subjects})
    config=json.loads(conninfo.read_text())
    with host.api('english') as client:
        receipt=host.send(client,'english','extract',SOURCE)
        model=SyntheticNeedsModel();worker=host.worker('english',model,LocalNeedsPreview())
        assert worker.process()[0].status=='completed' and model.calls==1
        value=json.loads(host.display(client,'english','extract')['text'])
        assert value['version']=='NEEDS-preview.1' and value['confirmation']=='unconfirmed'
        assert value['source']['message_id']==receipt['message_id'] and value['source']['run_id']==receipt['run_id']
        assert base64.b64decode(value['source']['text_utf8_base64'])==SOURCE.encode()
        assert value['deferred_memory_requests']==['remember I always avoid spicy']
        scope=needs_scope_for(scope_for(ISSUER,'english'))
        with psycopg.connect(**config) as observer:
            assert observer.execute('SELECT count(*) FROM cj_needs_record WHERE scope=%s',(scope,)).fetchone()[0]==0
            assert observer.execute('SELECT count(*) FROM cj_memory_item').fetchone()[0]==0
        fields=value['fields'];fields['party_size']={'state':'known','value':4}
        original=manual('manual-first','visit',0,fields)
        first=post(client,host,'english',original)['receipt']
        assert first['version']==1
        changed=manual('manual-correction','visit',1,{'budget_paid':{'state':'known','value':'300.00'}})
        assert post(client,host,'english',changed)['receipt']['version']==2
        saved=detail(client,host,'english','visit')
        assert saved['fields']['party_size']['value']==4 and saved['fields']['budget_paid']['value']=='300.00'
        assert saved['fields']['budget_per_person']['value']=='1000.50' and 'budget_total' not in saved['fields']
        assert saved['fields']['fixed_items'][0]['locked']['value'] is True
        assert saved['fields']['temporary_conditions'][0]['applies_to']==['companion:mother']
        assert saved['fields']['arrival']['date']['value']=='2026-11-02' and saved['fields']['arrival']['timezone']['value']=='Asia/Shanghai'
        assert post(client,host,'english',original)['receipt']==first
        post(client,host,'english',original+b' ',409)
        post(client,host,'english',manual('stale','visit',1,{'party_size':{'state':'known','value':99}}),409)
        post(client,host,'english',manual('bad-companion','visit',2,{'companions':{}}),400)
        revision=harness.expect(client.get('/v1/needs-revisions',params={'needs_id':'visit','version':1},headers=host.headers['english']))['revision']
        assert base64.b64decode(revision['original_input_utf8_base64'])==original
        assert revision['fields']['party_size']['value']==4
        def correct(index):
            raw=manual('cas-'+str(index),'visit',2,{'party_size':{'state':'known','value':5+index}})
            return client.post('/v1/needs-actions',content=raw,headers={**host.headers['english'],'Content-Type':'application/octet-stream'})
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(correct,[0,1]))
        assert sorted(r.status_code for r in results)==[200,409]
        assert detail(client,host,'english','visit')['version']==3
        post(client,host,'bob',manual('bob-own','bob-record',0,{'party_size':{'state':'known','value':2}}))
        assert detail(client,host,'bob','visit') is None
        post(client,host,'bob',manual('foreign','visit',3,{'party_size':{'state':'known','value':100}}),409)
        assert detail(client,host,'english','visit')['version']==3
    with host.api('english') as reopened:
        assert detail(reopened,host,'english','visit')['version']==3
    database=LocalDatabase(conninfo,needs_context=True)
    reader=protected_reader(database,checker_for(auth))
    token=host.headers['english']['Authorization'][7:]
    assert decode_snapshot(reader.read(token,lambda op,ctx:encode_snapshot(op.detail('visit')))).version==3
    alice_scope=needs_scope_for(scope_for(ISSUER,'english'))
    with database.connect(scope_for(ISSUER,'bob')) as conn:
        assert conn.execute('SELECT content FROM cj_needs_record WHERE scope=%s',(alice_scope,)).fetchone() is None
        assert conn.execute('UPDATE cj_needs_record SET version=version+1 WHERE scope=%s RETURNING needs_id',(alice_scope,)).fetchall()==[]
    with database.connect(scope_for(ISSUER,'bob')) as conn:
        try:conn.execute('INSERT INTO cj_needs_scope(scope) VALUES(%s)',(alice_scope,))
        except psycopg.errors.InsufficientPrivilege:pass
        else:raise AssertionError('cross-owner INSERT accepted')
    # A real commit followed by ACK loss; query only the original action/bytes.
    class LostAck:
        def __init__(self,connection):self.connection=connection
        def __getattr__(self,name):return getattr(self.connection,name)
        def commit(self):
            self.connection.commit()
            raise OSError('SYNTHETIC_ACK_LOSS')
    connect=LocalDatabase.connect
    def lost_connect(database,scope,**kwargs):
        connection=connect(database,scope,**kwargs)
        return LostAck(connection) if scope==scope_for(ISSUER,'ack') else connection
    ack=manual('ack-original','ack-record',0,{'party_size':{'state':'known','value':2}})
    with patch.object(LocalDatabase,'connect',lost_connect),host.api('ack') as client:
        failure=post(client,host,'ack',ack,503)['error']
        assert failure['code']=='NEEDS_OUTCOME_UNKNOWN' and failure['recovery']=='reconcile_original'
    with host.api('ack') as client:
        found=harness.expect(client.get('/v1/needs-action-receipts',params={'action_id':'ack-original'},headers=host.headers['ack']))['receipt']
        assert found['version']==1 and post(client,host,'ack',ack)['receipt']==found
        assert detail(client,host,'ack','ack-record')['version']==1
    with host.api('chinese') as client:
        text='本次3人；预算CNY1000每人；不含国际机票；抵达2026-11-02 09:30 Asia/Shanghai；本次母亲腿伤；请记住我长期不吃辣'
        host.send(client,'chinese','中文预览',text)
        model=SyntheticNeedsModel();assert host.worker('chinese',model,LocalNeedsPreview()).process()[0].status=='completed'
        value=json.loads(host.display(client,'chinese','中文预览')['text'])
        assert value['fields']['budget_currency']['value']=='CNY' and value['fields']['temporary_conditions'][0]['applies_to']==['companion:mother']
        post(client,host,'chinese',manual('中文保存','chinese-record',0,value['fields']),400)  # NEEDS action IDs stay the frozen ASCII grammar.
        assert post(client,host,'chinese',manual('chinese-save','chinese-record',0,value['fields']))['receipt']['version']==1
    with host.api('limit') as client:
        model=SyntheticNeedsModel();worker=host.worker('limit',model,LocalNeedsPreview())
        for index in range(16):
            host.send(client,'limit','limit-'+str(index),'We are 3')
            assert worker.process()[0].status=='completed'
        host.send(client,'limit','limit-over','We are 3')
        assert worker.process()[0].status=='failed' and model.calls==16
        assert host.status(client,'limit','limit-over')['budget_exhausted_stage']=='answer'
        assert Meter.exposure(host.ledger('limit'))==16
    with host.api('output') as client:
        host.send(client,'output','output','remember '+'x'*5000)
        model=SyntheticNeedsModel()
        assert host.worker('output',model,LocalNeedsPreview()).process()[0].status=='failed'
        assert host.status(client,'output','output')['budget_exhausted_stage']=='answer' and model.calls==1
    with host.api('unknown') as client:
        host.send(client,'unknown','unknown','We are 3')
        class UnknownModel(SyntheticNeedsModel):
            def stream(self,*args,**kwargs):
                self.calls+=1
                raise ProviderUnknown('synthetic completion unknown')
                yield ''
        model=UnknownModel();assert host.worker('unknown',model,LocalNeedsPreview()).process()[0].status=='unknown'
        original=host.ledger('unknown')
        assert model.calls==1 and Meter.exposure(original)==1
        assert host.worker('unknown',model,LocalNeedsPreview()).process()==[] and host.ledger('unknown')==original
    with host.api('cancel') as client:
        host.send(client,'cancel','cancel','We are 3')
        class CancelModel(SyntheticNeedsModel):
            def stream(self,*args,**kwargs):
                for raw in super().stream(*args,**kwargs):
                    yield raw[:1]
                    harness.expect(client.post('/v1/run-cancellations',json={'version':'RUN-cancel.1','message_id':'cancel'},headers=host.headers['cancel']))
                    yield raw[1:]
        model=CancelModel();assert host.worker('cancel',model,LocalNeedsPreview()).process()[0].status=='cancelled'
        assert host.display(client,'cancel','cancel')['text']=='' and model.calls==1
    with host.api('revoked') as client:
        post(client,host,'revoked',manual('revoked-first','revoked-record',0,{'party_size':{'state':'known','value':2}}))
        host.send(client,'revoked','revoked','We are 3')
        model=SyntheticNeedsModel();worker=host.worker('revoked',model,LocalNeedsPreview())
        invitation=(auth/'invited.json').read_bytes()
        try:
            (auth/'invited.json').write_text(json.dumps([s for s in subjects if s!='revoked']))
            post(client,host,'revoked',manual('revoked-late','revoked-record',1,{'party_size':{'state':'known','value':5}}),503)
            assert worker.process()[0].status=='context_invalid' and model.calls==0
        finally:(auth/'invited.json').write_bytes(invitation)
        assert detail(client,host,'revoked','revoked-record')['version']==1
    publication_orders(host,auth,conninfo)
    with host.api('cli') as client:
        host.send(client,'cli','cli','We are 3; dates undecided')
        completed=subprocess.run([sys.executable,'-B',str(harness.ROOT/'scripts/run_worker.py'),
            '--conninfo-json',str(conninfo),'--auth-dir',str(auth),'--run-context',str(host.profiles['cli'][0]),
            '--tools-profile','synthetic-needs-v1','--once'],env=dict(os.environ),capture_output=True,text=True,timeout=30)
        assert completed.returncode==0,(completed.stdout,completed.stderr)
        assert 'local_provider_calls=1' in completed.stdout
        assert json.loads(host.display(client,'cli','cli')['text'])['version']=='NEEDS-preview.1'
    print('PASS actual NEEDS API/preview/correction/history/CAS/ACK/owner/quota/unknown/cancel/worker CLI; no automatic Memory or formal Trip writes')


def publication_orders(host,auth,conninfo):
    import run_worker
    def prepare(client,subject):
        post(client,host,subject,manual('seed','fixed-record',0,{'party_size':{'state':'known','value':3}}))
        harness.dev_auth.activate_travel(conninfo,subject,host.profiles[subject][1],ABI)
        chat=harness.expect(client.put('/v1/conversations',params={'conversation_id':'planning'},headers=host.headers[subject]))
        raw=json.dumps(dict(version='MESSAGE-send.2',conversation_id='planning',message_id='planning',text='We are 3',
            trip_id=None,creation_intent='consider_trip',expected_generation=chat['generation'],expected_sequence=0,
            travel_context=None,needs_reference=dict(id='fixed-record',expected_version=1))).encode()
        harness.expect(client.post('/v2/messages',content=raw,headers={**host.headers[subject],'Content-Type':'application/octet-stream'}))
    def worker(subject,model):
        db=LocalDatabase(conninfo,run_context=host.profiles[subject][1],travel_context=True,needs_context=True)
        return run_worker._worker_for_scope(db,model,auth,scope_for(ISSUER,subject),checker_for(auth),tools_configuration=LocalNeedsPreview())
    with host.api('writer-first') as client:
        prepare(client,'writer-first')
        class RevisedModel(SyntheticNeedsModel):
            def stream(self,*args,**kwargs):
                for raw in super().stream(*args,**kwargs):
                    yield raw[:1]
                    assert post(client,host,'writer-first',manual('newer','fixed-record',1,{'party_size':{'state':'known','value':4}}))['receipt']['version']==2
                    yield raw[1:]
        model=RevisedModel();outcome=worker('writer-first',model).process()[0]
        assert outcome.status=='context_invalid' and outcome.proposal_id is None and model.calls==1
        assert detail(client,host,'writer-first','fixed-record')['fields']['party_size']['value']==4
    with host.api('publish-first') as client:
        prepare(client,'publish-first')
        model=SyntheticNeedsModel();running=worker('publish-first',model)
        published=threading.Event();release=threading.Event();original=running.drafts.publish
        def hold_after_real_publish(*args,**kwargs):
            result=original(*args,**kwargs)
            published.set()
            assert release.wait(5)
            return result
        running.drafts.publish=hold_after_real_publish
        with ThreadPoolExecutor(max_workers=2) as pool:
            run=pool.submit(running.process)
            assert published.wait(10)
            edit=pool.submit(post,client,host,'publish-first',manual('after-publish','fixed-record',1,{'party_size':{'state':'known','value':5}}))
            try:
                deadline=time.monotonic()+3
                with psycopg.connect(**json.loads(conninfo.read_text()),autocommit=True) as observer:
                    while time.monotonic()<deadline:
                        waiting=observer.execute("SELECT count(*) FROM pg_stat_activity WHERE usename='cj_m1_runtime' AND wait_event='advisory' AND query LIKE '%cj_needs_fence_key%'").fetchone()[0]
                        if waiting:break
                        time.sleep(.01)
                assert waiting>0 and not edit.done()
            finally:release.set()
            outcome=run.result(timeout=10)[0];saved=edit.result(timeout=10)
        assert outcome.proposal_id is not None and saved['receipt']['version']==2
        assert detail(client,host,'publish-first','fixed-record')['fields']['party_size']['value']==5
        assert harness.expect(client.get('/v1/trips',params={'limit':50},headers=host.headers['publish-first']))['trips']==[]
    print('PASS actual manual NEEDS writer first rejects old draft; real proposal + RUN commit first holds writer until original publication ends')


def exercise(auth,conninfo):
    schema_gates(conninfo)
    with patch.dict(os.environ,dict(CJ_LOCAL_NEEDS_PROFILE='manual-v1',CJ_LOCAL_TRAVEL_CONTEXT='message-travel.1',CJ_DRAFT_CONTENT_VERSION='legacy')):
        behavior(auth,conninfo)
    entry=next(e for e in migrate.load() if e['name']=='needs_runtime_write')
    with psycopg.connect(**json.loads(conninfo.read_text()),autocommit=True) as conn:
        try:conn.execute((harness.ROOT/entry['down']).read_text())
        except psycopg.errors.ObjectNotInPrerequisiteState:pass
        else:raise AssertionError('nonempty NEEDS down accepted')


if __name__=='__main__':
    harness.exercise=exercise;harness.main()
