"""Real PG/RUN/Meter with native HTTP fixtures; no live key/network/cost."""
import asyncio,json,os,time
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime,timezone
from unittest.mock import patch

import httpx
import psycopg
from fastapi.testclient import TestClient

from cj_agent.provider import DashScopeConfig,MeteredDashScopeProvider,M4_BASE,M4_MODEL,M4_TURN_FUNCTION_V2
from cj_api.real_services import RealServices,RealTools
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
from test_m4_real_services import turn_sse,KEY,NOW


def exercise(auth,conninfo):
    subjects=['m4-synthetic-'+v for v in ('ok','limit','unknown','malformed','late','permission','revoke','repeat','tail','tailbad','batch','batchfail','stop','guard-unknown')]
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
    def send(client,s):
        chat=harness.expect(client.put('/v1/conversations',params=dict(conversation_id=s),headers=headers[s]))
        raw=json.dumps(dict(version='MESSAGE-send.1',conversation_id=s,message_id=s,text='Find synthetic Beijing place',trip_id=None,
            creation_intent='none',expected_generation=chat['generation'],expected_sequence=0)).encode()
        return harness.expect(client.post('/v1/messages',content=raw,headers={**headers[s],'Content-Type':'application/octet-stream'}))['receipt']
    for subject in subjects:
        budget=AuthorizationBudget(auth.parent/subject,clock=lambda:NOW)
        def response(request):
            model_calls.append(subject)
            if subject.endswith('unknown'):raise httpx.ReadTimeout('synthetic unknown')
            body=json.loads(request.content)
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
        if subject.endswith('late'):model=MeteredDashScopeProvider(DashScopeConfig(M4_BASE,M4_MODEL,KEY),budget)
        class Writer:
            def __init__(self):self.transport=self
            def write(self,raw):writes.append(raw)
            async def drain(self):pass
            def abort(self):pass
        async def handshake(*args,**kwargs):
            await asyncio.sleep(1.1)
            return None,Writer()
        services=RealServices(model,KEY,frozenset(subjects));tools=RealTools(services)
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
                assert lost and len(model_calls) == before_models
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
            else:outcomes=run_worker.run_once(db,model,auth,tools_configuration=tools,real_services=services,account_admission=True)
            if subject.endswith('ok'):
                assert len(opened) <= 110, f'excessive worker database checkouts: {len(opened)}'
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
                    before_display = len(opened)
                    with TestClient(read_app) as reader, patch.object(
                            db, 'provision', side_effect=AssertionError('existing display must not provision')):
                        exact = harness.expect(reader.get('/v1/run-display', params=query, headers=headers[subject]))
                        assert exact['snapshot'] == display['snapshot']
                        assert len(opened) - before_display <= 12
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
            elif subject.endswith(('unknown','malformed')):
                assert outcomes[0].status=='unknown' and model.calls==1 and len(tool_calls)==before
                assert budget.inspect()[0]['state']==('INTENT' if subject.endswith('unknown') else 'RECEIVED')
            elif subject.endswith('late'):
                assert outcomes[0].status=='failed' and model.calls==1 and len(tool_calls)==before and not writes
                assert budget.inspect()[0]['state']=='INTENT'
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
    print('PASS signed API -> registered native model/tool/model -> real PG/RUN/Meter, live receipt references, owner isolation, limit/revocation-before-tool, UNKNOWN original read/no resend; HTTP fixtures only')


if __name__=='__main__':harness.exercise=exercise;harness.main()
