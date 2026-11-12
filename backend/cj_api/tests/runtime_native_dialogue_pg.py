"""Private PG/native Lio controls; FakeProvider only, never Hong Kong setup."""
import json
import time
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
        lambda:'unused-native-undo-generation')
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
    print('PASS native runtime undo through signed Lio v2/API/Fake plan and edit, real PG Trip authority, lost ACK query-only, repeated proof zero model calls, foreign owner denied')


if __name__=='__main__':
    harness.exercise=lambda auth,conninfo:exercise(auth.parent/'native-dialogue-controls',conninfo)
    harness.main()
