"""Real ASGI byte observation, bounded native-claim join; no network/provider."""
import asyncio
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import time
import tempfile
from types import SimpleNamespace
import uuid
import pytest

from cj_api.local_app import ISSUER,scope_for
from cj_auth.interfaces import AdmissionStatus
from cj_message.demo_dialogue import _identity
from cj_run.core import Binding
from cj_usage.authorization_budget import canonical
from runtime_adapter.contract import Unavailable

from deploy.hk.app_smoke_outer import OuterCapture,OuterControls,OuterMiddleware,VERSION
from deploy.tests.test_app_smoke_capture import fixture,write,SUBJECTS,NOW

TOKEN='synthetic-credential-never-log-this'
RID='4d2f670b-621a-4ae3-8801-8293fa9a5c23'


class Checker:
    def check(self,token):
        return SimpleNamespace(status=AdmissionStatus.ALLOWED if token==TOKEN else AdmissionStatus.DENIED,
            principal=SimpleNamespace(issuer=ISSUER,subject=SUBJECTS[0]))


class Originals:
    def __init__(self,binding,raw):self.binding,self.raw=binding,raw;self.deny=False;self.fail_after=False
    def _read(self,token,mid,project):
        if self.deny or token!=TOKEN:raise Unavailable('FIXTURE_AUTH_DENIED')
        b=self.binding;assert mid==b.message_id
        receipt=SimpleNamespace(conversation_id=b.conversation_id,generation=b.generation,message_id=mid,
            run_id=b.run_id,sequence=b.message_sequence,input_sha256=sha256(self.raw).hexdigest())
        result=project(b.scope,SimpleNamespace(receipt=receipt,raw=self.raw),(('completed',b.run_id),[],[],None))
        if self.fail_after:raise Unavailable('FIXTURE_SOURCE_CHANGED')
        return result


def setup(tmp_path,*,claim=True,historical=False):
    f=fixture(tmp_path);scope=scope_for(ISSUER,SUBJECTS[0]);mid=str(uuid.uuid4())
    b=Binding(scope,'lio-dialogue-'+_identity(scope,'lio-new:'+mid),'generation',mid,'native-run',1)
    raw=canonical(dict(version='LIO-message.2',message_id=mid,text='question-0',locale='zh',new_conversation=True))
    f.database.original(b,'question-0','zh')
    if historical:
        from cj_api.app_smoke_history import VERSION as HISTORY_VERSION
        def old(cid,message,run):
            return dict(version=HISTORY_VERSION,conversation_id=cid,generation='generation',messages=[dict(
                message_id=message,run_id=run,sequence=1,canonical_sha256=sha256(canonical(dict(text='question-0'))).hexdigest())])
        plan=dict(version='LIO-basic-chain-plan.2',first_setup=False,old_chats=dict(
            zh=old(b.conversation_id,b.message_id,b.run_id),
            en=old('lio-dialogue-'+'f'*32,'old-en','old-en-run')))
        write(tmp_path/'plan.json',plan)
        f.policy['plan_sha256']=sha256(canonical(plan)).hexdigest();write(f.path,f.policy)
        write(f.claims/'claims.json',dict(version='G2C-App-smoke-claims.1',policy_sha256=sha256(f.path.read_bytes()).hexdigest(),state='ACTIVE',claims=[]))
    smoke=f.load()
    if claim:
        smoke.registrations(b)
        f.database.statuses[(scope,b.run_id,mid)]=('completed',3,True)
        smoke.completed([SimpleNamespace(message_id=mid,run_id=b.run_id,status='completed')])
    temporary=tempfile.TemporaryDirectory(prefix='g2c-http-',dir='/tmp')
    directory=Path(temporary.name)/'outer';directory.mkdir(mode=0o700)
    p=tmp_path/'api.json'
    write(p,dict(version=VERSION,policy_path=str(f.path),policy_sha256=sha256(f.path.read_bytes()).hexdigest(),
        directory=str(directory),directory_device=directory.stat().st_dev,directory_inode=directory.stat().st_ino))
    controls=OuterControls(p,SUBJECTS,clock=lambda:f.clock[0])
    originals=Originals(b,canonical({'text':'question-0'}))
    observer=OuterCapture(controls,Checker(),originals,clock=lambda:f.clock[0])
    close=observer.close
    def cleanup():
        try:close()
        finally:temporary.cleanup()
    observer.close=cleanup
    return f,b,raw,directory,observer,originals


def drain(observer):
    end=time.monotonic()+3
    while (observer.queue.unfinished_tasks or observer.read_queue.unfinished_tasks)and time.monotonic()<end:time.sleep(.01)
    assert observer.queue.unfinished_tasks==observer.read_queue.unfinished_tasks==0,'bounded fixture observer did not finish'


def exchange(observer,raw,*,token=TOKEN,path='/v2/lio/messages'):
    async def scenario():
        received=[];sent=[]
        async def app(scope,receive,send):
            while True:
                message=await receive();received.append(message['body'])
                if not message.get('more_body',False):break
            await send({'type':'http.response.start','status':201,'headers':[(b'x-request-id',RID.encode())]})
            await send({'type':'http.response.body','body':b'original response','more_body':False})
        chunks=[raw[:7],raw[7:]]
        async def receive():
            body=chunks.pop(0)
            return {'type':'http.request','body':body,'more_body':bool(chunks)}
        async def send(message):sent.append(message)
        scope={'type':'http','method':'POST','path':path,'headers':[(b'authorization',('Bearer '+token).encode())],
               'query_string':b'private=must-not-log'}
        await OuterMiddleware(app,observer)(scope,receive,send)
        assert b''.join(received)==raw
        assert sent[-1]['body']==b'original response'and sent[0]['status']==201
    asyncio.run(scenario())


def test_original_http_bytes_require_claim_native_read_and_leave_original_response(tmp_path):
    f,b,raw,directory,observer,originals=setup(tmp_path)
    try:
        exchange(observer,raw);drain(observer)
        receipts=list(directory.glob('*.receipt.json'));assert len(receipts)==1
        receipt=json.loads(receipts[0].read_bytes());assert receipt['status']=='CAPTURED'
        data=json.loads((directory/receipt['file']).read_bytes())
        assert data['outer_utf8'].encode()==raw and data['input_sha256']==sha256(raw).hexdigest()
        assert data['binding']==asdict(b)and data['canonical_sha256']!=data['input_sha256']
        assert sha256((directory/receipt['file']).read_bytes()).hexdigest()==receipt['sha256']
        rows=[json.loads(x)for x in(directory/'http-attempts.jsonl').read_text().splitlines()]
        assert [x['phase']for x in rows]==['started','finished']
        assert rows[0]['exchange_id']==rows[1]['exchange_id']and rows[1]['message_id']==b.message_id
        assert rows[1]['request_id']==RID and rows[1]['status']==201
        assert TOKEN not in ''.join(x.read_text()for x in directory.iterdir()if x.is_file())
        assert 'must-not-log'not in ''.join(x.read_text()for x in directory.iterdir()if x.is_file())
        assert all(x.stat().st_mode&0o777==0o600 for x in directory.iterdir())
    finally:observer.close()


def test_actual_http_duplicates_are_counted_before_native_deduplication(tmp_path):
    f,b,raw,directory,observer,originals=setup(tmp_path)
    try:
        exchange(observer,raw);drain(observer);exchange(observer,raw);drain(observer)
        rows=[json.loads(x)for x in(directory/'http-attempts.jsonl').read_text().splitlines()]
        assert len([x for x in rows if x['phase']=='started'])==2
        assert len({x['exchange_id']for x in rows})==2
        assert len(json.loads((f.claims/'claims.json').read_bytes())['claims'])==1
        assert len(list(directory.glob('*.receipt.json')))==1
    finally:observer.close()


def test_foreign_token_and_login_route_are_not_captured(tmp_path):
    f,b,raw,directory,observer,originals=setup(tmp_path)
    try:
        exchange(observer,raw,token='foreign-token')
        exchange(observer,raw,path='/v2/demo-invite-sessions')
        assert {x.name for x in directory.iterdir()}=={'capture-status.sock'}
    finally:observer.close()


def test_missing_claim_never_reconstructs_legacy_outer_or_native_binding(tmp_path):
    f,b,raw,directory,observer,originals=setup(tmp_path,claim=False)
    try:
        exchange(observer,raw);time.sleep(.05);f.clock[0]=NOW+91;drain(observer)
        receipts=list(directory.glob('*.receipt.json'));assert len(receipts)==1
        receipt=json.loads(receipts[0].read_bytes());assert receipt['status']=='UNKNOWN'
        assert not(directory/receipt['file']).exists()
    finally:observer.close()


def test_failed_final_native_guard_cannot_publish_a_captured_receipt_on_retry(tmp_path):
    f,b,raw,directory,observer,originals=setup(tmp_path)
    try:
        originals.fail_after=True
        exchange(observer,raw);drain(observer)
        receipt=json.loads(next(directory.glob('*.receipt.json')).read_bytes());assert receipt['status']=='UNKNOWN'
        originals.fail_after=False
        exchange(observer,raw);drain(observer)
        assert json.loads(next(directory.glob('*.receipt.json')).read_bytes())['status']=='UNKNOWN'
    finally:observer.close()


def test_actual_scoped_get_response_is_retained_without_issuing_another_get(tmp_path):
    f,b,raw,directory,observer,originals=setup(tmp_path)
    response=canonical(dict(version='LIO-timeline.2',conversation_id=b.conversation_id,
                            messages=[dict(message_id=b.message_id,answer='actual read')],next_before=None))
    async def scenario():
        calls=[];sent=[]
        async def app(scope,receive,send):
            calls.append(scope['path'])
            await send(dict(type='http.response.start',status=200,headers=[]))
            await send(dict(type='http.response.body',body=response,more_body=False))
        async def receive():raise AssertionError('GET observer must not read a request body')
        async def send(message):sent.append(message)
        await OuterMiddleware(app,observer)(dict(type='http',method='GET',path='/v2/lio/timeline',
            query_string=('conversation_id='+b.conversation_id).encode(),
            headers=[(b'authorization',('Bearer '+TOKEN).encode())]),receive,send)
        assert calls==['/v2/lio/timeline']and sent[-1]['body']==response
    try:
        asyncio.run(scenario());drain(observer)
        (path,)=directory.glob('*.read.json');data=json.loads(path.read_bytes())
        assert data['response_utf8'].encode()==response and data['selector']=={'conversation_id':b.conversation_id}
        assert data['binding']==asdict(b)and data['route']=='/v2/lio/timeline'
        marker=json.loads(Path(str(path)+'.receipt').read_bytes())
        assert marker['status']=='CAPTURED'and marker['sha256']==sha256(path.read_bytes()).hexdigest()
    finally:observer.close()


def test_unscoped_or_incomplete_get_cannot_become_a_completed_read(tmp_path):
    f,b,raw,directory,observer,originals=setup(tmp_path)
    protected=protected_fixture(observer,originals,b)
    point=protected.http_checkpoint(TOKEN)
    async def scenario():
        async def app(scope,receive,send):
            await send(dict(type='http.response.start',status=200,headers=[]))
            await send(dict(type='http.response.body',body=b'{}',more_body=True))
        async def receive():raise AssertionError()
        async def send(message):pass
        await OuterMiddleware(app,observer)(dict(type='http',method='GET',path='/v2/lio/timeline',
            query_string=('conversation_id='+b.conversation_id).encode(),
            headers=[(b'authorization',('Bearer '+TOKEN).encode())]),receive,send)
    try:
        asyncio.run(scenario());assert observer.queue.unfinished_tasks==0
        assert not list(directory.glob('*.read.json'))
        observed=protected.http_observed(TOKEN,point)
        assert observed['read_coverage']=='UNKNOWN'and len(observed['unknown_read_exchanges'])==1
    finally:observer.close()


def test_dynamic_mid_is_only_the_current_frozen_step_claim_after_checkpoint():
    from deploy.hk.app_smoke_read import step_claim
    from types import SimpleNamespace
    import pytest
    slot=dict(nonce='a'*32,slot_id='zh.SM02')
    other=dict(nonce='b'*32,slot_id='zh.SM04')
    capture=SimpleNamespace(slots=[slot,other])
    step=dict(nonce=slot['nonce'],text='frozen input')
    claim=dict(slot_id=slot['slot_id'],binding=dict(message_id='actual-app-mid'))
    prior=dict(slot_id=other['slot_id'],binding=dict(message_id='other-mid'))
    checkpoint=dict(native_state=dict(message_ids=['old-mid']))
    assert step_claim(capture,[prior,claim],step,None,checkpoint)is claim
    assert step_claim(capture,[claim],step,'actual-app-mid',checkpoint)is claim
    for selected,request_mid,point,reason in [
        ([],None,checkpoint,'NOT_UNIQUE'),
        ([claim,claim],None,checkpoint,'NOT_UNIQUE'),
        ([prior],None,checkpoint,'NOT_UNIQUE'),
        ([claim],'other-mid',checkpoint,'MESSAGE_CHANGED'),
        ([claim],None,dict(native_state=dict(message_ids=['actual-app-mid'])),'PRECEDES'),
    ]:
        with pytest.raises(Unavailable,match=reason):step_claim(capture,selected,step,request_mid,point)
    with pytest.raises(Unavailable,match='NO_SEND_SLOT'):
        step_claim(capture,[claim],dict(nonce=slot['nonce'],text=None),None,checkpoint)
    with pytest.raises(Unavailable,match='NO_SEND_SLOT'):
        step_claim(capture,[claim],dict(nonce='c'*32,text='unfrozen'),None,checkpoint)


def get_exchange(observer,cid,response):
    async def scenario():
        sent=[]
        async def app(scope,receive,send):
            await send(dict(type='http.response.start',status=200,headers=[]))
            await send(dict(type='http.response.body',body=response,more_body=False))
        async def receive():raise AssertionError('no GET request body')
        async def send(message):sent.append(message)
        await OuterMiddleware(app,observer)(dict(type='http',method='GET',path='/v2/lio/timeline',
            query_string=('conversation_id='+cid).encode(),
            headers=[(b'authorization',('Bearer '+TOKEN).encode())]),receive,send)
        assert sent[-1]['body']==response
    asyncio.run(scenario())


def protected_fixture(observer,originals,binding):
    from cj_api.app_smoke_originals import SmokeOriginals
    def history(token,project):
        if token!=TOKEN:raise Unavailable('FIXTURE_AUTH_DENIED')
        return project(SimpleNamespace(scope=binding.scope))
    original=SimpleNamespace(raw=originals.raw,receipt=SimpleNamespace(
        conversation_id=binding.conversation_id,generation=binding.generation,message_id=binding.message_id,
        run_id=binding.run_id,sequence=binding.message_sequence,input_sha256=sha256(originals.raw).hexdigest()))
    originals.query_original=lambda context,mid:original
    originals.boundary=SimpleNamespace(with_history_context=history)
    from deploy.hk.app_smoke_lifecycle import require_live
    instance=observer.lifecycle.instance_id
    return SmokeOriginals(observer.controls,originals,lambda:require_live(observer.controls,instance))


def test_previous_step_get_published_late_is_not_a_new_step_read(tmp_path):
    import threading
    f,b,raw,directory,observer,originals=setup(tmp_path)
    protected=protected_fixture(observer,originals,b)
    response=canonical(dict(conversation_id=b.conversation_id,messages=[]))
    entered=threading.Event();release=threading.Event();publish=observer.publish_read
    def delayed(item,claim):
        entered.set();assert release.wait(10);return publish(item,claim)
    observer.publish_read=delayed
    try:
        original_point=protected.http_checkpoint(TOKEN)
        get_exchange(observer,b.conversation_id,response)
        assert entered.wait(2)
        next_step=protected.http_checkpoint(TOKEN)
        assert not list(directory.glob('*.read.json'))
        release.set();drain(observer)
        assert protected.http_observed(TOKEN,next_step)['actual_reads']==[]
        actual=protected.http_observed(TOKEN,original_point)
        assert actual['post_count']==0 and len(actual['actual_reads'])==1
        data=actual['actual_reads'][0]
        phases=[row['phase']for row in actual['read_exchanges']if row['exchange_id']==data['exchange_id']]
        assert phases==['started','finished','capture_result']
        assert actual['read_coverage']=='OBSERVED'
    finally:release.set();observer.close()


def test_twenty_unclosed_polls_do_not_wait_or_starve_original_post_and_final_get(tmp_path):
    f,b,raw,directory,observer,originals=setup(tmp_path,claim=False)
    response=canonical(dict(conversation_id=b.conversation_id,messages=[]))
    try:
        for _ in range(20):get_exchange(observer,b.conversation_id,response)
        assert observer.queue.unfinished_tasks==observer.read_queue.unfinished_tasks==0
        smoke=f.load();smoke.registrations(b)
        f.database.statuses[(b.scope,b.run_id,b.message_id)]=('completed',3,True)
        smoke.completed([SimpleNamespace(message_id=b.message_id,run_id=b.run_id,status='completed')])
        exchange(observer,raw);drain(observer)
        assert json.loads(next(directory.glob('*.receipt.json')).read_bytes())['status']=='CAPTURED'
        get_exchange(observer,b.conversation_id,response);drain(observer)
        assert len(list(directory.glob('*.read.json')))==1
        rows=[json.loads(line)for line in(directory/'http-attempts.jsonl').read_text().splitlines()]
        assert sum(row.get('capture_status')=='NOT_READY'for row in rows)==20
    finally:observer.close()


def test_full_read_queue_does_not_consume_post_capacity_and_overflow_stays_unknown(tmp_path):
    import threading
    f,b,raw,directory,observer,originals=setup(tmp_path)
    protected=protected_fixture(observer,originals,b)
    response=canonical(dict(conversation_id=b.conversation_id,messages=[]))
    entered=threading.Event();release=threading.Event();publish=observer.publish_read
    def blocked(item,claim):
        entered.set();assert release.wait(10);return publish(item,claim)
    observer.publish_read=blocked
    try:
        point=protected.http_checkpoint(TOKEN)
        get_exchange(observer,b.conversation_id,response);assert entered.wait(2)
        for _ in range(13):get_exchange(observer,b.conversation_id,response)
        assert observer.read_queue.qsize()==12
        exchange(observer,raw)
        assert observer.queue.qsize()==1
        release.set();drain(observer)
        assert json.loads(next(directory.glob('*.receipt.json')).read_bytes())['status']=='CAPTURED'
        rows=[json.loads(line)for line in(directory/'http-attempts.jsonl').read_text().splitlines()]
        assert sum(row.get('capture_status')=='UNKNOWN'for row in rows)==1
        assert sum(row['method']=='POST'and row['phase']=='started'for row in rows)==1
        with pytest.raises(Unavailable,match='LIFECYCLE_INVALID'):protected.http_observed(TOKEN,point)
    finally:release.set();observer.close()


def test_read_artifact_bound_preserves_prior_bytes_and_reports_unknown(tmp_path,monkeypatch):
    from deploy.hk import app_smoke_outer
    monkeypatch.setattr(app_smoke_outer,'MAX_READ_ARTIFACTS',1)
    f,b,raw,directory,observer,originals=setup(tmp_path)
    protected=protected_fixture(observer,originals,b)
    response=canonical(dict(conversation_id=b.conversation_id,messages=[]))
    try:
        point=protected.http_checkpoint(TOKEN)
        get_exchange(observer,b.conversation_id,response);drain(observer)
        old={p.name:p.read_bytes()for p in directory.glob('*.read.json')}
        get_exchange(observer,b.conversation_id,response);drain(observer)
        assert {p.name:p.read_bytes()for p in directory.glob('*.read.json')}==old
        result=protected.http_observed(TOKEN,point)
        assert result['read_coverage']=='UNKNOWN'and len(result['actual_reads'])==1
    finally:observer.close()


def test_completed_http_snapshot_before_worker_witness_is_retained_without_wait(tmp_path):
    f,b,raw,directory,observer,originals=setup(tmp_path,claim=False)
    smoke=f.load();smoke.registrations(b)  # producer return deliberately not yet recorded
    response=canonical(dict(conversation_id=b.conversation_id,
        messages=[dict(message_id=b.message_id,status='completed',answer='actual terminal HTTP snapshot')]))
    try:
        get_exchange(observer,b.conversation_id,response);drain(observer)
        assert len(list(directory.glob('*.read.json')))==1
        data=json.loads(next(directory.glob('*.read.json')).read_bytes())
        assert data['response_utf8'].encode()==response
        claim=json.loads((f.claims/'claims.json').read_bytes())['claims'][0]
        assert claim['producer_return']is None  # read evidence never fabricates a completion witness
    finally:observer.close()


def test_http_metadata_capacity_gap_remains_unknown_after_later_success(tmp_path,monkeypatch):
    from deploy.hk import app_smoke_outer
    f,b,raw,directory,observer,originals=setup(tmp_path)
    protected=protected_fixture(observer,originals,b)
    point=protected.http_checkpoint(TOKEN)
    try:
        monkeypatch.setattr(app_smoke_outer,'HTTP_LOG_LIMIT',10)
        exchange(observer,raw);drain(observer)
        assert(directory/'http-coverage-lost.json').exists()
        monkeypatch.setattr(app_smoke_outer,'HTTP_LOG_LIMIT',16*1024*1024)
        get_exchange(observer,b.conversation_id,canonical(dict(conversation_id=b.conversation_id,messages=[])))
        drain(observer)
        assert len(list(directory.glob('*.read.json')))==1
        with pytest.raises(Unavailable,match='LIFECYCLE_INVALID'):protected.http_observed(TOKEN,point)
    finally:observer.close()


@pytest.mark.parametrize('failure',['write','capacity'])
def test_lost_second_post_metadata_never_reports_one_as_exact_post_count(tmp_path,monkeypatch,failure):
    from deploy.hk import app_smoke_outer
    f,b,raw,directory,observer,originals=setup(tmp_path)
    protected=protected_fixture(observer,originals,b)
    point=protected.http_checkpoint(TOKEN);write_http=observer._write_http;starts=[]
    def lose_one(value):
        if value['method']=='POST'and value['phase']=='started':
            starts.append(value['exchange_id'])
            if len(starts)==2 and failure=='write':raise OSError('synthetic metadata write failure')
        return write_http(value)
    monkeypatch.setattr(observer,'_write_http',lose_one)
    try:
        exchange(observer,raw);drain(observer)
        if failure=='capacity':monkeypatch.setattr(app_smoke_outer,'HTTP_LOG_LIMIT',(directory/'http-attempts.jsonl').stat().st_size)
        exchange(observer,raw);drain(observer)
        assert len(starts)==2
        rows=[json.loads(line)for line in(directory/'http-attempts.jsonl').read_text().splitlines()]
        assert sum(row['method']=='POST'and row['phase']=='started'for row in rows)==1
        assert(directory/'http-coverage-lost.json').exists()
        with pytest.raises(Unavailable,match='LIFECYCLE_INVALID'):protected.http_observed(TOKEN,point)
    finally:observer.close()


def test_old_design_plan_cannot_prepare_a_new_dispatch_packet_without_C_dependency(tmp_path):
    import pytest
    from deploy.hk.app_smoke_prepare import prepare
    target=tmp_path/'must-not-be-created'
    with pytest.raises(ValueError,match='plan.2'):
        prepare(target,dict(version='LIO-basic-chain-plan.1'),{},source='a'*40,
            ledger_id='unused',starts_at='unused',ends_at='unused')
    assert not target.exists()


def test_pending_post_does_not_hold_up_more_than_queue_capacity_closed_old_reads(tmp_path):
    f,b,raw,directory,observer,originals=setup(tmp_path)
    mid2=str(uuid.uuid4())
    b2=Binding(b.scope,'lio-dialogue-'+_identity(b.scope,'lio-new:'+mid2),'generation',mid2,'new-native-run',1)
    f.database.original(b2,'question-1','zh');smoke=f.load();smoke.registrations(b2)
    raw2=canonical(dict(version='LIO-message.2',message_id=mid2,text='question-1',locale='zh',new_conversation=True))
    response=canonical(dict(conversation_id=b.conversation_id,messages=[]))
    try:
        exchange(observer,raw2)
        assert observer.queue.unfinished_tasks==1
        for _ in range(14):
            get_exchange(observer,b.conversation_id,response)
            end=time.monotonic()+2
            while observer.read_queue.unfinished_tasks and time.monotonic()<end:time.sleep(.01)
            assert observer.read_queue.unfinished_tasks==0
        assert observer.queue.unfinished_tasks==1
        assert len(list(directory.glob('*.read.json')))==14
        rows=[json.loads(line)for line in(directory/'http-attempts.jsonl').read_text().splitlines()]
        assert not any(row.get('capture_status')=='UNKNOWN'for row in rows)
    finally:observer.close()


def test_unpublished_partial_read_file_is_not_a_checkpoint_source(tmp_path):
    f,b,raw,directory,observer,originals=setup(tmp_path)
    protected=protected_fixture(observer,originals,b)
    try:
        orphan=directory/('a'*64+'.read.json');orphan.write_bytes(b'{');orphan.chmod(0o600)
        point=protected.http_checkpoint(TOKEN)
        result=protected.http_observed(TOKEN,point)
        assert result['actual_reads']==[]and result['post_count']==0
    finally:observer.close()


def test_append_and_gap_double_failure_stays_invalid_after_disk_recovery_and_restart(tmp_path,monkeypatch):
    from deploy.hk import app_smoke_outer
    from deploy.hk.app_smoke_lifecycle import read_status,require_live
    f,b,raw,directory,observer,originals=setup(tmp_path)
    protected=protected_fixture(observer,originals,b);point=protected.http_checkpoint(TOKEN)
    instance=observer.lifecycle.instance_id;write_http=observer._write_http;marker=app_smoke_outer.publish_marker;starts=[]
    def fail_second(value):
        if value['method']=='POST'and value['phase']=='started':
            starts.append(value['exchange_id'])
            if len(starts)==2:raise OSError('synthetic append unavailable')
        return write_http(value)
    def fail_gap(directory_fd,name,value,**kwargs):
        if name=='http-coverage-lost.json':raise OSError('synthetic gap persistence unavailable')
        return marker(directory_fd,name,value,**kwargs)
    restarted=None
    try:
        monkeypatch.setattr(observer,'_write_http',fail_second)
        monkeypatch.setattr(app_smoke_outer,'publish_marker',fail_gap)
        exchange(observer,raw);drain(observer);exchange(observer,raw);drain(observer)
        assert len(starts)==2 and not(directory/'http-coverage-lost.json').exists()
        rows=[json.loads(line)for line in(directory/'http-attempts.jsonl').read_text().splitlines()]
        assert sum(row['method']=='POST'and row['phase']=='started'for row in rows)==1
        monkeypatch.setattr(observer,'_write_http',write_http)
        monkeypatch.setattr(app_smoke_outer,'publish_marker',marker)
        assert read_status(observer.controls)['lost']is True
        with pytest.raises(Unavailable,match='LIFECYCLE_INVALID'):protected.http_observed(TOKEN,point)
        with pytest.raises(Unavailable,match='LIFECYCLE_INVALID'):protected.http_checkpoint(TOKEN)
        observer.stop.set();observer.thread.join(timeout=1);observer.lifecycle.close()
        restarted=OuterCapture(observer.controls,Checker(),originals,clock=lambda:f.clock[0])
        now=read_status(observer.controls)
        assert now['lost']is False and now['instance_id']!=instance
        with pytest.raises(Unavailable,match='LIFECYCLE_INVALID'):require_live(observer.controls,instance)
        with pytest.raises(Unavailable,match='LIFECYCLE_INVALID'):protected.http_observed(TOKEN,point)
    finally:
        if restarted is not None:restarted.close()
        observer.close()


def test_live_lifecycle_socket_loss_never_becomes_an_empty_success(tmp_path):
    f,b,raw,directory,observer,originals=setup(tmp_path)
    protected=protected_fixture(observer,originals,b);point=protected.http_checkpoint(TOKEN)
    try:
        observer.lifecycle.close()
        with pytest.raises(Unavailable,match='STATUS_UNAVAILABLE'):protected.http_observed(TOKEN,point)
    finally:observer.close()


def test_declared_historical_get_does_not_create_a_worker_or_model_claim(tmp_path):
    f,b,raw,directory,observer,originals=setup(tmp_path,claim=False,historical=True)
    protected=protected_fixture(observer,originals,b)
    response=canonical(dict(conversation_id=b.conversation_id,
        messages=[dict(message_id=b.message_id,status='completed',answer='original historical answer')]))
    try:
        point=protected.http_checkpoint(TOKEN)
        get_exchange(observer,b.conversation_id,response);drain(observer)
        result=protected.http_observed(TOKEN,point)
        assert len(result['actual_reads'])==1 and result['actual_reads'][0]['origin']=='readonly_history'
        assert result['actual_reads'][0]['response_utf8'].encode()==response
        assert json.loads((f.claims/'claims.json').read_bytes())['claims']==[]
        with pytest.raises(Unavailable,match='ORIGINAL_UNAVAILABLE'):
            protected.query(SimpleNamespace(scope=b.scope),b.message_id)
    finally:observer.close()
