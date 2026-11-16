"""Real ASGI byte observation, bounded native-claim join; no network/provider."""
import asyncio
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import time
from types import SimpleNamespace
import uuid

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


def setup(tmp_path,*,claim=True):
    f=fixture(tmp_path);scope=scope_for(ISSUER,SUBJECTS[0]);mid=str(uuid.uuid4())
    b=Binding(scope,'lio-dialogue-'+_identity(scope,'lio-new:'+mid),'generation',mid,'native-run',1)
    raw=canonical(dict(version='LIO-message.2',message_id=mid,text='question-0',locale='zh',new_conversation=True))
    f.database.original(b,'question-0','zh');smoke=f.load()
    if claim:
        smoke.registrations(b)
        f.database.statuses[(scope,b.run_id,mid)]=('completed',3,True)
        smoke.completed([SimpleNamespace(message_id=mid,run_id=b.run_id,status='completed')])
    directory=tmp_path/'outer';directory.mkdir(mode=0o700)
    p=tmp_path/'api.json'
    write(p,dict(version=VERSION,policy_path=str(f.path),policy_sha256=sha256(f.path.read_bytes()).hexdigest(),
        directory=str(directory),directory_device=directory.stat().st_dev,directory_inode=directory.stat().st_ino))
    controls=OuterControls(p,SUBJECTS,clock=lambda:f.clock[0])
    originals=Originals(b,canonical({'text':'question-0'}))
    observer=OuterCapture(controls,Checker(),originals,clock=lambda:f.clock[0])
    return f,b,raw,directory,observer,originals


def drain(observer):
    end=time.monotonic()+3
    while observer.queue.unfinished_tasks and time.monotonic()<end:time.sleep(.01)
    assert observer.queue.unfinished_tasks==0,'bounded fixture observer did not finish'


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
        assert TOKEN not in ''.join(x.read_text()for x in directory.iterdir())
        assert 'must-not-log'not in ''.join(x.read_text()for x in directory.iterdir())
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
        assert not list(directory.iterdir())
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
