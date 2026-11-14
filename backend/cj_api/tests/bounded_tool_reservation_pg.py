"""Signed native worker/PG output reservations; local tools, no real fees."""
from pathlib import Path
import json,time
from unittest.mock import patch
from fastapi.testclient import TestClient
import psycopg
import local_history_pg as harness
import local_run_context,run_worker
from cj_api.local_app import LocalDatabase,app_from_environment,ISSUER,scope_for
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import checker_for
from cj_agent.provider import FakeProvider
from cj_run.step_usage import ledger_scope_for
from cj_run.core import Binding
from cj_run.operation_usage import OperationStore
from cj_usage.core import Meter
from cj_usage.codec import decode
from cj_usage.registered_exit import Registration,InvocationInput
from cj_usage.metered_exit import BudgetExceeded


def exercise(auth,conninfo):
    subjects=['small-tools','legacy-tools','over-bound'];harness.dev_auth.init(auth,subjects)
    now=int(time.time());path=auth.parent/'bounds.json'
    path.write_text(json.dumps(dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(unit='provider_call',budget=800,
        period_start=now-60,period_end=now+3600,max_steps=24,max_tools=12,max_output=65536,max_seconds=600),
        output_limits=dict(model=12000,tool=48000,memory=12000)),history=[])))
    context=load_run_context(path);database=LocalDatabase(conninfo,run_context=context)
    for subject in subjects:local_run_context.provision_budget(conninfo,context,subject)
    env=dict(CJ_ENV='local',CJ_LOCAL_AUTH_DIR=str(auth),CJ_LOCAL_CONNINFO=str(conninfo),CJ_LOCAL_RUN_CONTEXT=str(path))
    with patch.dict('os.environ',env):app=app_from_environment()
    for subject in subjects:
        token=harness.dev_auth.token(auth,subject,600);headers={'Authorization':'Bearer '+token}
        with TestClient(app)as client:
            chat=harness.expect(client.put('/v1/conversations',params={'conversation_id':subject},headers=headers))
            raw=json.dumps(dict(version='MESSAGE-send.1',conversation_id=subject,message_id=subject,text='bounded local tools',trip_id=None,
                creation_intent='none',expected_generation=chat['generation'],expected_sequence=0)).encode()
            receipt=harness.expect(client.post('/v1/messages',content=raw,headers={**headers,'Content-Type':'application/octet-stream'}))['receipt']
        scope=scope_for(ISSUER,subject);calls=[];limit=None if subject=='legacy-tools'else 1 if subject=='over-bound'else 8192
        def prepare(argument):
            def materialize():
                def invoke():
                    calls.append(argument['key'])
                    yield 'xx'if subject=='over-bound'else'x'
                    yield 'y'
                return invoke
            return InvocationInput(json.dumps(argument,sort_keys=True).encode(),materialize,tool_output_limit=limit)
        worker=run_worker._worker_for_scope(database,FakeProvider(),auth,scope,checker_for(auth))
        worker.budget_exit.registrations={'tool.bound.1':Registration('tool',prepare)}
        class Tools:
            def answer(self,host,binding,messages,**options):
                one=host._registered_stream(binding,'one','tool.bound.1',{'key':'one'})
                if subject=='over-bound':
                    yield from one
                    raise AssertionError('over-bound output escaped original stream guard')
                assert next(one)=='x'
                two=host._registered_stream(binding,'two','tool.bound.1',{'key':'two'})
                if subject=='legacy-tools':
                    try:next(two)
                    except BudgetExceeded:pass
                    else:raise AssertionError('second 48000 reservation exceeded 65536 silently')
                    assert ''.join(one)=='y'
                else:
                    assert next(two)=='x'
                    view=json.loads(host.budget_exit.read_run_capacity(binding,guard=lambda:None))
                    assert view['remaining_calls']==798 and view['remaining_output']==49152
                    assert view['remaining_steps']==22 and view['remaining_tools']==10
                    assert view['admission']=='NOT_GRANTED'
                    assert ''.join(one)==''.join(two)=='y'
                yield 'local tool test complete'
        worker.tools=Tools();outcome,=worker.process()
        account=ledger_scope_for(scope,context.current.meter)
        with database.connect(scope,usage_profile=context.current)as db:
            before=db.execute('SELECT revision,ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()
        ledger=decode(before[1]);binding=Binding(scope,receipt['conversation_id'],receipt['generation'],receipt['message_id'],receipt['run_id'],receipt['sequence'])
        if subject=='small-tools':
            assert outcome.status=='completed'and calls==['one','two']and len(ledger.attempts)==2
            assert all(a.command.output_limit==8192 and a.state=='settled'and a.receipt.actual==1 for a in ledger.attempts.values())
            assert Meter.output_exposure(ledger,binding.run_id)==4
        elif subject=='legacy-tools':
            assert outcome.status=='completed'and calls==['one']and len(ledger.attempts)==1
            assert OperationStore(worker.runs,context.current.meter).read_original(binding,'two').command.output_limit==48000
        else:
            assert outcome.status=='failed'and calls==['one']and len(ledger.attempts)==1
            attempt,=ledger.attempts.values();assert attempt.state=='unknown'and attempt.command.output_limit==1
        original_exit=worker.budget_exit.for_run(binding,worker.runs.snapshot(binding))
        view=original_exit.read_run_capacity(binding,guard=lambda:None)
        with database.connect(scope,usage_profile=context.current)as db:
            assert db.execute('SELECT revision,ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()==before
        assert worker.process()==[]and worker.provider.calls==0
        assert ledger.config==context.current.meter and ledger.config.budget==800
    print('PASS native PG: concurrent 8192 reservations, original 48000 second-denial, over-bound UNKNOWN retained, no replay; SELECT-only capacity/revision unchanged; original800/24/12/65536 and zero real providers')


if __name__=='__main__':
    harness.exercise=exercise;harness.main()
