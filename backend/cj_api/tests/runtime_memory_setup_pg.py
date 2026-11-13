"""One native Memory setup against a fresh private runtime-role database."""
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json
from pathlib import Path
import time
from types import SimpleNamespace
import uuid
from unittest.mock import patch

import local_history_pg as harness
import dev_auth
import local_run_context
import run_worker
from cj_agent.provider import FakeProvider
from cj_api.local_app import LocalDatabase,ISSUER,scope_for
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import checker_for
from cj_api.local_lio_memory import lio_candidates
from cj_api.lio_memory_routes import LioMemoryCards
from cj_api.runtime_authority import RuntimeAuthority
from cj_api.runtime_message_claims import MessageClaims
from cj_api.runtime_memory_setup import NativeMemorySetup
from cj_api.runtime_preparation_input import MEMORY_TASK,MEMORY_QUOTES,MEMORY_SLOTS,preparation_text
from cj_memory.typed_runtime import TypedRuntimeConfiguration
from cj_memory_jobs.model_v2 import SYSTEM as MEMORY_SYSTEM
from cj_message.auth_boundary import Boundary
from cj_message.travel import ABI
from cj_usage.authorization_budget import AuthorizationBudget,CNY_SCALE
from cj_usage.sublimits import activate,scope_hash
from runtime_adapter.contract import VERSION,decode,digest,encode,Unavailable
from runtime_adapter.profiles import C0


def exercise(root,conninfo,language='en',*,lost_ack=False):
    root.mkdir(mode=0o700);auth=root/'auth';subject='runtime-memory-original-owner-'+language
    dev_auth.init(auth,[subject]);owner=scope_for(ISSUER,subject)
    path=root/'conn.json';path.write_bytes(conninfo.read_bytes())
    meter=root/'meter.json';now=int(time.time())
    meter.write_bytes(encode(dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(unit='provider_call',budget=80,
        period_start=now-60,period_end=now+3600,max_steps=8,max_tools=2,max_output=60000,max_seconds=600),
        output_limits=dict(model=4000,tool=2000,memory=1000)),history=[])))
    context=load_run_context(meter);local_run_context.provision_budget(path,context,subject)
    dev_auth.activate_travel(path,subject,context,ABI)
    database=LocalDatabase(path,run_context=context,travel_context=True,needs_context=True,trip_context=True)
    expiry=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
    profile=dict(subjects=['self'],extents=['long_term'],context_ids=[],slots={slot:dict(
        kind='preference',collection_allowed=True,semantic_resolved=True) for slot in MEMORY_SLOTS})
    configuration=TypedRuntimeConfiguration.from_bytes(encode(dict(version='local-memory-run.2',collection=dict(
        version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',expires_at=expiry,
        profiles={subject:profile}),travel_contexts={subject:[]}),selections={subject:dict(subject='self',
        slots=list(MEMORY_SLOTS),max_bytes=1000)})))
    checker=checker_for(auth);token=dev_auth.token(auth,subject,30)
    boundary=Boundary(checker,lambda principal:database.message_repository(scope_for(principal.issuer,principal.subject)),lambda:str(uuid.uuid4()))
    candidates=lio_candidates(database,boundary,frozenset({subject}),configuration.collection)
    cards=LioMemoryCards(candidates.collection,candidates.current)
    budget=AuthorizationBudget(root/'local-financial',clock=lambda:datetime(2026,11,12,tzinfo=timezone.utc))
    budget.begin('retained-memory-local-control','model',b'pre-allocation fixture')
    base=dict(cap=None,active_cap=None,model_cap=None,tool_cap=None,max_calls=None,model_calls=None,tool_calls=None)
    grants={line:dict(base) for line in ('A','B','L','C','E','F')}
    for line in ('L','C','E','F'):grants[line].update(cap=10*CNY_SCALE,active_cap=10*CNY_SCALE)
    activate(budget,grants,{scope_hash(owner):'E'})
    data=Path(__file__).resolve().parents[3]/'eval/optimization/cases.v2.json'
    pins=SimpleNamespace(key='b'*64,raw=b'local-memory-setup-pins',value=dict(task_sha256=sha256(data.read_bytes()).hexdigest()))
    authority=RuntimeAuthority(checker,lambda:token,budget,pins,lambda:pins.raw,line='E',
        wall_clock=lambda:datetime(2026,11,12,13,5,tzinfo=timezone.utc))
    directory=root/'canonical';directory.mkdir(mode=0o700)
    claims=MessageClaims(directory,boundary,lambda:token,authority,pins,history_profile='lio.2')
    quotes=MEMORY_QUOTES[language];text=preparation_text(MEMORY_TASK,language)
    class Model(FakeProvider):
        def stream(self,messages,system=None):
            if system!=MEMORY_SYSTEM:
                yield from super().stream(messages,system)
                return
            self.calls+=1
            original,=json.loads(messages[0]['content'])['messages']
            entries=[dict(subject='self',slot=slot,kind='preference',
                text=quote,extent='long_term',occurred_at='date unknown',evidence=[dict(ref=original['ref'],quote=quote)])
                for slot,quote in zip(MEMORY_SLOTS,quotes)] if original['text']==text else []
            yield encode(dict(version='MEMORY-EXTRACT@2',entries=entries)).decode()
    model=Model()
    worker=run_worker._worker_for_scope(database,model,auth,owner,checker,memory_configuration=configuration,
        demo_planning=True,lio_memory_enabled=True)
    def wait(receipt,deadline):
        with worker.execution_lease():outcome=worker._one(receipt)
        assert outcome.status=='completed',outcome
    setup=NativeMemorySetup(claims,boundary,database,lambda:token,configuration.collection,candidates,cards,wait)
    setup.require_available()
    request=dict(version=VERSION,attempt_id='native-memory-control',step_id='runtime-'+digest([owner,'native-memory-control',0]),
        binding_sha256=claims.binding.key,pins_sha256=pins.key,kind='task_setup',payload=dict(task_id=MEMORY_TASK,
        language=language,setup='public fixture recipe',dataset_sha256=pins.value['task_sha256']),candidate=C0,prior_step_ids=[])
    deadline=time.monotonic()+60;raw=encode(request);fresh=claims.claim(raw,deadline=deadline)
    assert fresh.fresh;claims.consume(raw,fresh.capability,deadline=deadline)
    if lost_ack:
        import cj_api.runtime_memory_stop as native_stop
        from cj_memory.operation import OperationWithheld
        original_execute=native_stop.execute
        writes=[]
        def lose_response(*args):
            result=original_execute(*args);writes.append(decode(result)['action_id'])
            raise OperationWithheld('local_response_lost',writes[-1],True)
        with patch.object(native_stop,'execute',side_effect=lose_response):
            try:setup.dispatch(request,deadline=deadline)
            except Unavailable as error:
                assert str(error)=='NATIVE_STOP_USE_ACK_UNCERTAIN_QUERY_ONLY'
            else:raise AssertionError('committed lost acknowledgement was hidden')
        assert len(writes)==1
    else:setup.dispatch(request,deadline=deadline)
    proof=decode(setup.proof(request,deadline=deadline))
    assert proof['status']=='PASS' and proof['items']['stopped']['status']=='withdrawn' and proof['items']['control']['status']=='active'
    assert model.calls==2,model.calls
    calls=model.calls
    assert decode(setup.proof(request,deadline=deadline))==proof and model.calls==calls
    assert not claims.claim(raw,deadline=deadline).fresh
    original=boundary.with_history_context(token,lambda current:claims.query(current,request['step_id']))
    with database.connect(owner) as db:
        assert db.execute('SELECT count(*) FROM cj_run_metered_operation WHERE run_id=%s',(original.receipt.run_id,)).fetchone()==(2,)
        assert db.execute('SELECT count(*) FROM cj_message_receipt').fetchone()==(1,)
        assert db.execute("SELECT count(*) FROM cj_memory_management_action WHERE operation='withdraw'").fetchone()==(1,)
    recall='native-memory-new-chat'
    from cj_api.runtime_message_input import lio_input
    sent=boundary.receive_lio(token,encode(dict(version='LIO-message.2',message_id=recall,
        text='我还有哪些旅行偏好？' if language=='zh' else 'What travel preferences do you still know about me?',locale=language,new_conversation=True)),
        prepare_scope=database._provision_scope,version='LIO-message.2')
    actual=boundary.with_history_context(token,lambda current:claims.query(current,recall))
    assert actual.receipt.conversation_id!=original.receipt.conversation_id
    wait(actual.receipt,time.monotonic()+60)
    with database.connect(owner) as db:
        raw,=db.execute("SELECT input_bytes FROM cj_run_metered_operation WHERE run_id=%s AND kind='model'",(actual.receipt.run_id,)).fetchone()
        assert quotes[0].encode() not in bytes(raw) and quotes[1].encode() in bytes(raw)
    print('PASS new native Lio conversation recalls the retained positive preference, not the stopped statement, in actual registered model input')
    print('PASS original preparatory MESSAGE/RUN holds both actual model/Memory Meter calls; two native Remember choices refresh target epoch, typed STOP-USE and retained positive control, repeat proof zero dispatch')


if __name__=='__main__':
    def both(auth,conninfo):
        for language in ('zh','en'):
            exercise(auth.parent/('native-memory-'+language),conninfo,language,lost_ack=language=='zh')
    harness.exercise=both
    harness.main()
