"""One original worker, legacy and typed scopes; private PG/Fake, no cloud calls."""
import json
import base64
import hashlib
import os
import sys
from datetime import datetime,timezone
from unittest.mock import patch
import httpx
from fastapi.testclient import TestClient
from cj_agent.provider import FakeProvider
from cj_api.local_app import LocalDatabase,create_local_app,scope_for,ISSUER
from cj_memory.typed_local import TypedConfiguration
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_memory.typed_api import register_typed_routes
from cj_memory.runtime import RuntimeDenied
import local_history_pg as harness
from registered_host_support import RegisteredHost
sys.path.insert(0,str(harness.ROOT))
from deploy.hk.configuration import Runtime
import run_worker

A='m4-synthetic-worker-a';B='m4-synthetic-worker-b'


def check_legacy_message_preflight(api, host, database, configured_app):
    from contextlib import contextmanager
    import psycopg
    from cj_api.composition import CompositionUnavailable

    mid = 'worker-legacy'
    chat = harness.expect(api.put('/v1/conversations', params={'conversation_id': mid}, headers=host.headers[A]))
    headers = {**host.headers[A], 'Content-Type': 'application/octet-stream'}

    def body(message_id, sequence):
        return json.dumps(dict(version='MESSAGE-send.1', conversation_id=mid, message_id=message_id,
            text='Synthetic old scope without Memory', trip_id=None, creation_intent='none',
            expected_generation=chat['generation'], expected_sequence=sequence)).encode()

    original = body(mid, 0)
    with patch.object(database, '_open_runtime_connection', wraps=database._open_runtime_connection) as opened:
        accepted = harness.expect(api.post('/v1/messages', content=original, headers=headers))['receipt']
        candidate_count = opened.call_count
    assert accepted['input_sha256'] == hashlib.sha256(original).hexdigest()
    with patch('cj_api.local_account_admission_v2.request_scope_connection', return_value=None):
        baseline = configured_app()
    with TestClient(baseline) as client, patch.object(database, '_open_runtime_connection',
            wraps=database._open_runtime_connection) as opened:
        replay = harness.expect(client.post('/v1/messages', content=original, headers=headers))['receipt']
        baseline_count = opened.call_count
    assert replay == accepted and (baseline_count, candidate_count) == (4, 2)

    rejected_mid = 'legacy-budget-rejected'
    with patch.object(database, '_check_budget_account', side_effect=CompositionUnavailable('fixture budget missing')), \
            patch.object(database, '_provision_scope', wraps=database._provision_scope) as provision:
        rejected = harness.expect(api.post('/v1/messages', content=body(rejected_mid, 1), headers=headers), 503)
        assert rejected['error']['code'] == 'MESSAGE_UNAVAILABLE'
        provision.assert_not_called()

    preflight = database._message_preflight_transaction

    @contextmanager
    def lose_read_ack(connection):
        with preflight(connection) as cursor:
            yield cursor
        raise psycopg.OperationalError('fixture budget read acknowledgement lost')

    unknown_mid = 'legacy-budget-ack-unknown'
    with patch.object(database, '_message_preflight_transaction', lose_read_ack), \
            patch.object(database, '_provision_scope', wraps=database._provision_scope) as provision:
        unknown = harness.expect(api.post('/v1/messages', content=body(unknown_mid, 1), headers=headers), 503)
        assert unknown['error']['code'] == 'MESSAGE_UNAVAILABLE'
        provision.assert_not_called()
    with database.connect(scope_for(ISSUER, A)) as connection:
        assert connection.execute('SELECT message_id FROM cj_message_delivery WHERE message_id IN (%s,%s,%s) ORDER BY message_id',
                                  (mid, rejected_mid, unknown_mid)).fetchall() == [(mid,)]
    print('PASS original legacy POST physical checkouts 4 -> 2, receipt replay and budget/preflight fail-closed')
    return accepted


def check_legacy_sse_followup(api, host, database):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event as Signal
    from cj_message.domain import Service as MessageService
    from cj_run.core import Binding, Event, Service as RunService
    from cj_run.display_snapshot import DisplaySnapshotReader, RunSnapshotAdvanced
    from cj_run.postgres import Repository, RunScopeBusy

    scope = scope_for(ISSUER, A)
    messages = MessageService(database.message_repository(scope), new_run_id=lambda: None)
    runs = RunService(database.run_repository(scope), valid=lambda _: True)
    recover_original, read_original = Repository.recover, DisplaySnapshotReader.read
    invitations = host.auth / 'invited.json'
    original_invitations = invitations.read_bytes()
    source, body = 'Source: fixture\n', 'Body 样例'

    for scenario in ('advance', 'consecutive', 'revoked', 'scope-busy', 'scope-revoked'):
        mid = 'legacy-sse-' + scenario
        accepted = host.send(api, A, mid, 'Private PG protected stream')
        receipt = messages.query(mid).receipt
        assert accepted['run_id'] == receipt.run_id
        binding = Binding(scope, receipt.conversation_id, receipt.generation, mid, receipt.run_id, receipt.sequence)
        assert runs.accept(binding).status == 'queued'
        assert runs.apply(Event(binding, 1, 'start', 'started')).status == 'running'
        recoveries = []
        held, release = Signal(), Signal()
        holder = None

        def hold_scope():
            with database.connect(scope) as connection:
                assert connection.execute('SELECT epoch FROM cj_run_scope WHERE scope=%s FOR UPDATE', (scope,)).fetchone()
                held.set()
                assert release.wait(18)

        def recover(repository, candidate, **kwargs):
            nonlocal holder
            if candidate != binding:
                return recover_original(repository, candidate, **kwargs)
            call = len(recoveries) + 1
            if call == 3 and scenario in ('scope-busy', 'scope-revoked'):
                holder = executor.submit(hold_scope)
                assert held.wait(3)
            if call == 5 and scenario == 'advance':
                runs.apply(Event(binding, 3, 'answer', 'text_delta', body))
                runs.apply(Event(binding, 4, 'end', 'completed'))
            try:
                result = recover_original(repository, candidate, **kwargs)
            except RunScopeBusy:
                assert holder is not None
                recoveries.append('scope-busy')
                release.set()
                holder.result(timeout=3)
                runs.apply(Event(binding, 2, 'source', 'text_delta', source))
                runs.apply(Event(binding, 3, 'answer', 'text_delta', body))
                runs.apply(Event(binding, 4, 'end', 'completed'))
                raise
            recoveries.append(result.state.sequence)
            if call == 3:
                runs.apply(Event(binding, 2, 'source', 'text_delta', source))
            if call == 5 and scenario == 'consecutive':
                runs.apply(Event(binding, 3, 'hidden', 'text_delta', body))
            return result

        def read(reader, token, key):
            try:
                return read_original(reader, token, key)
            except (RunSnapshotAdvanced, RunScopeBusy):
                if scenario in ('revoked', 'scope-revoked'):
                    invitations.write_text(json.dumps([B]))
                raise

        params = {'message_id': mid}
        with ThreadPoolExecutor(max_workers=1) as executor:
            try:
                with patch.object(Repository, 'recover', recover), patch.object(DisplaySnapshotReader, 'read', read):
                    response = api.get('/v1/run-events', params=params, headers=host.headers[A])
            finally:
                release.set()
                invitations.write_bytes(original_invitations)
        assert response.status_code == 200
        frames = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
        if scenario in ('advance', 'scope-busy'):
            expected = [1, 1, 1, 2, 4, 4] if scenario == 'advance' else [1, 1, 'scope-busy', 4, 4]
            assert recoveries == expected
            assert frames == [{'status': 'running'}, {'text': source + body}, {'status': 'completed'}]
            resumed = api.get('/v1/run-events', params=params,
                              headers={**host.headers[A], 'Last-Event-ID': str(len(source.encode()))})
            assert resumed.status_code == 200 and resumed.text.count(body) == 1 and 'Source: fixture' not in resumed.text
            harness.expect(api.get('/v1/run-events', params=params, headers=host.headers[B]), 503)
        else:
            expected = {
                'consecutive': [1, 1, 1, 2, 2, 3],
                'revoked': [1, 1, 1, 2],
                'scope-revoked': [1, 1, 'scope-busy'],
            }
            assert recoveries == expected[scenario]
            assert frames == [{'status': 'running'}, {'status': 'unavailable'}]
    print('PASS original legacy SSE same-RUN advance, scope lock timeout, bounded follow-up, revocation and byte resume')


def exercise(auth,conninfo):
    host=RegisteredHost(auth,conninfo,{s:(8,2,50000) for s in (A,B)})
    path,context=host.profiles[A]
    database=LocalDatabase(conninfo,run_context=context,travel_context=True)
    app=create_local_app(conninfo_path=None,auth_dir=auth,database=database,run_context=context)
    def headers(s):return {**host.headers[s],'Content-Type':'application/octet-stream'}
    def expect(r):return harness.expect(r)
    with TestClient(app) as api:
        travels=[]
        for i in range(2):
            r=api.post('/v1/travel-context-actions',headers=headers(B),content=json.dumps(dict(
                version='TRAVEL-context-action.1',action_id='worker-travel-'+str(i),operation='create',travel_context=None)).encode())
            travels.append(expect(r)['receipt']['travel_context'])
    profile=dict(subjects=['self'],slots={'preference':dict(kind='preference',collection_allowed=True,semantic_resolved=True)},
                 extents=['long_term','current'],context_ids=[])
    policy=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',expires_at='2099-11-30T23:59:59+08:00',
        profiles={B:profile}),travel_contexts={B:[t['id'] for t in travels]})
    config=TypedRuntimeConfiguration.from_bytes(json.dumps(dict(version='local-memory-run.2',collection=policy,
        selections={B:dict(subject='self',slots=['preference'],max_bytes=1000)})).encode())
    runtime=Runtime(auth,context,path,[],subjects=frozenset((A,B)),memory_runtime=config)
    assert runtime.memory_configuration_for_scope(scope_for(ISSUER,A)) is None
    assert runtime.memory_configuration_for_scope(scope_for(ISSUER,B)) is config
    assert runtime.memory_configuration_for_scope(scope_for(ISSUER,'uninvited')) is None
    register_typed_routes(app,database=database,auth_dir=auth,configuration=TypedConfiguration.from_bytes(json.dumps(policy).encode()))
    api_runtime=Runtime(auth,context,path,[],typed_memory=config.collection,subjects=frozenset((A,B)),
                        typed_message_subjects=frozenset((B,)))
    def configured_app():
        with patch.dict(os.environ,dict(CJ_BETA_HISTORY_B64=base64.b64encode(b'h'*32).decode(),
            CJ_BETA_CONFIRMATION_B64=base64.b64encode(b'c'*32).decode())),patch.object(Runtime,'database',return_value=database):
            return api_runtime.app()
    def memory_rows():
        with database.connect(scope_for(ISSUER,B)) as c:
            return {table:c.execute('SELECT to_jsonb(t)::text FROM '+table+' t ORDER BY 1').fetchall()
                    for table in ('cj_memory_scope','cj_memory_item','cj_memory_source','cj_memory_operation')}
    class Recorded(FakeProvider):
        def __init__(self):super().__init__();self.inputs=[]
        def stream(self,messages,system=None):
            self.inputs.append(json.loads(json.dumps(messages)))
            yield from super().stream(messages,system)
    def send(api,tag,travel):
        head=expect(api.put('/v1/conversations',params={'conversation_id':tag},headers=host.headers[B]))
        raw=json.dumps(dict(version='MESSAGE-send.2',conversation_id=tag,message_id=tag,text='Synthetic original request '+tag,
            trip_id=None,creation_intent='none',expected_generation=head['generation'],expected_sequence=0,
            travel_context=None if travel is None else dict(id=travel['id'],expected_version=travel['version']),needs_reference=None)).encode()
        original=expect(api.post('/v2/messages',content=raw,headers=headers(B)))
        assert original['receipt']['input_sha256']==hashlib.sha256(raw).hexdigest()
        found=expect(api.get('/v2/message-send-status',params={'conversation_id':tag,'message_id':tag},headers=host.headers[B]))
        assert found['receipt']==original['receipt'] and found['reference']==original['reference']
        return original
    with TestClient(app) as api:
        for i,travel in enumerate((None,*travels)):
            raw=json.dumps(dict(version='MEMORY-manual.2',operation_id='worker-save-'+str(i),item_id='worker-item-'+str(i),
                subject='self',slot='preference',kind='preference',text=('LONG_ONLY','CURRENT_ONE_ONLY','CURRENT_TWO_ONLY')[i],
                extent='long_term' if travel is None else 'current',occurred_at='date unknown',
                context=None if travel is None else dict(kind='travel',id=travel['id'],expected_version=travel['version']))).encode()
            expect(api.post('/v2/memories',content=raw,headers=headers(B)))
        before=memory_rows()
        try:configured_app()
        except ValueError as e:assert str(e)=='original_typed_message_travel_profile_required'
        else:raise AssertionError('configured API bypassed missing canonical Travel profile')
        try:harness.dev_auth.activate_travel(conninfo,B,context,'MESSAGE-TRAVEL-CONSUMER@1')
        except ValueError:pass
        else:raise AssertionError('old activation accepted existing Memory without its consumer')
        try:harness.dev_auth.activate_travel(conninfo,A,context,'MESSAGE-TRAVEL-CONSUMER@1',
            typed_memory_configuration=config,auth_dir=auth)
        except RuntimeDenied:pass
        else:raise AssertionError('unconfigured foreign owner activated with B consumer')
        for options in (dict(typed_memory_configuration=object(),auth_dir=auth),
                        dict(typed_memory_configuration=config)):
            try:harness.dev_auth.activate_travel(conninfo,B,context,'MESSAGE-TRAVEL-CONSUMER@1',**options)
            except ValueError:pass
            else:raise AssertionError('activation accepted a noncanonical consumer or missing AUTH')
        expired=json.loads(json.dumps(policy));expired['collection']['expires_at']='2000-01-01T00:00:00+00:00'
        expired_config=TypedRuntimeConfiguration.from_bytes(json.dumps(dict(version='local-memory-run.2',collection=expired,
            selections={B:dict(subject='self',slots=['preference'],max_bytes=1000)})).encode())
        try:harness.dev_auth.activate_travel(conninfo,B,context,'MESSAGE-TRAVEL-CONSUMER@1',
            typed_memory_configuration=expired_config,auth_dir=auth)
        except RuntimeDenied:pass
        else:raise AssertionError('expired policy enabled an existing Memory consumer')
        missing=json.loads(json.dumps(policy));missing['collection']['profiles']={A:profile};missing['travel_contexts']={A:[]}
        missing_config=TypedRuntimeConfiguration.from_bytes(json.dumps(dict(version='local-memory-run.2',collection=missing,
            selections={A:dict(subject='self',slots=['preference'],max_bytes=1000)})).encode())
        try:harness.dev_auth.activate_travel(conninfo,A,context,'MESSAGE-TRAVEL-CONSUMER@1',
            typed_memory_configuration=missing_config,auth_dir=auth)
        except RuntimeDenied:pass
        else:raise AssertionError('readonly activation provisioned a missing Memory namespace')
        assert memory_rows()==before
        assert not database.travel_profile(scope_for(ISSUER,A)) and not database.travel_profile(scope_for(ISSUER,B))
        # The operator uses the existing table owner, never a runtime GRANT.
        assert harness.dev_auth.activate_travel(conninfo,B,context,'MESSAGE-TRAVEL-CONSUMER@1',
            typed_memory_configuration=config,auth_dir=auth)=='activated'
        assert harness.dev_auth.activate_travel(conninfo,B,context,'MESSAGE-TRAVEL-CONSUMER@1',
            typed_memory_configuration=config,auth_dir=auth)=='existing'
        assert memory_rows()==before
        with database.connect(scope_for(ISSUER,B)) as c:
            assert c.execute("SELECT has_table_privilege(current_user,'cj_message_context_profile','INSERT'),has_table_privilege(current_user,'cj_message_context_profile','UPDATE')").fetchone()==(False,False)
    params={'limit':10}
    with TestClient(app) as baseline,patch.object(database,'_open_runtime_connection',wraps=database._open_runtime_connection) as opened:
        original_items=expect(baseline.get('/v2/memories',params=params,headers=headers(B)))['items']
        original_checkouts=opened.call_count
    with patch('cj_api.supabase_test_database.current_authorization') as authorize:
        with TestClient(configured_app()) as leased,patch.object(database,'_open_runtime_connection',wraps=database._open_runtime_connection) as opened:
            assert expect(leased.get('/v2/memories',params=params,headers=headers(B)))['items']==original_items
            assert opened.call_count<original_checkouts
            assert authorize.call_count>1
            authorization_calls=authorize.call_count
            expect(leased.get('/v2/memory-items',params={'item_id':'worker-item-0'},headers=headers(B)))
            assert authorize.call_count==authorization_calls
            harness.expect(leased.get('/v2/memories',params=params,headers=headers(A)),503)
    print('PASS HK typed list preserves original items with fewer checkouts; detail and foreign behavior unchanged')
    with TestClient(configured_app()) as api:
        old=check_legacy_message_preflight(api, host, database, configured_app)
        current=send(api,'worker-current-one',travels[0])
        # Compare two reads of the same original through its idempotent POST
        # path. Count fresh checkouts, not cached admission verdicts.
        from contextlib import nullcontext
        with patch('cj_api.local_account_admission_v2.permit_retirement_read_lease',return_value=nullcontext()):
            baseline_post=configured_app()
        original=current['receipt']
        replay=json.dumps(dict(version='MESSAGE-send.2',conversation_id=original['conversation_id'],
            message_id=original['message_id'],text='Synthetic original request worker-current-one',
            trip_id=None,creation_intent='none',expected_generation=original['generation'],expected_sequence=0,
            travel_context=dict(id=travels[0]['id'],expected_version=travels[0]['version']),needs_reference=None)).encode()
        with TestClient(baseline_post) as baseline,patch.object(database,'_open_runtime_connection',
                wraps=database._open_runtime_connection) as opened:
            assert expect(baseline.post('/v2/messages',content=replay,headers=headers(B)))['receipt']==original
            fresh_baseline=opened.call_count
        with patch.object(database,'_open_runtime_connection',wraps=database._open_runtime_connection) as opened:
            assert expect(api.post('/v2/messages',content=replay,headers=headers(B)))['receipt']==original
            fresh_leased=opened.call_count
        assert fresh_leased<fresh_baseline,(fresh_baseline,fresh_leased)
        print(f'PASS original typed POST fresh checkouts {fresh_baseline} -> {fresh_leased}; original receipt retained')
        from cj_auth.interfaces import Fact
        with patch('cj_api.local_account_admission_v2._retirement_fact',
                side_effect=(Fact.NO,Fact.NO,Fact.NO,Fact.YES)) as retirement:
            denied=harness.expect(api.post('/v2/messages',content=replay,headers=headers(B)),503)
            assert denied['error']['code']=='MESSAGE_OUTCOME_UNKNOWN' and retirement.call_count==4
        assert expect(api.get('/v2/message-send-status',
            params={'conversation_id':original['conversation_id'],'message_id':original['message_id']},
            headers=headers(B)))['receipt']==original
        model=Recorded()
        results=run_worker.run_once(database,model,auth,memory_configuration_for_scope=runtime.memory_configuration_for_scope)
        assert {r.message_id:r.status for r in results}=={'worker-legacy':'completed','worker-current-one':'completed'},results
        assert model.calls==2
        plain,typed=['\n'.join(m['content'] for m in rows) for rows in model.inputs]
        assert all(text not in plain for text in ('LONG_ONLY','CURRENT_ONE_ONLY','CURRENT_TWO_ONLY'))
        assert 'CURRENT_ONE_ONLY' in typed and 'CURRENT_TWO_ONLY' not in typed and 'LONG_ONLY' not in typed
        payload=json.loads(model.inputs[1][0]['content'].split('\n',1)[1])
        assert payload['version']=='MEMORY-RUN-CONSUME@2'
        assert payload['items'][0]['context']==dict(kind='travel',id=travels[0]['id'])
        second=send(api,'worker-current-two',travels[1]);model=Recorded()
        assert [r.status for r in run_worker.run_once(database,model,auth,memory_configuration_for_scope=runtime.memory_configuration_for_scope)]==['completed']
        content='\n'.join(m['content'] for m in model.inputs[0])
        assert 'CURRENT_TWO_ONLY' in content and 'CURRENT_ONE_ONLY' not in content and 'LONG_ONLY' not in content
        none=send(api,'worker-no-travel',None);model=Recorded()
        assert [r.status for r in run_worker.run_once(database,model,auth,memory_configuration_for_scope=runtime.memory_configuration_for_scope)]==['completed']
        assert 'LONG_ONLY' in model.inputs[0][0]['content'] and 'CURRENT_ONE_ONLY' not in str(model.inputs)
        # Existing Memory without its explicit resolver cannot fall back to plain.
        pending=send(api,'worker-held',travels[0]);blocked=Recorded();before=host.ledger(B)
        try:run_worker.run_once(database,blocked,auth)
        except RuntimeDenied:pass
        else:raise AssertionError('missing Memory configuration dispatched a plain model')
        assert blocked.calls==0 and host.ledger(B)==before
        try:run_worker.run_once(database,blocked,auth,memory_configuration=config,
            memory_configuration_for_scope=runtime.memory_configuration_for_scope)
        except ValueError:pass
        else:raise AssertionError('mixed global and scope Memory configurations accepted')
        assert blocked.calls==0 and host.ledger(B)==before
        # The same original pending action executes once when explicitly configured.
        assert [r.status for r in run_worker.run_once(database,blocked,auth,
            memory_configuration_for_scope=runtime.memory_configuration_for_scope)]==['completed']
        assert blocked.calls==1
        assert run_worker.run_once(database,blocked,auth,memory_configuration_for_scope=runtime.memory_configuration_for_scope)==[]
        assert blocked.calls==1
        for original in (current,second,none,pending):
            receipt=original['receipt']
            value=expect(api.get('/v2/run-display',params={'message_id':receipt['message_id']},headers=host.headers[B]))
            assert value['reference']==original['reference']
            display=value['snapshot']
            assert display['run_id']==receipt['run_id'] and display['text']
        stream_params={'message_id':none['receipt']['message_id']}
        with TestClient(baseline_post) as baseline,patch.object(database,'_open_runtime_connection',
                wraps=database._open_runtime_connection) as opened:
            baseline_stream=baseline.get('/v2/run-events',params=stream_params,headers=host.headers[B])
            baseline_stream_checkouts=opened.call_count
        with patch.object(database,'_open_runtime_connection',wraps=database._open_runtime_connection) as opened, \
                patch.object(database,'_check_execution_connection',wraps=database._check_execution_connection) as checked:
            stream=api.get('/v2/run-events',params=stream_params,headers=host.headers[B])
            leased_stream_checkouts=opened.call_count
        assert leased_stream_checkouts <= 2 and checked.call_count == 5
        assert stream.content==baseline_stream.content
        assert leased_stream_checkouts<baseline_stream_checkouts,(baseline_stream_checkouts,leased_stream_checkouts)
        print(f'PASS original typed SSE snapshot fresh checkouts {baseline_stream_checkouts} -> {leased_stream_checkouts}')
        assert stream.status_code==200 and stream.headers['content-type'].startswith('text/event-stream')
        frames=[json.loads(line[6:]) for line in stream.text.splitlines() if line.startswith('data: ')]
        body=expect(api.get('/v2/run-display',params=stream_params,headers=host.headers[B]))['snapshot']['text']
        assert frames==[{'text':body},{'status':'completed'}]
        resumed=api.get('/v2/run-events',params=stream_params,
            headers={**host.headers[B],'Last-Event-ID':str(len(body.encode('utf8')))})
        assert resumed.status_code==200 and 'event: delta' not in resumed.text
        assert 'data: {"status":"completed"}' in resumed.text
        harness.expect(api.get('/v2/run-events',params=stream_params,
            headers={**host.headers[B],'Last-Event-ID':str(len(body.encode('utf8'))+1)}),409)
        harness.expect(api.get('/v2/run-events',params=stream_params,headers=host.headers[A]),503)
        harness.expect(api.get('/v1/run-events',params=stream_params,headers=host.headers[B]),503)
        old_params={'message_id':old['message_id']}
        harness.expect(api.get('/v2/run-events',params=old_params,headers=host.headers[A]),503)
        with TestClient(baseline_post) as baseline,patch.object(database,'_open_runtime_connection',
                wraps=database._open_runtime_connection) as opened:
            old_baseline=baseline.get('/v1/run-events',params=old_params,headers=host.headers[A])
            old_checkouts=opened.call_count
        with patch.object(database,'_open_runtime_connection',wraps=database._open_runtime_connection) as opened, \
                patch.object(database,'_check_execution_connection',wraps=database._check_execution_connection) as checked:
            old_stream=api.get('/v1/run-events',params=old_params,headers=host.headers[A])
            old_leased_checkouts=opened.call_count
        assert old_leased_checkouts <= 2 and checked.call_count == 5
        assert old_stream.status_code==old_baseline.status_code==200
        assert old_stream.content==old_baseline.content
        assert old_leased_checkouts<old_checkouts,(old_checkouts,old_leased_checkouts)
        print(f'PASS original legacy SSE fresh checkouts {old_checkouts} -> {old_leased_checkouts}')
        validate = database._check_execution_connection

        def retain_fixture_scope(cursor):
            validate(cursor)
            cursor.execute("SELECT set_config('cj.usage_scope', 'stale-fixture-scope', false)")

        with patch.object(database, '_check_execution_connection', side_effect=retain_fixture_scope) as checked:
            denied = api.get('/v1/run-events', params=old_params, headers=host.headers[A])
        assert denied.status_code == 503 and checked.call_count == 1
        assert api.get('/v1/run-events', params=old_params, headers=host.headers[A]).content == old_stream.content
        print('PASS retained session scope is rejected; a separate original read remains available')
        with database.connect(scope_for(ISSUER,A)) as c:
            assert c.execute('SELECT count(*) FROM cj_memory_item').fetchone()==(0,)
        with database.connect(scope_for(ISSUER,B)) as c:
            assert c.execute('SELECT count(*) FROM cj_message_delivery WHERE NOT acknowledged').fetchone()==(0,)
        assert old['run_id']==host.display(api,A,'worker-legacy')['run_id']
        # The accepted real adapter stays on its original wrapper/registrations.
        # HTTP fixtures prove the composition, not a live model/tool result.
        from cj_agent.provider import DashScopeConfig,MeteredDashScopeProvider,M4_BASE,M4_MODEL
        from cj_api.real_services import RealServices,RealTools
        from cj_usage.authorization_budget import AuthorizationBudget
        from cj_place.gaode import Response
        from cj_place.https_transport import TransportResult
        from test_m4_real_services import turn_sse,KEY,NOW
        budget=AuthorizationBudget(auth.parent/'fixture-only-authorization',clock=lambda:NOW)
        calls=[];tools=[]
        def response(request):
            body=json.loads(request.content);calls.append(body)
            content=json.dumps(body['messages'])
            assert 'CURRENT_ONE_ONLY' in content and 'CURRENT_TWO_ONLY' not in content and 'LONG_ONLY' not in content
            follow=any(m['role']=='tool' for m in body['messages'])
            return httpx.Response(200,stream=httpx.ByteStream(turn_sse(tool=not follow,compact=True).replace(
                'chatcmpl-synthetic','chatcmpl-worker-'+str(len(calls))).encode()))
        async def place(config,request,credentials,*,before_send=None,basic=False):
            tools.append(request.request_ref)
            raw=json.dumps(dict(status='1',info='OK',infocode='10000',count='1',pois=[dict(
                id='SYNTH_ONLY',name='Synthetic fixture only',location='116.1,39.1')])).encode()
            return TransportResult('received','fixture',Response(request.binding_digest,request.origin,request.path,200,raw,datetime.now(timezone.utc)))
        native=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,KEY),budget,transport=httpx.MockTransport(response))
        services=RealServices(native,KEY,frozenset((A,B)));registered=RealTools(services)
        original=send(api,'worker-native-fixture',travels[0])
        with patch('cj_api.real_services.fetch_candidate',place):
            outcomes=run_worker.run_once(database,native,auth,tools_configuration=registered,real_services=services,
                memory_configuration_for_scope=runtime.memory_configuration_for_scope)
        assert [o.status for o in outcomes]==['completed'],outcomes
        assert len(calls)==2 and len(tools)==1
        assert [(r['kind'],r['state']) for r in budget.inspect()]==[('model','RECEIVED'),('place','RECEIVED'),('model','RECEIVED')]
        display=expect(api.get('/v2/run-display',params={'message_id':'worker-native-fixture'},headers=host.headers[B]))['snapshot']
        assert display['run_id']==original['receipt']['run_id'] and 'Needs verification.' in display['text']
        assert run_worker.run_once(database,native,auth,tools_configuration=registered,real_services=services,
            memory_configuration_for_scope=runtime.memory_configuration_for_scope)==[]
        assert len(calls)==2 and len(tools)==1
        check_legacy_sse_followup(api, host, database)
    print('PASS HK single worker/legacy and typed scopes/original signed MESSAGE2/owned travel lease/selected Memory/isolated input/held original resume/no duplicate calls; real providers UNRUN')


if __name__=='__main__':
    harness.exercise=exercise;harness.main()
