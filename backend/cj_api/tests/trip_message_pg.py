"""#330: signed local API, restricted PG, formal run_once, offline FakeProvider.

Trip content is a synthetic stored structured.1 fixture, not a real travel service.
"""
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch
import psycopg
from fastapi.testclient import TestClient
from cj_api.local_app import LocalDatabase,app_from_environment,scope_for,ISSUER
from cj_api.local_run_context import load_run_context
from cj_agent.provider import FakeProvider,ProviderUnknown
from cj_run.core import Binding
from cj_trip.domain import packed
from cj_message.trip_context import ABI,trip_scope_for
import local_history_pg as harness

sys.path.insert(0,str(harness.ROOT/'scripts'))
import dev_auth
import local_run_context as operator
import message_trip_profile
import run_worker


def document():
    def event(day,time):
        return {k:dict(state='known',value=v) for k,v in
            [('date',day),('time',time),('timezone','Asia/Shanghai'),('utc_offset','+08:00')]}
    return dict(content_version='structured.1',title='正式合成行程',sources=[],items=[dict(
        id='item-a',text='合成条目，不代表已核实营业事实',verification='pending',evidence=[],
        schedule=dict(start=event('2026-10-31','10:00:00'),end=event('2026-10-31','11:00:00')),
        fixed=dict(state='unknown'),source_category='unknown',source_refs=[])])


def exercise(auth,conninfo):
    config=json.loads(conninfo.read_text())
    subjects=['alice','bob','upgrade','memory']
    dev_auth.init(auth,subjects)
    now=int(time.time())
    value=dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(unit='provider_call',budget=30,
        period_start=now-60,period_end=now+3600,max_steps=30,max_tools=10,max_output=100000,max_seconds=600),
        output_limits=dict(model=12000,tool=2000,memory=2000)),history=[])
    path=auth.parent/'trip-run.json';path.write_text(json.dumps(value));context=load_run_context(path)
    for subject in subjects:
        operator.provision_budget(conninfo,context,subject)
        dev_auth.activate_travel(conninfo,subject,context,'MESSAGE-TRAVEL-CONSUMER@1')
    # Empty up/down round trip, and the old schema remains intact.
    import migrate
    migration=migrate.load()[-1]
    up=harness.ROOT/migration['file'];down=harness.ROOT/migration['down']
    # Development runner may install this append migration after the manifest tip.
    if migration['name']=='message_trip_context':
        with psycopg.connect(**config) as admin:
            admin.execute(down.read_text());admin.execute(up.read_text())
    for subject in ('alice','bob'):
        assert message_trip_profile.activate(conninfo,subject,context,ABI)=='activated'
    database=LocalDatabase(conninfo,run_context=context,travel_context=True,trip_context=True)
    scope=scope_for(ISSUER,'alice');foreign=scope_for(ISSUER,'bob');source=packed(document())
    database.provision(scope);database.provision(foreign)
    with psycopg.connect(**config) as admin:
        admin.execute('INSERT INTO cj_trip_record(scope,trip_id,version,content) VALUES(%s,%s,1,%s)',
                      (trip_scope_for(scope),'trip-a',source))
        admin.execute('INSERT INTO cj_trip_record(scope,trip_id,version,content) VALUES(%s,%s,1,%s)',
                      (trip_scope_for(scope),'trip-b',source))
    headers={s:{'Authorization':'Bearer '+dev_auth.token(auth,s,30)} for s in subjects}
    env=dict(CJ_LOCAL_AUTH_DIR=str(auth),CJ_LOCAL_CONNINFO=str(conninfo),CJ_LOCAL_RUN_CONTEXT=str(path),
        CJ_LOCAL_TRAVEL_CONTEXT='message-travel.1',CJ_LOCAL_TRIP_CONTEXT='message-trip.1')
    def expect(response,code=200):return harness.expect(response,code)
    def selection(**changes):
        value=dict(id='trip-a',expected_version=1,day=dict(date='2026-10-31',timezone='Asia/Shanghai'),item_id='item-a')
        value.update(changes);return value
    def binding(accepted):
        r=accepted['receipt'];return Binding(scope,r['conversation_id'],r['generation'],r['message_id'],r['run_id'],r['sequence'])
    with patch.dict(os.environ,env):
      with TestClient(app_from_environment()) as client:
        def send(mid,selected,cid=None,subject='alice',code=200,head=None):
            cid=mid if cid is None else cid
            if head is None:head=expect(client.put('/v1/conversations',params=dict(conversation_id=cid),headers=headers[subject]))
            raw=json.dumps(dict(version='MESSAGE-send.3',conversation_id=cid,message_id=mid,text='这个条目安排如何？',
                trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=head['last_sequence'],
                travel_context=None,needs_reference=None,trip_context=selected),ensure_ascii=False,indent=2).encode()+b'\n'
            return expect(client.post('/v3/messages',content=raw,headers={**headers[subject],'Content-Type':'application/octet-stream'}),code),raw
        def status(mid,cid=None,subject='alice'):
            return expect(client.get('/v3/message-send-status',params=dict(conversation_id=mid if cid is None else cid,message_id=mid),headers=headers[subject]))
        def cancel(mid,subject='alice',code=200):
            return expect(client.post('/v3/run-cancellations',json=dict(version='RUN-cancel.3',message_id=mid),headers=headers[subject]),code)
        send('foreign',selection(),subject='bob',code=503)
        send('stale',selection(expected_version=2),code=409)
        send('item',selection(item_id='foreign-item'),code=503)
        send('day',selection(day=dict(date='2026-11-01',timezone='Asia/Shanghai')),code=503)
        send('owner',dict(**selection(),owner='alice'),code=400)
        accepted,raw=send('positive',selection())
        assert accepted['version']=='MESSAGE-accept.3'
        assert accepted['reference']['content_sha256']==hashlib.sha256(source).hexdigest()
        model=FakeProvider();outcomes=run_worker.run_once(database,model,auth)
        assert len(outcomes)==1 and outcomes[0].status=='completed' and model.calls==1
        display=expect(client.get('/v3/run-display',params=dict(message_id='positive'),headers=headers['alice']))
        assert display['reference']==accepted['reference']
        assert 'trip-a' in json.dumps(display) and 'item-a' in json.dumps(display)
        history=expect(client.get('/v2/message-history',params=dict(conversation_id='positive',limit=10),headers=headers['alice']))
        assert base64.b64decode(history['messages'][0]['original_utf8_base64'])==raw
        assert history['messages'][0]['reference']==accepted['reference']
        assert status('positive')['reference']==accepted['reference']
        # Version changes cannot refresh original replay/status/history/cancel bytes.
        with psycopg.connect(**config) as admin:
            admin.execute('SELECT scope FROM cj_trip_scope WHERE scope=%s FOR UPDATE',(trip_scope_for(scope),))
            admin.execute('UPDATE cj_trip_record SET version=2 WHERE scope=%s AND trip_id=%s',(trip_scope_for(scope),'trip-a'))
        repeated=expect(client.post('/v3/messages',content=raw,headers={**headers['alice'],'Content-Type':'application/octet-stream'}))
        assert repeated['receipt']==accepted['receipt'] and repeated['reference']==accepted['reference']
        assert cancel('positive')['reference']==accepted['reference']
        assert status('positive')['reference']==accepted['reference']
        # Ambiguous null is a clarification, even though two formal Trips exist.
        ambiguous,_=send('ambiguous',None)
        model=FakeProvider();assert run_worker.run_once(database,model,auth)[0].status=='completed' and model.calls==1
        text=json.dumps(expect(client.get('/v3/run-display',params=dict(message_id='ambiguous'),headers=headers['alice'])),ensure_ascii=False)
        assert '请明确选择' in text and 'trip-a' not in text and 'trip-b' not in text
        # Accepted current version invalidates before dispatch; no charged invocation.
        obsolete,_=send('obsolete',selection(expected_version=2))
        with psycopg.connect(**config) as admin:
            admin.execute('SELECT scope FROM cj_trip_scope WHERE scope=%s FOR UPDATE',(trip_scope_for(scope),))
            admin.execute('UPDATE cj_trip_record SET version=3 WHERE scope=%s AND trip_id=%s',(trip_scope_for(scope),'trip-a'))
        model=FakeProvider();assert run_worker.run_once(database,model,auth)[0].status=='context_invalid' and model.calls==0
        # Cancel remains possible after source invalidation and cannot expose another owner.
        cancel('obsolete',subject='bob',code=503)
        assert cancel('obsolete')['reference']==obsolete['reference']
        queued,_=send('cancelled',selection(expected_version=3));assert cancel('cancelled')['status']=='cancelled'
        model=FakeProvider();assert run_worker.run_once(database,model,auth)[0].status=='cancelled' and model.calls==0
        # Late model output cannot outlive a Trip update.
        late,_=send('late',selection(expected_version=3))
        class Advances(FakeProvider):
            def stream(self,messages,system=None):
                self.calls+=1
                with psycopg.connect(**config) as admin:
                    admin.execute('SELECT scope FROM cj_trip_scope WHERE scope=%s FOR UPDATE',(trip_scope_for(scope),))
                    admin.execute('UPDATE cj_trip_record SET version=4 WHERE scope=%s AND trip_id=%s',(trip_scope_for(scope),'trip-a'))
                yield 'PRIVATE_LATE_OUTPUT'
        model=Advances();assert run_worker.run_once(database,model,auth)[0].status=='context_invalid' and model.calls==1
        state=database.run_repository(scope).recover(binding(late)).state
        assert not state.text and not state.effects
        # Provider UNKNOWN is an original terminal outcome, never redispatched.
        unknown,_=send('unknown',selection(expected_version=4))
        class Unknown(FakeProvider):
            def stream(self,messages,system=None):
                self.calls+=1
                raise ProviderUnknown('synthetic unknown')
                yield
        model=Unknown();assert run_worker.run_once(database,model,auth)[0].status=='unknown' and model.calls==1
        model=FakeProvider();assert run_worker.run_once(database,model,auth)==[] and model.calls==0
        assert cancel('unknown')['status']=='unknown'
        assert status('unknown')['reference']==unknown['reference']
        # Actual CLI consumes the configured version; no external provider is permitted.
        send('cli',selection(expected_version=4))
        result=subprocess.run([sys.executable,'-B',str(harness.ROOT/'scripts/run_worker.py'),'--conninfo-json',str(conninfo),
            '--auth-dir',str(auth),'--run-context',str(path),'--travel-context','message-travel.1',
            '--trip-context','message-trip.1','--once'],env={**os.environ,**env},capture_output=True,text=True,timeout=30)
        assert result.returncode==0,(result.stdout,result.stderr)
        assert 'local_provider_calls=1' in result.stdout
        # Old new-send writers cannot bypass the new profile's reference requirement.
        with psycopg.connect(**dict(config,user='cj_m1_runtime')) as runtime:
            runtime.execute("SELECT set_config('cj.message_scope',%s,true),set_config('cj.message_context_abi',%s,true)",
                            (scope,'MESSAGE-TRAVEL-CONSUMER@1'))
            assert runtime.execute('SELECT count(*) FROM cj_message_receipt').fetchone()[0]==0
            runtime.execute("SELECT set_config('cj.message_trip_abi',%s,true)",(ABI,))
            assert runtime.execute('SELECT count(*) FROM cj_message_trip_reference WHERE scope=%s',(foreign,)).fetchone()[0]==0
            for sql in ('DELETE FROM cj_message_trip_reference','UPDATE cj_message_trip_reference SET selection_epoch=1'):
                try:
                    with runtime.transaction():runtime.execute(sql)
                except psycopg.errors.InsufficientPrivilege:pass
                else:raise AssertionError('immutable references granted runtime mutation')
        with psycopg.connect(**config) as admin:
            assert admin.execute('SELECT count(*) FROM cj_message_receipt WHERE message_id IN (%s,%s,%s,%s)',('foreign','stale','item','day')).fetchone()[0]==0
            if migration['name']=='message_trip_context':
                try:
                    with admin.transaction():admin.execute(down.read_text())
                except psycopg.errors.RaiseException:pass
                else:raise AssertionError('nonempty down accepted')
    print('PASS MESSAGE3: signed API/runtime role/run_once/FakeProvider, explicit Trip/version/day/item, foreign/stale/invalid rejection, ambiguity clarification, original replay/status/history/cancel/UNKNOWN and late source fence')


if __name__=='__main__':
    harness.exercise=exercise
    harness.main()
