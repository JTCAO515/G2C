"""HK host + canonical C typed routes, real restricted PG and signed identities."""
import base64
from contextlib import contextmanager
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
import uuid
from fastapi.testclient import TestClient
from cj_api.local_app import LocalDatabase,ISSUER,scope_for
from cj_api.composition import CompositionUnavailable
from cj_api.local_worker_context import checker_for
import local_history_pg as harness
from registered_host_support import RegisteredHost
sys.path.insert(0,str(harness.ROOT))
from deploy.hk import configuration

A='m4-synthetic-hk-a';B='m4-synthetic-hk-b'
class Clock(datetime):
    @classmethod
    def now(cls,tz=None):return datetime(2026,11,6,8,tzinfo=timezone.utc)


def exercise(auth,conninfo):
    host=RegisteredHost(auth,conninfo,{s:(8,2,50000) for s in (A,B)})
    context_path,context=host.profiles[A]
    database=LocalDatabase(conninfo,run_context=context,travel_context=True)
    common=dict(CJ_ENV='local',CJ_DEPLOY_TARGET='hk-beta',CJ_M4_SYNTHETIC_ONLY='1',
        CJ_TRIAL_VALID_UNTIL='2027-02-03T00:00:00+08:00',CJ_BETA_SUBJECTS_JSON=json.dumps([A,B]),
        CJ_BETA_SIGNING_PUBLIC_B64=base64.b64encode((auth/'public.pem').read_bytes()).decode(),
        CJ_BETA_RUN_CONTEXT_JSON=context_path.read_text())
    required=dict(CJ_SUPABASE_RUNTIME_URI='synthetic-private-PG-transport-only',
        CJ_BETA_HISTORY_B64=base64.b64encode(b'h'*32).decode(),CJ_BETA_CONFIRMATION_B64=base64.b64encode(b'c'*32).decode())
    @contextmanager
    def app(policy=None):
        directory=auth.parent/('api-secrets-'+uuid.uuid4().hex);directory.mkdir(mode=0o700)
        values=dict(required)
        if policy is not None:values[configuration.TYPED_POLICY]=base64.b64encode(json.dumps(policy).encode()).decode()
        p=directory/'api.env';p.write_text('\n'.join(k+'='+v for k,v in values.items())+'\n');p.chmod(0o600)
        with patch.dict(os.environ,common),patch.object(configuration,'datetime',Clock),patch.object(configuration.Runtime,'database',return_value=database):
            for name in {*required,configuration.TYPED_POLICY}:os.environ.pop(name,None)
            configuration.load_secret_environment('api',root=directory)
            runtime=configuration.Runtime.load(directory/'runtime')
            try:
                with TestClient(runtime.app()) as client:yield client
            finally:runtime.close()
    def headers(subject):return {**host.headers[subject],'Content-Type':'application/octet-stream'}
    def create(client,subject,tag):
        r=client.post('/v1/travel-context-actions',headers=headers(subject),content=json.dumps(dict(
            version='TRAVEL-context-action.1',action_id=tag,operation='create',travel_context=None)).encode())
        return harness.expect(r)['receipt']['travel_context']
    with app() as client:
        assert client.get('/v2/memories',params={'limit':100},headers=host.headers[B]).status_code!=200
        contexts=[create(client,B,'hk-typed-travel-'+str(i)) for i in range(2)]
        foreign=create(client,A,'hk-foreign-travel')
    profile=dict(subjects=['self'],slots={'preference':dict(kind='preference',collection_allowed=True,semantic_resolved=True)},
                 extents=['long_term','current'],context_ids=[])
    policy=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',expires_at='2099-11-30T23:59:59+08:00',profiles={B:profile}),
        travel_contexts={B:[c['id'] for c in [*contexts,foreign]]})
    def save_raw(tag,travel=None):
        return json.dumps(dict(version='MEMORY-manual.2',operation_id='hk-op-'+tag,item_id='hk-item-'+tag,
            subject='self',slot='preference',kind='preference',text='Synthetic preference '+tag,
            extent='long_term' if travel is None else 'current',occurred_at='date unknown',
            context=None if travel is None else dict(kind='travel',id=travel['id'],expected_version=travel['version'])),separators=(',',':')).encode()
    with app(policy) as client:
        raw=save_raw('long');first=harness.expect(client.post('/v2/memories',headers=headers(B),content=raw))['receipt']
        original=harness.expect(client.get('/v2/memory-receipts',params={'operation_id':'hk-op-long'},headers=host.headers[B]))['receipt']
        assert original==first
        for i,travel in enumerate(contexts):
            harness.expect(client.post('/v2/memories',headers=headers(B),content=save_raw('current-'+str(i),travel)))
        for i,travel in enumerate(contexts):
            item=harness.expect(client.get('/v2/memory-items',params={'item_id':'hk-item-current-'+str(i)},headers=host.headers[B]))['item']
            assert item['command']['context']==dict(kind='travel',id=travel['id'],expected_version=travel['version'])
        # Even deliberately overbroad operator policy cannot grant a foreign
        # Travel: the original owner/lease is still authoritative.
        rejected=client.post('/v2/memories',headers=headers(B),content=save_raw('foreign',foreign))
        assert rejected.status_code!=200
        assert client.get('/v2/memories',params={'limit':100},headers=host.headers[A]).status_code!=200
        action=dict(version='MEMORY-management.2',action_id='hk-pause',operation='pause',
                    item_id='hk-item-long',expected_version=1,expected_source_version=1)
        pause=harness.expect(client.post('/v2/memory-management-actions',headers=headers(B),content=json.dumps(action).encode()))['receipt']
        assert pause['version']==2 and pause['status']=='disabled'
        queried=harness.expect(client.get('/v2/memory-management-receipts',params={'action_id':'hk-pause'},headers=host.headers[B]))['receipt']
        assert queried==pause
        action.update(action_id='hk-resume',operation='resume',expected_version=2)
        assert harness.expect(client.post('/v2/memory-management-actions',headers=headers(B),content=json.dumps(action).encode()))['receipt']['version']==3
        # The API-only cohort never reaches a MESSAGE producer or worker queue.
        assert client.put('/v1/conversations',params={'conversation_id':'hk-blocked'},headers=host.headers[B]).status_code==503
        denied=dict(version='MESSAGE-send.1',conversation_id='hk-blocked',message_id='hk-blocked',text='Synthetic blocked input',
            trip_id=None,creation_intent='none',expected_generation='0'*32,expected_sequence=0)
        assert client.post('/v1/messages',headers=headers(B),content=json.dumps(denied).encode()).status_code==503
        with database.connect(scope_for(ISSUER,B)) as c:
            assert c.execute('SELECT count(*) FROM cj_message_receipt').fetchone()==(0,)
            assert c.execute('SELECT count(*) FROM cj_message_chat').fetchone()==(0,)
            assert c.execute("SELECT count(*) FROM cj_memory_operation WHERE operation_id='hk-op-foreign'").fetchone()==(0,)
            assert bytes(c.execute("SELECT original_input FROM cj_memory_operation WHERE operation_id='hk-op-long'").fetchone()[0])==raw
        # Existing plain subject remains the original signed MESSAGE/Fake path.
        accepted=host.send(client,A,'hk-plain-message','Synthetic existing plain subject')
        from cj_agent.provider import FakeProvider
        import run_worker
        worker=run_worker._worker_for_scope(database,FakeProvider(),auth,scope_for(ISSUER,A),
            checker_for(auth))
        assert worker.process()[0].status=='completed'
        assert host.display(client,A,'hk-plain-message')['run_id']==accepted['run_id']
    # Persisted Memory cannot silently reopen an old unconfigured MESSAGE host.
    try:
        with app():pass
    except ValueError as e:assert str(e)=='existing_beta_memory_requires_explicit_policy'
    else:raise AssertionError('missing policy reopened an incompatible beta host')
    invalid=dict(policy,version='UNKNOWN')
    try:
        with app(invalid):pass
    except ValueError:pass
    else:raise AssertionError('invalid typed policy accepted')
    outside=json.loads(json.dumps(policy));outside['collection']['profiles']={'m4-synthetic-uninvited':profile};outside['travel_contexts']={'m4-synthetic-uninvited':[]}
    try:
        with app(outside):pass
    except ValueError:pass
    else:raise AssertionError('typed policy outside original invites accepted')
    print('PASS HK canonical typed cohost/real PG/original bytes/owned Travel/foreign lease/management/old subject and pre-queue gate/default-off/policy negatives; no real providers')

if __name__=='__main__':
    harness.exercise=exercise;harness.main()
