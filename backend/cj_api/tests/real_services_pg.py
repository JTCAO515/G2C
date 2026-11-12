"""Real PG/RUN/Meter with native HTTP fixtures; no live key/network/cost."""
import asyncio,json,os,time
from hashlib import sha256
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
from threading import Event
from unittest.mock import patch

import httpx
import psycopg
import uuid
from fastapi.testclient import TestClient

from cj_agent.provider import DashScopeConfig,MeteredDashScopeProvider,M4_BASE,M4_MODEL,M4_TURN_FUNCTION_V2,M4_REAL_OUTPUT_TOKENS
from cj_api.real_services import RealServices,RealTools
from cj_api.tool_evidence import ToolEvidence
from cj_api.local_app import LocalDatabase,app_from_environment,create_local_app,scope_for,ISSUER
from cj_api.local_run_context import load_run_context
from cj_place.gaode import Response
from cj_place.https_transport import TransportResult
from cj_usage.authorization_budget import AuthorizationBudget
from cj_usage.codec import decode
from cj_run.step_usage import ledger_scope_for
import local_history_pg as harness
import local_run_context as operator
import run_worker
from test_m4_real_services import sse,turn_sse,KEY,NOW


def exercise(auth,conninfo):
    subjects=['m4-synthetic-'+v for v in ('ok','limit','unknown','malformed','late','permission','revoke','repeat','tail','tailbad','batch','batchfail','stop','guard-unknown','progress','run-commit-unknown','stream','stream-mixed')]
    assembly_pair=tuple('m4-synthetic-660-0123456789ab-'+lang for lang in ('zh','en'))
    subjects.extend((*assembly_pair,'m4-synthetic-stream-buffered-mixed','m4-synthetic-stream-buffered-late-mixed'))
    original_subjects=tuple(subjects)
    subjects.extend(('m4-synthetic-runtime-reflection','m4-synthetic-runtime-factory'))
    harness.dev_auth.init(auth,subjects)
    now=int(time.time());profiles={}
    for subject in subjects:
        value=dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(unit='provider_call',budget=20,
            period_start=now-60,period_end=now+3600,max_steps=1 if subject.endswith('limit') else 8,
            max_tools=8 if subject.endswith(('tail','tailbad')) else 4,max_output=30000,max_seconds=1 if subject.endswith('late') else 300),output_limits=dict(model=12000,tool=24000,memory=1000)),history=[])
        if subject.endswith(('tail','tailbad')):value['current']['meter'].update(max_steps=16,max_output=65536)
        path=auth.parent/(subject+'.json');path.write_text(json.dumps(value))
        profiles[subject]=(path,load_run_context(path));operator.provision_budget(conninfo,profiles[subject][1],subject)
    headers={s:dict(Authorization='Bearer '+harness.dev_auth.token(auth,s,30)) for s in subjects}
    tool_calls=[];model_calls=[]
    async def place(config,request,credentials,*,before_send=None,basic=False):
        tool_calls.append(request.request_ref)
        if subject.endswith('batchfail') and request.query.keyword=='synthetic-B':raise OSError('synthetic second source failed after admission')
        raw=json.dumps(dict(status='1',info='OK',infocode='10000',count='1',pois=[dict(id='SYNTH_ONLY',name='合成资料',location='116.1,39.1')])).encode()
        if subject.endswith('permission'):raw=b'{"status":"0","info":"INSUFFICIENT_PRIVILEGES","infocode":"10012"}'
        return TransportResult('received','fixture',Response(request.binding_digest,request.origin,request.path,200,raw,datetime.now(timezone.utc)))
    def api(s):
        with patch.dict(os.environ,dict(CJ_LOCAL_AUTH_DIR=str(auth),CJ_LOCAL_CONNINFO=str(conninfo),CJ_LOCAL_RUN_CONTEXT=str(profiles[s][0]))):
            return TestClient(app_from_environment())
    def send(client,s,text='Find synthetic Beijing place'):
        chat=harness.expect(client.put('/v1/conversations',params=dict(conversation_id=s),headers=headers[s]))
        raw=json.dumps(dict(version='MESSAGE-send.1',conversation_id=s,message_id=s,text=text,trip_id=None,
            creation_intent='none',expected_generation=chat['generation'],expected_sequence=0)).encode()
        return harness.expect(client.post('/v1/messages',content=raw,headers={**headers[s],'Content-Type':'application/octet-stream'}))['receipt']
    for subject in original_subjects:
        budget=AuthorizationBudget(auth.parent/subject,clock=lambda:NOW)
        legacy_stream=subject.endswith(('stream','stream-mixed'))
        buffered='stream-buffered' in subject
        incremental=legacy_stream or buffered or subject in assembly_pair
        mixed=subject.endswith('stream-mixed')
        paused,release=Event(),Event()
        prefix='Synthetic visible answer before the provider completes; '
        suffix='the final fragment follows.'

        class PausedAnswer(httpx.SyncByteStream):
            def __iter__(self):
                body=sse(tool=mixed).splitlines(keepends=True)
                if mixed:
                    first=json.loads(body[0][6:])
                    first['choices'][0]['delta']={'content':prefix}
                else:
                    first=json.loads(body[0][6:])
                    first['id']='chatcmpl-synthetic-answer'
                    first['choices'][0]['delta']={'content':prefix}
                yield ('data: '+json.dumps(first)+'\n\n').encode()
                paused.set()
                if not release.wait(12):raise TimeoutError('synthetic partial response release expired')
                if mixed:
                    yield ''.join(body).encode()
                else:
                    first['choices'][0]['delta']={'content':suffix}
                    yield ('data: '+json.dumps(first)+'\n\n').encode()
                    yield ''.join(body[2:]).replace('chatcmpl-synthetic','chatcmpl-synthetic-answer').encode()

        def response(request):
            model_calls.append(subject)
            if subject.endswith('unknown') and not subject.endswith('run-commit-unknown'):
                raise httpx.ReadTimeout('synthetic unknown')
            body=json.loads(request.content)
            if incremental:
                assert body['tool_choice']=='auto' and body['parallel_tool_calls']
                assert 'response_format' not in body
                if mixed:return httpx.Response(200,stream=PausedAnswer())
                if body['messages'][-1]['role']!='tool':
                    data=sse(tool=True).splitlines(keepends=True)
                    first=json.loads(data[0][6:])
                    calls=first['choices'][0]['delta']['tool_calls']
                    second=dict(calls[0],index=1,id='call_second',function=dict(name='place_search',
                        arguments=json.dumps(dict(keyword='synthetic-two',city='北京',page=1,page_size=1))))
                    calls.append(second)
                    if buffered:
                        if subject.endswith('late-mixed'):
                            preface={**first,'choices':[{'delta':{'content':'Speculative same-turn text must stay private'}}]}
                            data.insert(0,'data: '+json.dumps(preface)+'\n\n')
                            data[1]='data: '+json.dumps(first)+'\n'
                            return httpx.Response(200,stream=httpx.ByteStream(''.join(data).encode()))
                        first['choices'][0]['delta']['content']='Speculative same-turn text must stay private'
                    return httpx.Response(200,stream=httpx.ByteStream(('data: '+json.dumps(first)+'\n'+''.join(data[1:])).encode()))
                assistant,*replies=body['messages'][-3:]
                if buffered:assert assistant['content'] is None
                assert [c['function']['name'] for c in assistant['tool_calls']]==['place_search','place_search']
                assert [r['tool_call_id'] for r in replies]==[c['id'] for c in assistant['tool_calls']]
                assert [json.loads(r['content'])['results'][0]['index'] for r in replies]==[0,1]
                return httpx.Response(200,stream=PausedAnswer())
            assert body['tool_choice']=={'type':'function','function':{'name':M4_TURN_FUNCTION_V2}}
            assert 'response_format' not in body
            follow=any(m['role']=='tool' and 'tool_call_id' in m for m in body['messages'])
            if follow:
                assistant=next(m for m in reversed(body['messages']) if m['role']=='assistant')
                result=body['messages'][-1]
                assert result['role']=='tool' and result['tool_call_id']==assistant['tool_calls'][0]['id']
                assert assistant['tool_calls'][0]['function']['name']==M4_TURN_FUNCTION_V2
                prior=json.loads(assistant['tool_calls'][0]['function']['arguments'])
                assert prior['calls'][0]['name']=='place_search'
                assert json.loads(result['content'])['results'][0]['name']=='place_search'
                if subject.endswith('batch'):
                    results=json.loads(result['content'])['results']
                    assert [(r['index'],r['name']) for r in results]==[(0,'place_search'),(1,'place_search')]
                if subject.endswith('ok'):assert assistant['content']=='Synthetic preface; checking the location.'
            if subject.endswith('revoke') and not follow:
                (auth/'invited.json').write_text(json.dumps([s for s in subjects if s!=subject]))
            payload=turn_sse(tool=not follow or subject.endswith('repeat'),compact=True).replace('chatcmpl-synthetic','chatcmpl-synthetic-'+str(len(model_calls)))
            if subject.endswith(('batch','batchfail')) and not follow:
                event=json.loads(payload.splitlines()[0][6:]);call=event['choices'][0]['delta']['tool_calls'][0]
                turn=json.loads(call['function']['arguments']);first=turn['calls'][0]
                turn['calls']=[dict(name=first['name'],arguments={**first['arguments'],'keyword':word}) for word in ('synthetic-A','synthetic-B')]
                call['function']['arguments']=json.dumps(turn)
                payload='data: '+json.dumps(event)+'\n\n'+'\n'.join(payload.splitlines()[2:])
            if subject.endswith(('tail','tailbad')):
                final=set(body['tools'][0]['function']['parameters']['properties'])=={'answer'}
                assert final==(sum(m['role']=='tool' for m in body['messages'])==7)
                payload=turn_sse(tool=not final or subject.endswith('tailbad'),compact=True).replace('chatcmpl-synthetic','chatcmpl-synthetic-'+str(len(model_calls)))
                if not final or subject.endswith('tailbad'):
                    event=json.loads(payload.splitlines()[0][6:]);call=event['choices'][0]['delta']['tool_calls'][0]
                    call['id']='call_synthetic_'+str(len(model_calls))
                    turn=json.loads(call['function']['arguments'])
                    turn['calls'][0]['arguments']['keyword']='synthetic-'+str(len(model_calls))
                    call['function']['arguments']=json.dumps(turn)
                    payload='data: '+json.dumps(event)+'\n\n'+'\n'.join(payload.splitlines()[2:])
            if subject.endswith('ok') and not follow:
                value=json.loads(payload.splitlines()[0][6:]);value['choices'][0]['delta']['content']='Synthetic preface; checking the location.'
                payload='data: '+json.dumps(value)+'\n\n'+'\n'.join(payload.splitlines()[2:])
            if subject.endswith('malformed'):payload=payload.replace('\\"page\\": 1','\\"page\\": \\"bad\\"')
            if subject.endswith('stop'):payload=payload.replace('"finish_reason": "tool_calls"','"finish_reason": "stop"')
            return httpx.Response(200,stream=httpx.ByteStream(payload.encode()))
        model=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,KEY),budget,transport=httpx.MockTransport(response))
        writes=[]
        if subject.endswith(('late','progress')):model=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,KEY),budget)
        class Writer:
            def __init__(self):self.transport=self
            def write(self,raw):writes.append(raw)
            async def drain(self):pass
            def abort(self):pass
        async def handshake(*args,**kwargs):
            await asyncio.sleep(1.1)
            return None,Writer()
        services=RealServices(model,KEY,frozenset(subjects))
        evidence=None
        if subject=='m4-synthetic-ok':
            evidence_directory=auth.parent/'tool-evidence'
            evidence_directory.mkdir(mode=0o700)
            manifest=auth.parent/'tool-evidence-window.json'
            manifest.write_text(json.dumps(dict(version='G2C-tool-evidence-window.1',
                directory=str(evidence_directory),messages=[dict(subject=subject,message_id=subject)],
                expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),source_commit='a'*40)))
            manifest.chmod(0o600)
            evidence=ToolEvidence.load(manifest,frozenset(subjects))
        tools=RealTools(services,streaming_subject=subject if legacy_stream else None,
                        assembly_streaming_subjects=frozenset(assembly_pair),
                        buffered_streaming_subjects=frozenset({subject}) if buffered else frozenset(),
                        tool_evidence=evidence)
        db=LocalDatabase(conninfo,run_context=profiles[subject][1])
        opened = []
        open_runtime = db._open_runtime_connection

        def counted_checkout():
            opened.append(None)
            return open_runtime()

        with api(subject) as client, patch('cj_api.real_services.fetch_candidate',place), patch.object(db,'_open_runtime_connection',counted_checkout):
            receipt=send(client,subject)
            before=len(tool_calls)
            if subject.endswith('late'):
                with patch('cj_agent.provider.asyncio.open_connection',handshake):
                    outcomes=run_worker.run_once(db,model,auth,tools_configuration=tools,real_services=services,account_admission=True)
            elif incremental:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    original=pool.submit(run_worker.run_once,db,model,auth,tools_configuration=tools,
                                         real_services=services,account_admission=True)
                    try:
                        assert paused.wait(10)
                        assert budget.inspect()[-1]['state']=='INTENT'
                        if buffered:
                            with db.connect(scope_for(ISSUER,subject)) as connection:
                                assert connection.execute('SELECT status FROM cj_run_record WHERE run_id=%s',(receipt['run_id'],)).fetchone()==('running',)
                                assert connection.execute("SELECT count(*) FROM cj_run_event WHERE run_id=%s AND (value::text LIKE '%%Synthetic visible answer%%' OR value::text LIKE '%%Speculative same-turn%%')",(receipt['run_id'],)).fetchone()==(0,)
                        else:
                            running=harness.expect(client.get('/v1/run-display',params=dict(message_id=subject),headers=headers[subject]))['snapshot']
                            assert running['run_id']==receipt['run_id'] and running['status']=='running'
                            assert 'Synthetic visible answer' in running['text'] and suffix not in running['text']
                    finally:release.set()
                    outcomes=original.result(timeout=15)
            elif subject.endswith('progress'):
                sent,release=Event(),Event()
                body=turn_sse(compact=True).replace('"finish_reason": "tool_calls"','"finish_reason": "stop"').encode()
                response_bytes=(b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nContent-Length: '+
                                str(len(body)).encode()+b'\r\n\r\n'+body)

                class PausedReader:
                    async def read(self, size):
                        if not await asyncio.to_thread(release.wait,15):
                            raise TimeoutError('synthetic response release expired')
                        return response_bytes

                class SentWriter(Writer):
                    async def drain(self):
                        sent.set()

                async def paused_handshake(*args,**kwargs):
                    return PausedReader(),SentWriter()

                with patch('cj_agent.provider.asyncio.open_connection',paused_handshake),ThreadPoolExecutor(max_workers=1) as pool:
                    original=pool.submit(run_worker.run_once,db,model,auth,tools_configuration=tools,
                                         real_services=services,account_admission=True)
                    try:
                        assert sent.wait(10)
                        assert budget.inspect()[0]['state']=='INTENT'
                        running=harness.expect(client.get('/v1/run-display',params=dict(message_id=subject),headers=headers[subject]))
                        assert running['snapshot']['status']=='running' and running['snapshot']['text']==''
                    finally:
                        release.set()
                    outcomes=original.result(timeout=15)
            elif subject.endswith('guard-unknown'):
                from cj_api.local_account_admission_v2 import retired_in_transaction
                original_chunks = model._chunks
                original_commit = psycopg.Connection.commit
                active = False
                scoped_connection = None
                lost = False

                @contextmanager
                def last_guard(*args):
                    nonlocal active
                    active = True
                    try:
                        with original_chunks(*args) as chunks:
                            yield chunks
                    finally:
                        active = False

                def capture_retirement(cursor, scope):
                    nonlocal scoped_connection
                    if active:
                        scoped_connection = cursor.connection
                    return retired_in_transaction(cursor, scope)

                def commit_with_lost_ack(connection):
                    nonlocal lost
                    original_commit(connection)
                    if active and connection is scoped_connection:
                        lost = True
                        raise psycopg.OperationalError('synthetic guard commit acknowledgement lost')

                from cj_message.domain import CommitUnknown as MessageCommitUnknown
                before_models = len(model_calls)
                with patch.object(model, '_chunks', last_guard), patch(
                        'cj_api.local_account_admission_v2.retired_in_transaction', capture_retirement), patch.object(
                        psycopg.Connection, 'commit', commit_with_lost_ack):
                    try:
                        run_worker.run_once(db,model,auth,tools_configuration=tools,real_services=services,account_admission=True)
                    except MessageCommitUnknown:
                        pass
                    else:
                        raise AssertionError('lost commit acknowledgement must remain unknown')
                assert lost and scoped_connection.closed and len(model_calls) == before_models
                original_attempts = budget.inspect()
                assert [(row['kind'], row['state']) for row in original_attempts] == [('model','INTENT')]
                with db.connect(scope_for(ISSUER,subject)) as connection:
                    assert connection.execute('SELECT status FROM cj_run_record WHERE run_id=%s',
                                              (receipt['run_id'],)).fetchone() == ('running',)
                    assert connection.execute('SELECT acknowledged FROM cj_message_delivery WHERE run_id=%s',
                                              (receipt['run_id'],)).fetchone() == (False,)
                outcomes = run_worker.run_once(db,model,auth,tools_configuration=tools,real_services=services,account_admission=True)
                assert [(outcome.run_id, outcome.status) for outcome in outcomes] == [(receipt['run_id'],'unknown')]
                assert budget.inspect() == original_attempts and len(model_calls) == before_models
            elif subject.endswith('run-commit-unknown'):
                from cj_run.postgres import CommitUnknown as RunCommitUnknown, Transaction
                publication_connection = None
                original_put = Transaction.put
                original_commit = psycopg.Connection.commit

                def capture_publication(tx, state):
                    nonlocal publication_connection
                    original_put(tx, state)
                    if state.events[-1].kind == 'text_delta':
                        publication_connection = tx.cur.connection

                def commit_without_ack(connection):
                    original_commit(connection)
                    if connection is publication_connection:
                        raise psycopg.OperationalError('synthetic RUN publication commit acknowledgement lost')

                with patch.object(Transaction,'put',capture_publication),patch.object(psycopg.Connection,'commit',commit_without_ack):
                    try:
                        run_worker.run_once(db,model,auth,tools_configuration=tools,real_services=services,account_admission=True)
                    except RunCommitUnknown:
                        pass
                    else:
                        raise AssertionError('lost RUN commit acknowledgement must remain unknown')
                assert publication_connection is not None and publication_connection.closed
                original_attempts = budget.inspect()
                assert model.calls==1 and len(tool_calls)==before+1
                assert [(row['kind'],row['state']) for row in original_attempts]==[
                    ('model','RECEIVED'),('place','RECEIVED')]
                with db.connect(scope_for(ISSUER,subject)) as connection:
                    assert connection.execute('SELECT status FROM cj_run_record WHERE run_id=%s',
                                              (receipt['run_id'],)).fetchone()==('running',)
                outcomes=run_worker.run_once(db,model,auth,tools_configuration=tools,real_services=services,account_admission=True)
            elif subject.endswith('ok'):
                from cj_api.composition import CompositionUnavailable
                from cj_run.core import Service as RunService

                scope = scope_for(ISSUER, subject)
                scoped_cursor = db.scoped_cursor
                retained = []

                @contextmanager
                def retain_fixture_scope(scope, *, connection=None):
                    assert connection is not None
                    retained.append(connection)
                    with scoped_cursor(scope, connection=connection) as cursor:
                        yield cursor
                        cursor.execute("SELECT set_config('cj.usage_scope', 'stale-fixture-scope', false)")

                with patch.object(db, 'scoped_cursor', retain_fixture_scope):
                    try:
                        run_worker.run_once(db,model,auth,tools_configuration=tools,real_services=services,account_admission=True)
                    except CompositionUnavailable:
                        pass
                    else:
                        raise AssertionError('retained scope must stop the original before RUN creation')
                assert retained and retained[0].closed and not budget.inspect() and model.calls == 0
                with db.connect(scope) as connection:
                    assert connection.execute('SELECT status FROM cj_run_record WHERE run_id=%s',
                                              (receipt['run_id'],)).fetchone() is None
                    assert connection.execute('SELECT acknowledged FROM cj_message_delivery WHERE run_id=%s',
                                              (receipt['run_id'],)).fetchone() == (False,)

                opened.clear()
                stages = []
                accept, apply = RunService.accept, RunService.apply

                def observe_accept(service, binding):
                    state = accept(service, binding)
                    stages.append((state.status, len(opened)))
                    return state

                def observe_apply(service, event):
                    state = apply(service, event)
                    if event.kind == 'started':
                        stages.append(('started', len(opened)))
                    return state

                with patch.object(RunService, 'accept', observe_accept), patch.object(RunService, 'apply', observe_apply):
                    outcomes=run_worker.run_once(db,model,auth,tools_configuration=tools,real_services=services,account_admission=True)
                assert stages == [('queued', len(subjects) + 5), ('started', len(subjects) + 7)], stages
                print('PASS original queued/started scope checkouts, retained scope refused before RUN and Meter')
            else:outcomes=run_worker.run_once(db,model,auth,tools_configuration=tools,real_services=services,account_admission=True)
            if subject.endswith('ok'):
                assert len(opened) <= 50, f'excessive worker database checkouts: {len(opened)}'
            if subject.endswith(('ok','stop')):
                assert outcomes[0].status=='completed',(outcomes,budget.inspect(),model.calls,len(tool_calls))
                assert model.calls==2 and len(tool_calls)==before+1
                display=harness.expect(client.get('/v1/run-display',params=dict(message_id=subject),headers=headers[subject]))
                assert 'Source: https://restapi.amap.com/v3/place/text' in display['snapshot']['text']
                assert 'Needs verification.' in display['snapshot']['text']
                assert 'TOOL-output.1' not in display['snapshot']['text']
                harness.expect(client.get('/v1/run-display',params=dict(message_id=subject),headers=headers[subjects[1]]),503)
                if subject.endswith('ok'):
                    from cj_message import domain as message_domain
                    read_app = create_local_app(conninfo_path=None, auth_dir=auth, database=db,
                                                run_context=profiles[subject][1], account_admission=True,
                                                existing_display_reads=True)
                    query = dict(message_id=subject)
                    legacy_stream = client.get('/v1/run-events',params=query,headers=headers[subject])
                    before_display = len(opened)
                    with TestClient(read_app) as reader, patch.object(
                            db, 'provision', side_effect=AssertionError('existing display must not provision')):
                        exact = harness.expect(reader.get('/v1/run-display', params=query, headers=headers[subject]))
                        assert exact['snapshot'] == display['snapshot']
                        assert len(opened) - before_display <= 12
                        protected_stream = reader.get('/v1/run-events',params=query,headers=headers[subject])
                        assert protected_stream.status_code == legacy_stream.status_code == 200
                        assert protected_stream.content == legacy_stream.content
                        harness.expect(reader.get('/v1/run-display', params=query, headers=headers[subjects[1]]),503)
                        original_read = message_domain.read_active_message
                        invitations = auth/'invited.json'
                        previous = invitations.read_bytes()

                        def revoke_after_read(tx, message_id):
                            record = original_read(tx, message_id)
                            invitations.write_text(json.dumps([s for s in subjects if s != subject]))
                            return record

                        try:
                            with patch.object(message_domain, 'read_active_message', revoke_after_read):
                                denied = reader.get('/v1/run-display', params=query, headers=headers[subject])
                                assert denied.status_code == 503 and 'snapshot' not in denied.json()
                        finally:
                            invitations.write_bytes(previous)
                    with TestClient(read_app) as reader, patch.object(db, 'provision', wraps=db.provision) as provision:
                        terminal = harness.expect(reader.post('/v1/run-cancellations',
                            json=dict(version='RUN-cancel.1', message_id=subject), headers=headers[subject]))
                        assert (terminal['run_id'], terminal['status'], terminal['event_highwater']) == (
                            receipt['run_id'], 'completed', display['snapshot']['event_highwater'])
                        provision.assert_called_once_with(scope_for(ISSUER, subject))
            elif subject.endswith('repeat'):
                assert outcomes[0].status=='failed' and model.calls==2 and len(tool_calls)==before+1
                assert [(r['kind'],r['state']) for r in budget.inspect()]==[('model','RECEIVED'),('place','RECEIVED'),('model','RECEIVED')]
            elif subject.endswith(('batch','batchfail')):
                failed=subject.endswith('batchfail')
                assert outcomes[0].status==('unknown' if failed else 'completed') and model.calls==(1 if failed else 2)
                assert len(tool_calls)==before+2
                expected=[('model','RECEIVED'),('place','RECEIVED'),('place','INTENT' if failed else 'RECEIVED')]
                if not failed:expected.append(('model','RECEIVED'))
                assert [(r['kind'],r['state']) for r in budget.inspect()]==expected
            elif subject.endswith(('tail','tailbad')):
                assert model.calls==8 and len(tool_calls)==before+7,(subject,outcomes,model.calls,len(tool_calls)-before,[(r['kind'],r['state']) for r in budget.inspect()])
                assert outcomes[0].status==('unknown' if subject.endswith('tailbad') else 'completed')
                assert len(budget.inspect())==15
                assert budget.inspect()[-1]['state']==('INTENT' if subject.endswith('tailbad') else 'RECEIVED')
                if subject.endswith('tail'):
                    display=harness.expect(client.get('/v1/run-display',params=dict(message_id=subject),headers=headers[subject]))
                    assert display['snapshot']['text_state']=='complete' and 'Needs verification.' in display['snapshot']['text']
            elif subject.endswith('limit'):
                assert outcomes[0].status=='failed' and model.calls==1 and len(tool_calls)==before
            elif subject.endswith('run-commit-unknown'):
                assert [(outcome.run_id,outcome.status) for outcome in outcomes]==[(receipt['run_id'],'unknown')]
                assert model.calls==1 and len(tool_calls)==before+1 and budget.inspect()==original_attempts
                with db.connect(scope_for(ISSUER,subject)) as connection:
                    assert connection.execute('SELECT acknowledged FROM cj_message_delivery WHERE run_id=%s',
                                              (receipt['run_id'],)).fetchone()==(True,)
            elif subject.endswith(('unknown','malformed')):
                assert outcomes[0].status=='unknown' and model.calls==1 and len(tool_calls)==before
                assert budget.inspect()[0]['state']==('INTENT' if subject.endswith('unknown') else 'RECEIVED')
            elif subject.endswith('late'):
                assert outcomes[0].status=='failed' and model.calls==1 and len(tool_calls)==before and not writes
                assert budget.inspect()[0]['state']=='INTENT'
            elif subject.endswith('progress'):
                assert outcomes[0].status=='completed' and model.calls==len(writes)==1 and len(tool_calls)==before
                assert budget.inspect()[0]['state']=='RECEIVED'
            elif incremental:
                assert [(outcome.run_id,outcome.status) for outcome in outcomes]==[(receipt['run_id'],'unknown' if mixed else 'completed')]
                assert model.calls==(1 if mixed else 2) and len(tool_calls)==before+(0 if mixed else 2)
                expected=[('model','INTENT')] if mixed else [('model','RECEIVED'),('place','RECEIVED'),('place','RECEIVED'),('model','RECEIVED')]
                assert [(r['kind'],r['state']) for r in budget.inspect()]==expected
                display=harness.expect(client.get('/v1/run-display',params=dict(message_id=subject),headers=headers[subject]))['snapshot']
                assert 'Synthetic visible answer' in display['text'] and (prefix+suffix in display['text']) is not mixed
                if buffered:assert 'Speculative same-turn' not in display['text']
            elif subject.endswith('permission'):
                assert outcomes[0].status=='failed' and model.calls==1 and len(tool_calls)==before+1
                assert budget.inspect()[-1]['receipt']['provider_code']=='10012'
            else:
                assert outcomes[0].status=='context_invalid' and model.calls==1 and len(tool_calls)==before
                (auth/'invited.json').write_text(json.dumps(subjects))
            calls=model.calls
            assert run_worker.run_once(db,model,auth,tools_configuration=tools,real_services=services,account_admission=True)==[] and model.calls==calls
        scope=scope_for(ISSUER,subject);account=ledger_scope_for(scope,profiles[subject][1].current.meter)
        with db.connect(scope) as conn:
            operations=conn.execute('SELECT operation_key,attempt_id FROM cj_run_metered_operation WHERE run_id=%s',(receipt['run_id'],)).fetchall()
            assert operations and len({attempt for _,attempt in operations})==len(operations)
            ledger=decode(conn.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()[0])
            assert ledger.attempts
            if subject=='m4-synthetic-ok':
                artifact,=evidence_directory.iterdir()
                captured=json.loads(artifact.read_bytes())
                assert captured['run_id']==receipt['run_id'] and captured['message_id']==subject
                raw_input,=conn.execute('SELECT input_bytes FROM cj_run_metered_operation '
                    'WHERE scope=%s AND run_id=%s AND operation_key=%s',
                    (scope,receipt['run_id'],captured['operation_key'])).fetchone()
                assert captured['input_sha256']==sha256(bytes(raw_input)).hexdigest()
                assert captured['input_utf8'].encode()==bytes(raw_input)
                native,=conn.execute('SELECT input_bytes FROM cj_run_metered_operation '
                    'WHERE scope=%s AND run_id=%s AND operation_key=%s',
                    (scope,receipt['run_id'],'model.tool_turn.1')).fetchone()
                next_input=json.loads(bytes(native))
                tool_message=next(message for message in reversed(next_input['messages']) if message['role']=='tool')
                continued,=json.loads(tool_message['content'])['results']
                assert continued['result']==json.loads(captured['result_utf8'])
                original=next(row for row in budget.inspect() if row['attempt_id']==captured['attempt_id'])
                assert original['state']=='RECEIVED' and ledger.attempts[captured['attempt_id']].state=='settled'
                assert captured['response_sha256']==original['receipt']['response_sha256']
                assert captured['response_sha256']==sha256(captured['result_utf8'].encode()).hexdigest()
                print('PASS signed original tool artifact, registered input, vendor digest, actual continuation and settled Meter')
            if incremental:
                assert all((attempt.receipt is None)==mixed for attempt in ledger.attempts.values())
                assert conn.execute('SELECT acknowledged FROM cj_message_delivery WHERE run_id=%s',
                                    (receipt['run_id'],)).fetchone()==(True,)
    # A real admitted MESSAGE/RUN invokes exactly one original reflection
    # registration. The ordinary tool/planning/Memory paths are never selected.
    from runtime_adapter.profiles import C0
    subject='m4-synthetic-runtime-reflection';packets=[]
    budget=AuthorizationBudget(auth.parent/subject,clock=lambda:NOW)
    output=json.dumps({'prompt.answer_style':'Short and useful.'},separators=(',',':'))
    def reflection_response(request):
        body=json.loads(request.content);packets.append(body)
        assert 'tools' not in body and body['max_tokens']==1024
        event=dict(id='local-reflection-original-'+str(len(packets)),model=M4_MODEL,
            choices=[dict(index=0,delta={'content':output},finish_reason='stop')],
            usage=dict(prompt_tokens=10,completion_tokens=8,total_tokens=18))
        return httpx.Response(200,stream=httpx.ByteStream(('data: '+json.dumps(event)+'\n\ndata: [DONE]\n\n').encode()))
    model=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,KEY,max_output_tokens=M4_REAL_OUTPUT_TOKENS),budget,
        transport=httpx.MockTransport(reflection_response))
    services=RealServices(model,KEY,frozenset(subjects))
    reflection_directory=auth.parent/'reflection-evidence';reflection_directory.mkdir(mode=0o700)
    reflection_manifest=auth.parent/'reflection-evidence-window.json'
    reflection_manifest.write_text(json.dumps(dict(version='G2C-runtime-evidence-window.3',
        directory=str(reflection_directory),messages=[dict(subject=subject,message_id=subject)],
        expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),source_commit='a'*40,kinds=['model'])))
    reflection_manifest.chmod(0o600)
    tools=RealTools(services,tool_evidence=ToolEvidence.load(reflection_manifest,frozenset(subjects)))
    db=LocalDatabase(conninfo,run_context=profiles[subject][1]);scope=scope_for(ISSUER,subject)
    payload=dict(candidate=C0,components=['prompt.answer_style'],feedback={'development':'synthetic quoted feedback'})
    def registrations(binding):
        assert binding.scope==scope and binding.message_id==subject
        return tools.runtime_registrations(C0)
    options=dict(tools_configuration=tools,real_services=services,account_admission=True,
                 runtime_registrations_for_run=registrations,runtime_reflection=lambda binding:payload)
    with api(subject) as client:
        receipt=send(client,subject,'Reflect the candidate texts using development feedback only.')
        outcomes=run_worker.run_once(db,model,auth,**options)
        assert [(x.run_id,x.status) for x in outcomes]==[(receipt['run_id'],'completed')]
        assert len(packets)==model.calls==1
        display=harness.expect(client.get('/v1/run-display',params={'message_id':subject},headers=headers[subject]))
        assert display['snapshot']['text']==output
        assert run_worker.run_once(db,model,auth,**options)==[] and model.calls==1
    account=ledger_scope_for(scope,profiles[subject][1].current.meter)
    with db.connect(scope) as conn:
        ops=conn.execute('SELECT registration_id,attempt_id FROM cj_run_metered_operation WHERE scope=%s AND run_id=%s',
                        (scope,receipt['run_id'])).fetchall()
        assert len(ops)==1 and ops[0][0]=='model.runtime_reflection.1'
        meter=decode(conn.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()[0])
        assert meter.attempts[ops[0][1]].state=='settled'
        assert conn.execute("SELECT count(*) FROM cj_run_event WHERE scope=%s AND run_id=%s AND kind='effect_committed'",(scope,receipt['run_id'])).fetchone()==(0,)
    assert [(x['attempt_id'],x['state']) for x in budget.inspect()]==[(ops[0][1],'RECEIVED')]
    artifacts=[json.loads(path.read_bytes()) for path in reflection_directory.iterdir()]
    wire,=[x for x in artifacts if x['version']=='G2C-model-wire-input.1']
    result,=[x for x in artifacts if x['version']=='G2C-model-evidence.1']
    assert len(artifacts)==2 and wire['attempt_id']==result['attempt_id']==ops[0][1]
    assert sha256(wire['wire_input_utf8'].encode()).hexdigest()==budget.inspect()[0]['input_sha']==wire['wire_input_sha256']
    assert wire['logical_input_sha256']==result['input_sha256']!=wire['wire_input_sha256']
    assert result['result_utf8']==output and result['receipt']==budget.inspect()[0]['receipt']
    assert all(KEY not in json.dumps(record) for record in artifacts)
    from cj_api.runtime_originals import RuntimeOriginals
    from cj_api.local_account_admission_v2 import account_checker_for
    from cj_message.auth_boundary import Boundary
    from runtime_adapter.contract import Unavailable
    boundary=Boundary(account_checker_for(auth,db),
        lambda principal:db.message_repository(scope_for(principal.issuer,principal.subject)),lambda:str(uuid.uuid4()))
    reader=RuntimeOriginals(boundary,db,budget,reflection_directory)
    token=headers[subject]['Authorization'].removeprefix('Bearer ')
    inventory=json.loads(reader.inventory(token,subject))
    assert inventory['status']=='completed' and [o['operation_id'] for o in inventory['operations']]==[result['operation_id']]
    assert json.loads(reader.artifact(token,subject,result['operation_id'],wire_input=True))==wire
    assert json.loads(reader.artifact(token,subject,result['operation_id']))==result
    assert json.loads(reader.fee(token,subject,result['operation_id']))['actual_wire_input_sha256']==wire['wire_input_sha256']
    assert json.loads(reader.meter(token,subject,result['operation_id']))['state']=='settled'
    try:reader.inventory(headers['m4-synthetic-ok']['Authorization'].removeprefix('Bearer '),subject)
    except Unavailable:pass
    else:raise AssertionError('foreign runtime original exposed')
    output_file=next(path for path in reflection_directory.iterdir() if json.loads(path.read_bytes())['version']=='G2C-model-evidence.1')
    saved=output_file.read_bytes();tampered=json.loads(saved);tampered['result_utf8']='tampered result'
    output_file.write_text(json.dumps(tampered))
    try:reader.artifact(token,subject,result['operation_id'])
    except Unavailable:pass
    else:raise AssertionError('corrupt runtime output exposed')
    output_file.write_bytes(saved)
    # AUTH is repeated after protected bytes/storage callbacks, not merely when
    # the reader was constructed. A late revocation may not publish old bytes.
    roster=auth/'invited.json';saved_roster=roster.read_bytes()
    read_operations=reader._operations;reads=[0]
    def revoke_after_storage(owner,run_id):
        value=read_operations(owner,run_id);reads[0]+=1
        if reads[0]==2:roster.write_text(json.dumps([s for s in subjects if s!=subject]))
        return value
    try:
        with patch.object(reader,'_operations',revoke_after_storage):
            try:reader.input(token,subject,result['operation_id'])
            except Unavailable as error:assert str(error)=='ORIGINAL_AUTH_UNAVAILABLE'
            else:raise AssertionError('original bytes escaped after final AUTH revoked')
    finally:roster.write_bytes(saved_roster)
    # Canonical claims share the *actual* MESSAGE admission lock and the signed
    # Boundary lifetime. They never reserve or invoke the model.
    from types import SimpleNamespace
    from cj_api.runtime_authority import RuntimeAuthority
    from cj_api.runtime_message_claims import MessageClaims
    from cj_usage.authorization_budget import journal_state,CNY_SCALE
    from cj_usage.sublimits import activate,scope_hash
    from runtime_adapter.contract import VERSION,digest,encode
    base=dict(cap=None,active_cap=None,model_cap=None,tool_cap=None,max_calls=None,model_calls=None,tool_calls=None)
    grants={line:dict(base) for line in ('A','B','L','C','E','F')}
    for line in ('L','C','E','F'):grants[line].update(cap=50*CNY_SCALE,active_cap=50*CNY_SCALE)
    activate(budget,grants,{scope_hash(scope):'E',scope_hash(scope_for(ISSUER,'m4-synthetic-runtime-factory')):'E'})
    pins=SimpleNamespace(key='a'*64,raw=b'local-control-pins')
    authority=RuntimeAuthority(account_checker_for(auth,db),lambda:token,budget,pins,lambda:pins.raw,
        line='E',wall_clock=lambda:datetime(2026,11,12,13,5,tzinfo=timezone.utc))
    claim_directory=auth.parent/'native-claims';claim_directory.mkdir(mode=0o700)
    claims=MessageClaims(claim_directory,boundary,lambda:token,authority,pins)
    def request(attempt):
        return encode(dict(version=VERSION,attempt_id=attempt,step_id='runtime-'+digest([scope,attempt,0]),
            binding_sha256=authority.binding().key,pins_sha256=pins.key,kind='message',
            payload={'text':'Original native claim fixture'},candidate=C0,prior_step_ids=[]))
    with budget.connect() as journal:before_claims=journal_state(journal)
    original_calls=model.calls
    raw=request('native-fresh-claim');deadline=time.monotonic()+30
    claimed=claims.claim(raw,deadline=deadline)
    assert claimed.fresh and claims.consume(raw,claimed.capability,deadline=deadline)==json.loads(raw)
    assert not claims.claim(raw,deadline=deadline).fresh
    rebuilt=MessageClaims(claim_directory,boundary,lambda:token,authority,pins)
    assert not rebuilt.claim(raw,deadline=deadline).fresh
    # Admit a different ID through the genuine signed MESSAGE API first. The
    # claim lookup observes it inside the same original scope transaction.
    native=request('native-already-admitted');mid=json.loads(native)['step_id']
    with api(subject) as client:
        head=harness.expect(client.get('/v1/message-send-status',params={'conversation_id':subject},headers=headers[subject]))['head']
        body=json.dumps(dict(version='MESSAGE-send.1',conversation_id=subject,message_id=mid,
            text='Original native claim fixture',trip_id=None,creation_intent='none',
            expected_generation=head['generation'],expected_sequence=head['last_sequence'])).encode()
        harness.expect(client.post('/v1/messages',content=body,headers={**headers[subject],'Content-Type':'application/octet-stream'}))
    assert not claims.claim(native,deadline=deadline).fresh
    assert len(list(claim_directory.iterdir()))==1
    from cj_api.runtime_run_requests import RunRequests,REFLECTION_MESSAGE
    from cj_run.core import Binding as RunBinding
    routing=RunRequests(claims,boundary,lambda:token,tools)
    for kind in ('message','reflection'):
        route=json.loads(request('native-route-'+kind));route['kind']=kind
        if kind=='reflection':route['payload']=payload
        encoded=encode(route);prepared=claims.claim(encoded,deadline=deadline);assert prepared.fresh
        claims.consume(encoded,prepared.capability,deadline=deadline)
        mid=route['step_id']
        with api(subject) as client:
            conversation=subject+'-reflection' if kind=='reflection' else subject
            if kind=='reflection':harness.expect(client.put('/v1/conversations',params={'conversation_id':conversation},headers=headers[subject]))
            head=harness.expect(client.get('/v1/message-send-status',params={'conversation_id':conversation},headers=headers[subject]))['head']
            body=json.dumps(dict(version='MESSAGE-send.1',conversation_id=conversation,message_id=mid,
                text=REFLECTION_MESSAGE if kind=='reflection' else route['payload']['text'],trip_id=None,creation_intent='none',
                expected_generation=head['generation'],expected_sequence=head['last_sequence'])).encode()
            admitted=harness.expect(client.post('/v1/messages',content=body,headers={**headers[subject],'Content-Type':'application/octet-stream'}))['receipt']
        binding=RunBinding(scope,admitted['conversation_id'],admitted['generation'],mid,admitted['run_id'],admitted['sequence'])
        assert routing.request(binding)==route
        assert set(routing.registrations(binding))==set(tools.runtime_registrations(C0))
        assert routing.reflection(binding)==(payload if kind=='reflection' else None)
    assert model.calls==original_calls
    with budget.connect() as journal:assert journal_state(journal)==before_claims
    # Execute only the selected *original* receipt using RunWorker's existing
    # execution lease/owned _one path. Other pending test messages stay pending;
    # no normal worker races a differently configured registry in this harness.
    from cj_api.runtime_collector import RuntimeCollector
    from cj_api.runtime_model import RuntimeModel
    from cj_agent.provider import M4_NATIVE_TURN_BUFFERED
    from runtime_adapter.evidence import check_snapshot
    reflection_manifest.write_text(json.dumps(dict(version='G2C-runtime-evidence-window.3',
        directory=str(reflection_directory),messages=[dict(subject=subject,message_id=mid)],
        expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),source_commit='a'*40,kinds=['model'])))
    tools=RealTools(services,tool_evidence=ToolEvidence.load(reflection_manifest,frozenset(subjects)))
    routing=RunRequests(claims,boundary,lambda:token,tools)
    worker=run_worker._worker_for_scope(db,model,auth,scope,account_checker_for(auth,db),
        tools_configuration=tools,runtime_registrations_for_run=routing.registrations,runtime_reflection=routing.reflection)
    receipt=boundary.with_history_context(token,lambda context:context.query_message(mid).receipt)
    from cj_usage.authorization_budget import HK_PRODUCER
    # Exercise the accepted scoped operation-ID branch. The already-created
    # budget remains the actual local MAC producer/journal; no HK path/control
    # or live balance is opened or fabricated by this environment selection.
    with patch.dict(os.environ,{'CJ_M4_BUDGET_PRODUCER':HK_PRODUCER}),worker.execution_lease():
        outcome=worker._one(receipt)
    assert (outcome.status,model.calls)==('completed',original_calls+1),(outcome.status,model.calls,original_calls)
    def state_reader(token_value,original_mid):
        with api(subject) as client:
            response=client.get('/v1/run-display',params={'message_id':original_mid},headers={'Authorization':'Bearer '+token_value})
            # The original snapshot is stable; each HTTP request_id is fresh
            # routing metadata, not a field in the original RUN/state proof.
            return encode(harness.expect(response)['snapshot'])
    model_reader=RuntimeModel(reader,model,native_turn_profile=M4_NATIVE_TURN_BUFFERED)
    operation,=json.loads(reader.inventory(token,mid))['operations']
    # Fixture-only model pin is specified independently from the provider
    # projection; no production code/image card or live eligibility is claimed.
    pins.value={'model':dict(endpoint=M4_BASE,id=M4_MODEL,parameters=dict(stream=True,
        stream_options={'include_usage':True},enable_thinking=False,
        max_tokens_by_profile=dict(answer=M4_REAL_OUTPUT_TOKENS,intake=M4_REAL_OUTPUT_TOKENS,reflection=1024),
        native_turn_profile=M4_NATIVE_TURN_BUFFERED))}
    references=auth.parent/'collector-refs';references.mkdir(mode=0o700)
    collector=RuntimeCollector(reader,claims,routing,lambda:token,pins,references,
        guard=lambda **kwargs:authority.require(binding=authority.binding(),pins_sha256=pins.key,
            purpose='query',deadline=time.monotonic()+30,read_only=True),state_reader=state_reader,model_reader=model_reader)
    snapshot=collector.inspect(route['attempt_id'],mid,deadline=time.monotonic()+30)
    verified=check_snapshot(snapshot,request=route,binding=authority.binding(),pins=pins,
        original=lambda ref:collector.original(ref,deadline=time.monotonic()+30))
    assert verified['status']=='PASS' and verified['result']==json.loads(output)
    assert len(verified['operation_checks'])==1 and verified['operation_checks'][0]['status']=='PASS'
    assert model.calls==original_calls+1
    # Finally exercise G's public propose/query on the concrete native host,
    # rather than a fake RuntimeBackend. All identities/model responses here are
    # local fixtures and no production runtime card/quality result is claimed.
    from runtime_adapter import RuntimeAdapter
    from runtime_adapter.configuration import source_c0
    from runtime_adapter.contract import Pins
    from cj_api.runtime_native_backend import NativeRuntimeBackend
    source=source_c0()
    names=('version','adapter_sha256','system_prompt_sha256','tool_schema_sha256','tool_implementation_sha256',
        'c0','task_version','task_sha256','score_version','score_sha256','preregistration_sha256')
    runtime_pins=Pins.from_dict({**{name:source[name] for name in names},'code_sha':'a'*40,
        'image_digest':'sha256:'+'a'*64,'model':pins.value['model']})
    runtime_authority=RuntimeAuthority(account_checker_for(auth,db),lambda:token,budget,runtime_pins,
        lambda:runtime_pins.raw,line='E',wall_clock=lambda:datetime(2026,11,12,13,5,tzinfo=timezone.utc))
    runtime_claims=MessageClaims(claim_directory,boundary,lambda:token,runtime_authority,runtime_pins)
    logical_attempt='native-public-propose';step='runtime-'+digest([scope,logical_attempt,0])
    reflection_manifest.write_text(json.dumps(dict(version='G2C-runtime-evidence-window.4',
        directory=str(reflection_directory),subjects=[subject],
        expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),source_commit='a'*40,kinds=['model'])))
    runtime_tools=RealTools(services)
    runtime_routing=RunRequests(runtime_claims,boundary,lambda:token,runtime_tools)
    runtime_tools.tool_evidence=ToolEvidence.load(reflection_manifest,frozenset(subjects),
        runtime_selection=runtime_routing.selects)
    runtime_worker=run_worker._worker_for_scope(db,model,auth,scope,account_checker_for(auth,db),
        tools_configuration=runtime_tools,runtime_registrations_for_run=runtime_routing.registrations,
        runtime_reflection=runtime_routing.reflection)
    def runtime_guard(**kwargs):
        runtime_authority.require(binding=runtime_claims.binding,pins_sha256=runtime_pins.key,
            purpose='query',deadline=time.monotonic()+30,read_only=kwargs['read_only'])
    runtime_collector=RuntimeCollector(reader,runtime_claims,runtime_routing,lambda:token,runtime_pins,references,
        guard=runtime_guard,state_reader=state_reader,model_reader=model_reader)
    def require_worker(binding,pinned,deadline):
        assert binding==runtime_claims.binding and pinned.raw==runtime_pins.raw and time.monotonic()<deadline
        assert runtime_worker.runtime_reflection.__self__ is runtime_routing
        assert runtime_worker.budget_exit.registrations_for_run.__self__ is runtime_routing
    def wait_original(original_receipt,deadline):
        assert time.monotonic()<deadline
        with patch.dict(os.environ,{'CJ_M4_BUDGET_PRODUCER':HK_PRODUCER}),runtime_worker.execution_lease():
            completed=runtime_worker._one(original_receipt)
        assert completed.status=='completed'
    def legacy_fixture_reflection(mid):
        cid='fixture-reflection-'+digest([scope,mid]);head=boundary.open_conversation(token,cid)
        return boundary.receive(token,encode(dict(version='MESSAGE-send.1',conversation_id=cid,message_id=mid,
            text=REFLECTION_MESSAGE,trip_id=None,creation_intent='none',expected_generation=head.generation,expected_sequence=0)))
    backend=NativeRuntimeBackend(runtime_authority,runtime_claims,runtime_collector,boundary,lambda:token,
        require_worker=require_worker,wait_original=wait_original,admit_reflection=legacy_fixture_reflection)
    mappings=auth.parent/'g-original-mapping';mappings.mkdir(mode=0o700)
    adapter=RuntimeAdapter(backend,runtime_authority.binding(),runtime_pins,mappings)
    feedback=dict(split='development',dataset_sha256=runtime_pins.value['task_sha256'],rows=[
        dict(task_id='dev-airport',language='en',feedback='Local fixture feedback only, no live quality claim.',
            evidence=['local-controlled-feedback-not-live-quality'])])
    proposed=adapter.propose(C0,feedback,['prompt.answer_style'],logical_attempt,60)
    assert proposed['status']=='PASS',proposed
    assert proposed['result']==json.loads(output) and proposed['quality_status']=='UNKNOWN'
    calls=model.calls
    assert adapter.query(logical_attempt)['status']=='PASS' and model.calls==calls
    captured=next(path for path in reflection_directory.iterdir() if
        (value:=json.loads(path.read_bytes()))['message_id']==step and value['version']=='G2C-model-evidence.1')
    saved=captured.read_bytes()
    corrupt_text=json.loads(saved);corrupt_text['result_utf8']='corrupted original'
    missing_receipt=json.loads(saved);missing_receipt.pop('receipt')
    wrong_type=json.loads(saved);wrong_type['result_utf8']=17
    try:
        for corrupt in (corrupt_text,missing_receipt,wrong_type):
            captured.write_text(json.dumps(corrupt))
            bad=adapter.query(logical_attempt)
            assert bad['status']=='UNKNOWN' and model.calls==calls
            operation,=bad['steps'][0]['snapshot']['operations']
            assert operation['fee'] is not None and operation['input'] is not None and operation['output'] is None
            assert len(bad['steps'][0]['operation_checks'])==1
    finally:captured.write_bytes(saved)
    assert adapter.query(logical_attempt)['status']=='PASS' and model.calls==calls
    roster=auth/'invited.json';saved_roster=roster.read_bytes()
    read_state=runtime_collector.state_reader
    def revoke_after_state(token_value,original_mid):
        raw=read_state(token_value,original_mid)
        roster.write_text(json.dumps([s for s in subjects if s!=subject]))
        return raw
    try:
        with patch.object(runtime_collector,'state_reader',revoke_after_state):
            revoked=adapter.query(logical_attempt)
        assert revoked['status']=='UNKNOWN' and 'steps' not in revoked and 'result' not in revoked
        assert model.calls==calls
    finally:roster.write_bytes(saved_roster)
    stopped=adapter.call({'id':'dev-airport','language':'en'},C0,'native-no-task-recipes',60)
    assert stopped['status']=='UNRUN' and stopped['reason']=='NATIVE_DIALOGUE_TASK_RECIPES_NOT_CONNECTED'
    assert model.calls==calls
    # Load the actual private worker composition/card, including a pinned
    # non-restored claim directory. G dispatch and the existing worker run on
    # different threads, as in the worker socket/main-loop deployment.
    from cj_api.runtime_worker_bindings import RuntimeWorkerBindings
    from cj_api.runtime_rpc import RuntimeRPC
    from cj_api.runtime_text_slots import C0_NATIONAL_V2,source_c0_national_v2
    factory_subject='m4-synthetic-runtime-factory';factory_scope=scope_for(ISSUER,factory_subject)
    # Initial operator-only fixture configuration, before this new subject has
    # any message. Not an experimental setup or an administrator-built Trip.
    with psycopg.connect(**json.loads(conninfo.read_bytes())) as initializer:
        initializer.execute("INSERT INTO cj_message_context_profile VALUES(%s,'message-travel.1')",(factory_scope,))
    factory_db=LocalDatabase(conninfo,run_context=profiles[factory_subject][1],travel_context=True)
    factory_token=headers[factory_subject]['Authorization'].removeprefix('Bearer ')
    factory_boundary=Boundary(account_checker_for(auth,factory_db),
        lambda principal:factory_db.message_repository(scope_for(principal.issuer,principal.subject)),lambda:str(uuid.uuid4()))
    manifest=auth.parent/'runtime-host.json';token_file=auth.parent/'runtime-host.jwt'
    token_file.write_text(factory_token);token_file.chmod(0o600)
    def pinned(path):
        path.mkdir(mode=0o700,exist_ok=True);info=path.stat()
        return dict(path=str(path),device=info.st_dev,inode=info.st_ino)
    directory_pins={key:pinned(auth.parent/name) for key,name in (
        ('canonical_directory','factory-claims'),('references_directory','factory-references'),('mapping_directory','factory-mapping'))}
    manifest.write_bytes(encode(dict(version='G2C-runtime-host.1',baseline='national.2',resource_root=str(harness.ROOT),
        runtime_card=dict(code_sha='a'*40,image_digest='sha256:'+'a'*64,model=source_c0_national_v2()['model']),
        evidence_manifest=str(reflection_manifest),lines=[dict(line='E',subject=factory_subject,token_file=str(token_file),**directory_pins)])))
    manifest.chmod(0o600)
    factory_tools=RealTools(services,buffered_streaming_subjects=frozenset({factory_subject}))
    fixture_runtime=SimpleNamespace(auth=auth,database=lambda:factory_db,demo_subjects=frozenset({factory_subject}),memory_configuration_for_scope=lambda owner:None)
    factory=RuntimeWorkerBindings(manifest,fixture_runtime,services,factory_tools,confirmation_signer=None,
        wall_clock=lambda:datetime(2026,11,12,13,5,tzinfo=timezone.utc))
    reflection_manifest.write_bytes(encode(dict(version='G2C-runtime-evidence-window.4',directory=str(reflection_directory),
        subjects=[factory_subject],expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),source_commit='a'*40,kinds=['model'])))
    factory.attach_evidence(ToolEvidence.load(reflection_manifest,frozenset(subjects),runtime_selection=factory.selects))
    session=factory.by_scope[factory_scope];rpc=RuntimeRPC(factory)
    request=lambda method,params:encode(dict(version='G2C-runtime-host.1',token=factory_token,method=method,params=params))
    blocked=json.loads(rpc.handle(request('propose',dict(candidate=C0_NATIONAL_V2,feedback=feedback,
        components=['prompt.answer_style'],attempt_id='factory-training-not-ready',timeout=60))))
    assert blocked['status']=='UNRUN' and blocked['reason']=='ALL_TASK_LEGAL_SETUPS_NOT_CONNECTED' and model.calls==calls
    assert list((auth.parent/'factory-mapping').iterdir())==[]
    c0=json.loads(rpc.handle(request('c0',{})));assert c0['c0']['runtime_eligible'] is False and c0['training_status']=='UNRUN'
    factory_worker=run_worker._worker_for_scope(factory_db,model,auth,factory_scope,account_checker_for(auth,factory_db),tools_configuration=factory_tools,
        runtime_registrations_for_run=factory.registrations,runtime_reflection=factory.reflection)
    with ThreadPoolExecutor(max_workers=1) as pool:
        proposal=pool.submit(session['adapter'].propose,C0_NATIONAL_V2,feedback,['prompt.answer_style'],'factory-local-component-control',60)
        factory_mid='runtime-'+digest([factory_scope,'factory-local-component-control',0]);limit=time.monotonic()+30
        while True:
            native=factory_boundary.with_history_context(factory_token,lambda context:context.query_lio_message(factory_mid))
            if native is not None:break
            assert time.monotonic()<limit
            time.sleep(.02)
        with patch.dict(os.environ,{'CJ_M4_BUDGET_PRODUCER':HK_PRODUCER}),factory_worker.execution_lease():
            final=factory_worker._one(native.receipt)
        assert final.status=='completed'
        completed=proposal.result(timeout=30)
    assert completed['status']=='PASS' and model.calls==calls+1,(completed,session['adapter'].query('factory-local-component-control'))
    observed=json.loads(rpc.handle(request('query',{'attempt_id':'factory-local-component-control'})))
    assert observed['status']=='PASS' and model.calls==calls+1
    print('PASS actual private worker manifest/national.2 pins/canonical directory pin, concurrent G/native original worker, E/F full-setup gate before any intent or spend')
    print('PASS public G propose/query -> concrete native MESSAGE/RUN/registered reflection/collector; repeated query zero sends, unavailable all-task recipe stops before paid setup')
    print('PASS canonical MESSAGE -> original leased RUN/candidate/reflection -> actual original collector envelope verified by G; fixture model/wire/Meter/fee, no copied expected state')
    print('PASS signed Boundary + actual MESSAGE scope lock/native original lookup; durable claim/reconstruction/native-existing reject, zero fees or provider sends')
    print('PASS signed reflection original MESSAGE/RUN -> single registered model/settled Meter/original financial receipt; no tools, publication or replay')
    print('PASS signed API -> registered native model/tool/model -> real PG/RUN/Meter, live receipt references, owner isolation, limit/revocation-before-tool, UNKNOWN original read/no resend; HTTP fixtures only')


if __name__=='__main__':harness.exercise=exercise;harness.main()
