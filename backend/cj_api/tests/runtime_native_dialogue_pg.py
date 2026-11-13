"""Private PG/native Lio controls; FakeProvider only, never Hong Kong setup."""
import json
import time
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient

from cj_api.local_app import LocalDatabase,create_local_app,load_confirmation_signer,scope_for,ISSUER
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import checker_for
from cj_api.lio_trip_routes import LioTripBoundary
from cj_api.runtime_undo import NativeUndo
from cj_message.auth_boundary import Boundary
from cj_message.travel import ABI
from cj_trip import lio_history
from cj_trip.domain import CommitUnknown,Denied
from runtime_adapter.contract import decode,encode,Unavailable
import local_history_pg as harness
import dev_auth
import hk_demo_local_check
import local_run_context
import run_worker


def exercise(root,conninfo):
    root.mkdir(mode=0o700)
    auth=root/'auth';subjects=('runtime-native-undo-owner','runtime-native-undo-foreign')
    dev_auth.init(auth,subjects)
    path=root/'conn.json';path.write_text(json.dumps(json.loads(conninfo.read_bytes())))
    meter=root/'meter.json';now=int(time.time())
    meter.write_bytes(encode(dict(version='CJ-LOCAL-RUN@2',current=dict(meter=dict(unit='provider_call',
        budget=80,period_start=now-60,period_end=now+3600,max_steps=8,max_tools=2,max_output=60000,max_seconds=600),
        output_limits=dict(model=4000,tool=2000,memory=1000)),history=[])))
    context=load_run_context(meter)
    for subject in subjects:
        local_run_context.provision_budget(path,context,subject)
        dev_auth.activate_travel(path,subject,context,ABI)
    database=LocalDatabase(path,run_context=context,travel_context=True,needs_context=True,trip_context=True)
    checker=checker_for(auth);signer=load_confirmation_signer(auth)
    model,_=hk_demo_local_check.lio_fixture_model()
    owner,foreign=(dev_auth.token(auth,s,30) for s in subjects)
    scope=scope_for(ISSUER,subjects[0])
    boundary=Boundary(checker,lambda principal:database.message_repository(scope_for(principal.issuer,principal.subject)),
        lambda:str(uuid.uuid4()))
    app=create_local_app(conninfo_path=None,auth_dir=auth,database=database,run_context=context,
        confirmation_signer=signer,account_admission=True,demo_dialogue_subjects=frozenset(subjects),
        lio_dialogue_subjects=frozenset(subjects))
    worker=run_worker._worker_for_scope(database,model,auth,scope,checker,demo_planning=True,
        draft_profile='needs-structured.1',lio_confirmation=signer)
    with TestClient(app) as api:
        headers={'Authorization':'Bearer '+owner,'Content-Type':'application/octet-stream'}
        first=encode(dict(version='LIO-message.2',message_id='native-undo-plan',
            text='Plan a trip to Beijing from 2026-11-11 to 2026-11-12 for two people.',locale='en',new_conversation=True))
        response=api.post('/v2/lio/messages',headers=headers,content=first)
        assert response.status_code==200,response.text
        cid=response.json()['conversation_id']
        assert [o.status for o in worker.process()]==['completed']
        before=api.get('/v2/lio/trip',params={'conversation_id':cid},headers=headers).json()
        assert before['current'] is not None and before['undo_target'] is None,before
        edit=encode(dict(version='LIO-message.2',message_id='native-undo-edit',
            text='Replace the second afternoon with Temple of Heaven.',locale='en',conversation_id=cid))
        assert api.post('/v2/lio/messages',headers=headers,content=edit).status_code==200
        assert [o.status for o in worker.process()]==['completed']
        changed=api.get('/v2/lio/trip',params={'conversation_id':cid},headers=headers).json()
        assert changed['current']!=before['current'] and changed['history'][0]==before['current']
    # The legal native API above supplies the actual Trip and original MESSAGE.
    # Only the outer runtime claim is a local fixture; no expected state is
    # returned by its original reader or the Trip repository.
    setup=encode(dict(kind='task_setup',payload={'task_id':'val-undo'}))
    claims=SimpleNamespace(read=lambda *args,**kwargs:setup,query=lambda context,mid:context.query_lio_message(mid))
    trip=LioTripBoundary(database,checker,signer)
    control=NativeUndo(claims,boundary,trip,lambda:owner)
    request=dict(step_id='native-undo-action',prior_step_ids=['fixture-setup','native-undo-plan','native-undo-edit'])
    calls=model.calls
    assert decode(control.proof(request,deadline=time.monotonic()+30))['status']=='UNKNOWN'
    append=lio_history._append_undo
    def lose_ack(*args):
        append(*args)
        raise CommitUnknown('private native undo committed, response lost')
    with patch.object(lio_history,'_append_undo',side_effect=lose_ack) as writes:
        try:control.dispatch(request,deadline=time.monotonic()+30)
        except Unavailable as error:assert str(error)=='NATIVE_UNDO_ACK_UNCERTAIN_QUERY_ONLY'
        else:raise AssertionError('lost undo acknowledgement was hidden')
        assert writes.call_count==1
    proof=decode(control.proof(request,deadline=time.monotonic()+30))
    assert proof['status']=='PASS' and proof['committed']
    assert proof['history']['current']==before['current'] and len(proof['history']['history'])==2
    assert decode(control.proof(request,deadline=time.monotonic()+30))==proof and model.calls==calls
    other=NativeUndo(claims,boundary,trip,lambda:foreign)
    try:other.proof(request,deadline=time.monotonic()+30)
    except (Denied,Unavailable):pass
    else:raise AssertionError('foreign owner read the native undo original')
    cancel_control(root,database,auth,checker,model,worker,boundary,owner,foreign,scope)
    print('PASS native runtime undo through signed Lio v2/API/Fake plan and edit, real PG Trip authority, lost ACK query-only, repeated proof zero model calls, foreign owner denied')


def cancel_control(root,database,auth,checker,model,worker,boundary,token,foreign,scope):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime,timezone
    from pathlib import Path
    from cj_api.runtime_authority import RuntimeAuthority
    from cj_api.runtime_message_claims import MessageClaims
    from cj_api.runtime_dialogue import NativeDialogue
    from cj_api.runtime_cancel import NativeCancellation
    from cj_api.runtime_controlled_generation import ControlledGeneration
    from cj_api.runtime_originals import RuntimeOriginals
    from cj_api.runtime_native_backend import NativeRuntimeBackend
    from cj_usage.authorization_budget import AuthorizationBudget,CNY_SCALE,journal_state
    from cj_usage.sublimits import activate,scope_hash,operation_id
    from runtime_adapter.contract import VERSION,digest
    from runtime_adapter.profiles import C0
    budget=AuthorizationBudget(root/'cancel-local-fees',clock=lambda:datetime(2026,11,12,tzinfo=timezone.utc))
    budget.begin('retained-local-control','model',b'original pre-allocation fixture')
    base=dict(cap=None,active_cap=None,model_cap=None,tool_cap=None,max_calls=None,model_calls=None,tool_calls=None)
    grants={line:dict(base) for line in ('A','B','L','C','E','F')}
    for line in ('L','C','E','F'):grants[line].update(cap=2*CNY_SCALE,active_cap=2*CNY_SCALE)
    activate(budget,grants,{scope_hash(scope):'E'})
    data=Path(__file__).resolve().parents[3]/'eval/optimization/cases.v2.json'
    from hashlib import sha256
    pins=SimpleNamespace(key='a'*64,raw=b'private-local-controls',value={
        'task_sha256':sha256(data.read_bytes()).hexdigest(),'task_version':decode(data.read_bytes())['version']})
    clock_state={'wall':datetime(2026,11,12,13,5,tzinfo=timezone.utc)}
    authority=RuntimeAuthority(checker,lambda:token,budget,pins,lambda:pins.raw,line='E',wall_clock=lambda:clock_state['wall'])
    directory=root/'cancel-canonical';directory.mkdir(mode=0o700)
    claims=MessageClaims(directory,boundary,lambda:token,authority,pins,history_profile='lio.2')
    artifacts=root/'cancel-evidence';artifacts.mkdir(mode=0o700)
    originals=RuntimeOriginals(boundary,database,budget,artifacts,query_original=claims.query)
    controls=ControlledGeneration()
    cancellation=NativeCancellation(claims,boundary,database,lambda:token,controls,originals)
    dialogue=NativeDialogue(claims,boundary,database,lambda:token,lambda receipt,deadline:None,
        dataset_path=data,cancellation=cancellation)
    # Exact public recipe, same original subject. The local financial holds
    # below test denial only, and are not attributed to this FakeProvider RUN.
    task=dialogue.tasks['dev-cancel'];attempt='native-cancel-control';prior=[]
    def request(kind,payload):
        return dict(version=VERSION,attempt_id=attempt,step_id='runtime-'+digest([scope,attempt,len(prior)]),
            binding_sha256=claims.binding.key,pins_sha256=pins.key,kind=kind,payload=payload,candidate=C0,prior_step_ids=list(prior))
    backend=NativeRuntimeBackend(authority,claims,None,boundary,lambda:token,
        require_worker=lambda binding,pins,deadline:None,wait_original=lambda receipt,deadline:None,
        admit_reflection=None,dialogue=dialogue)
    def send(value,deadline):
        raw=encode(value);fresh=backend.claim(raw,deadline=deadline)
        assert fresh.fresh
        backend.dispatch(raw,capability=fresh.capability,deadline=deadline)
    deadline=time.monotonic()+15
    setup=request('task_setup',dict(task_id='dev-cancel',language='en',setup=task['setup'],dataset_sha256=pins.value['task_sha256']))
    send(setup,deadline);prior.append(setup['step_id'])
    start=request('start_controlled_generation',{'text':task['variants']['en']['turns'][0]})
    worker=run_worker._worker_for_scope(database,model,auth,scope,checker,demo_planning=True,
        runtime_exit_observer_for_run=lambda binding:controls if binding.message_id==start['step_id'] else None)
    calls=model.calls
    with ThreadPoolExecutor(max_workers=2) as pool:
        dispatched=pool.submit(send,start,deadline)
        native=None
        while native is None:
            native=boundary.with_history_context(token,lambda context:context.query_lio_message(start['step_id']))
            assert time.monotonic()<deadline
            if native is None:time.sleep(.01)
        def process():
            with worker.execution_lease():return worker._one(native.receipt)
        running=pool.submit(process)
        while not dispatched.done() and not running.done():time.sleep(.01)
        if running.done():
            result=running.result()
            raise AssertionError(('native worker finished before controlled generation',result,model.calls,calls))
        dispatched.result(timeout=60)
        assert model.calls==calls+1
        prior.append(start['step_id'])
        for _ in range(2):budget.begin(operation_id(scope),'model',b'local allowance denial control')
        clock_state['wall']=datetime(2026,11,12,13,52,tzinfo=timezone.utc)
        with budget.connect() as db:before=journal_state(db)
        try:authority.require(binding=claims.binding,pins_sha256=pins.key,purpose='call',deadline=deadline,read_only=False)
        except Unavailable as error:assert str(error)=='ORIGINAL_LINE_ALLOWANCE_EXHAUSTED'
        else:raise AssertionError('new work bypassed exhausted original allowance')
        cancel=request('cancel_original_run',{'text':task['variants']['en']['turns'][1]})
        from cj_run.cancellation import CancellationUnavailable
        from cj_message.auth_boundary import AccessBlocked,IdentityChanged
        other=NativeCancellation(claims,boundary,database,lambda:foreign,controls,originals)
        try:other.dispatch(cancel,deadline=deadline)
        except (Unavailable,CancellationUnavailable,AccessBlocked,IdentityChanged):pass
        else:raise AssertionError('foreign owner cancelled the controlled original')
        assert decode(originals.inventory(token,start['step_id']))['status']=='running'
        assert not controls.pauses[start['step_id']].release.is_set()
        from threading import Event
        from cj_message.domain import Service as MessageService
        ack_entered,allow_ack=Event(),Event()
        acknowledge=MessageService.acknowledge
        def delayed_ack(service,receipt):
            if receipt.message_id==start['step_id']:
                ack_entered.set()
                if not allow_ack.wait(5):raise AssertionError('cancel ACK test was not released')
            return acknowledge(service,receipt)
        with patch.object(MessageService,'acknowledge',delayed_ack):
            cancellation_sent=pool.submit(send,cancel,deadline)
            try:
                assert ack_entered.wait(5)
                try:cancellation.proof(cancel,deadline=deadline)
                except Unavailable as error:assert str(error)=='NATIVE_CANCEL_DELIVERY_PENDING'
                else:raise AssertionError('cancel proof escaped before original worker ACK')
                assert not cancellation_sent.done()
            finally:allow_ack.set()
            cancellation_sent.result(timeout=60)
        running.result(timeout=60)
    proof=decode(cancellation.proof(cancel,deadline=time.monotonic()+30))
    assert proof['status']=='CANCELLED' and proof['delivery_acknowledged'] is True and model.calls==calls+1
    assert decode(cancellation.proof(cancel,deadline=time.monotonic()+30))==proof
    try:other.proof(cancel,deadline=time.monotonic()+30)
    except (Unavailable,AccessBlocked,IdentityChanged):pass
    else:raise AssertionError('foreign owner read cancellation proof')
    # Withdraw actual local invite qualification after the scoped ACK SELECT,
    # while the native history boundary still owes its final AUTH/source check.
    import psycopg
    invited=auth/'invited.json';invited_before=invited.read_bytes();execute=psycopg.Connection.execute
    revoked=[]
    def revoke_at_ack(connection,query,*args,**kwargs):
        result=execute(connection,query,*args,**kwargs)
        if isinstance(query,str) and query.startswith('SELECT acknowledged FROM cj_message_delivery'):
            invited.write_text('[]\n');revoked.append(True)
        return result
    try:
        with patch.object(psycopg.Connection,'execute',revoke_at_ack):
            try:cancellation.proof(cancel,deadline=time.monotonic()+30)
            except (Unavailable,AccessBlocked,IdentityChanged):pass
            else:raise AssertionError('cancel proof escaped qualification withdrawal during ACK read')
        assert revoked
    finally:invited.write_bytes(invited_before)
    assert decode(cancellation.proof(cancel,deadline=time.monotonic()+30))==proof
    with budget.connect() as db:assert journal_state(db)==before
    assert not claims.claim(encode(cancel),deadline=time.monotonic()+30).fresh
    print('PASS actual native RUN controlled after original Meter settlement, canonical one-use cancel across STOP_NEW/exhausted allowance, original RUN-cancel.2, proof withheld until original worker ACK, foreign cancel/read denied, qualification withdrawal during ACK read withheld, read-only repeat proof and zero new model or financial operations')


if __name__=='__main__':
    harness.exercise=lambda auth,conninfo:exercise(auth.parent/'native-dialogue-controls',conninfo)
    harness.main()
