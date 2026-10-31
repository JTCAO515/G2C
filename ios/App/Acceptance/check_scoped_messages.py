"""#337 scoped-message App prefix; actual signed API/PG/run_once/Fake only.

Frozen send.4/RUN and TRIP-scoped-discovery.1. Worker outcomes remain backend
oracles only; no candidate ID is supplied to the App. All Trip sources are created
by the signed MESSAGE/worker/confirmation/source-initialize chain.
"""
import os,sys,json,time,tempfile,subprocess,uuid,base64,hashlib,argparse,threading,importlib.util,plistlib
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--simulator',required=True);parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--build-dir',type=Path,required=True);parser.add_argument('--run-context',type=Path,required=True)
parser.add_argument('--case',choices=['testScopedItemAndLanguageSwitch','testScopedDayChineseLargest','testScopedUndeterminedDayWithoutModel','testScopedCandidateAccept','testScopedCandidateReject','testScopedCandidateACKLoss','testScopedCandidateConflict','testScopedCandidateWithdrawal','testScopedCandidateLateAccount','testScopedCandidateStaleAcceptance','testScopedCandidateDiscoveryUnavailable'],required=True)
ARGS=parser.parse_args();OUT=ARGS.output.resolve();BUILD=ARGS.build_dir.resolve();CASE=ARGS.case
if OUT.is_relative_to(ROOT) or BUILD.is_relative_to(ROOT):raise ValueError('external evidence required')
if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT):raise ValueError('commit candidate first')
os.umask(0o077);OUT.mkdir(parents=True,mode=0o700)
if (OUT/'report.json').exists():raise ValueError('preserve historical report')
sys.path.insert(0,str(ROOT/'scripts'))
for key in tuple(os.environ):
 if key.startswith(('PG','LIBPQ','CJ_LOCAL_','G2C_DEV_')):os.environ.pop(key)
os.environ['CJ_ENV']='local'
import psycopg,dev_auth,migrate
from pg_suites import cluster
from fastapi.testclient import TestClient
from cj_api.local_app import create_local_app,LocalDatabase,ISSUER,scope_for
from cj_api.local_run_context import load_run_context
from cj_agent.provider import FakeProvider
from run_worker import run_once
from cj_trip.confirmation import ConfirmationSigner
from cj_trip.local_needs_app import create_local_needs_app
from cj_trip.local_structured_read import create_local_structured_read_app
from cj_trip.domain import packed
import uvicorn
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
from cj_api.local_app import load_history_configuration
r={'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'status':'RUNNING','layer':'actual simulator/signed API/private PG/formal run_once/Fake synthetic','cases':{},'unrun':['expansion/clarification pending B360/C336','real accounts/models/services/fees/cloud','physical device/VoiceOver']}
def save():(OUT/'report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
def expect(response,phase):
 r.setdefault('setup_responses',[]).append(dict(phase=phase,status=response.status_code,error=response.json().get('error')));save();assert response.status_code==200,(phase,response.status_code,response.text)
 return response.json()
def known(x):return dict(state='known',value=x)
def event(date,clock):return dict(date=known(date),time=known(clock),timezone=known('Asia/Shanghai'),utc_offset=known('+08:00'))
sources=[*list((ROOT/'ios/App').glob('*.swift')),HERE/'DevelopmentScopedMessageUITests.swift',Path(__file__)]
for name in ('CJManualPreviewClient','CJShell','CJMessageClient','CJRunClient','CJTripClient','CJNeedsClient','CJMemoryClient'):
 sources+=list((ROOT/'ios/Modules'/name/'Sources').rglob('*.swift'))
r['source_hashes']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources};save()
try:
 with tempfile.TemporaryDirectory(prefix='cj337-native-',dir='/tmp') as temporary:
  root=Path(temporary)
  with cluster('scopedsourceapp',port=55827,role='cj21_source_init_initializer',root=root/'pg') as config:
   with psycopg.connect(**config,autocommit=True) as conn:
    chain=migrate.load();migrate.up(conn,chain,chain[-1]['version'])
   connection=root/'connection.json';connection.write_text(json.dumps(config));connection.chmod(0o600)
   auth=root/'auth';subject='cj21-source-'+uuid.uuid4().hex;other_subject='cj337-other-'+uuid.uuid4().hex
   dev_auth.init(auth,[subject,other_subject] if CASE=='testScopedCandidateLateAccount' else [subject])
   path=ARGS.run_context.resolve();context=load_run_context(path);assert context.version=='CJ-LOCAL-RUN@2';r['run_context']=json.loads(path.read_text());save()
   os.environ.update(CJ_LOCAL_CONNINFO=str(connection),CJ_LOCAL_AUTH_DIR=str(auth),CJ_LOCAL_RUN_CONTEXT=str(path))
   for budget_subject in ([subject,other_subject] if CASE=='testScopedCandidateLateAccount' else [subject]):
    subprocess.run([sys.executable,'-B',str(ROOT/'scripts/local_run_context.py'),'--conninfo-json',str(connection),'--auth-dir',str(auth),'--run-context',str(path),'--subject',budget_subject,'init-budget'],cwd=ROOT,check=True,capture_output=True)
   dev_auth.activate_travel(connection,subject,context,'MESSAGE-TRAVEL-CONSUMER@1')
   signer=ConfirmationSigner(b'synthetic-source-init-app-only-signing-123456789')
   api=create_local_app(conninfo_path=connection,auth_dir=auth,run_context=context,travel_context=True,needs_profile='manual-v1',confirmation_signer=signer)
   headers={'Authorization':'Bearer '+dev_auth.token(auth,subject,120)};binary={**headers,'Content-Type':'application/octet-stream'}
   native_tokens=dict(A=headers['Authorization'][7:])
   if CASE=='testScopedCandidateLateAccount':native_tokens['B']=dev_auth.token(auth,other_subject,120)
   def fixed(key,start,end):
    def edge(clock):return dict(date=known('2026-11-02'),time=known(clock),timezone=known('Asia/Shanghai'),place=dict(state='unknown'))
    return dict(item_id=key,kind='appointment',description='SYNTHETIC declared source '+key,applies_to=['self'],locked=known(False),booking_status=dict(state='unknown'),start=edge(start),end=edge(end))
   class SyntheticSource(FakeProvider):
    def stream(self,messages,system=None):
     for chunk in super().stream(messages,system):
      if system is not None:
       value=json.loads(chunk);value['title']='SYNTHETIC scoped source';yield json.dumps(value)
      else:yield chunk
   with TestClient(api) as client:
    needs=dict(action_id='synthetic-source',needs_id='visit',expected_version=0,source=dict(kind='manual',text='SYNTHETIC explicit source'),changes=dict(party_size=known(1)))
    expect(client.post('/v1/needs-actions',content=packed(needs),headers=binary),'actual-needs-save')
    chat=expect(client.put('/v1/conversations',params={'conversation_id':'synthetic-source'},headers=headers),'actual-chat')
    command=dict(version='MESSAGE-send.2',conversation_id='synthetic-source',message_id='synthetic-original',text='SYNTHETIC operator original planning request',trip_id=None,creation_intent='consider_trip',expected_generation=chat['generation'],expected_sequence=0,travel_context=None,needs_reference=dict(id='visit',expected_version=1))
    receipt=expect(client.post('/v2/messages',content=packed(command),headers=binary),'actual-message')['receipt']
    database=LocalDatabase(connection,run_context=context,travel_context=True,needs_context=True);model=SyntheticSource();outcomes=run_once(database,model,auth)
    r['worker_outcomes']=[dict(status=x.status,proposal_id=x.proposal_id) for x in outcomes];r['provider_calls']=model.calls;save();assert len(outcomes)==1 and outcomes[0].status=='completed'
    proposal=expect(client.get('/v1/trip-proposals',params={'proposal_id':outcomes[0].proposal_id},headers=headers),'actual-proposal')['proposal']
    confirmation=expect(client.post('/v1/trip-confirmations',json=dict(action_id='synthetic-accept',kind='accept',proposal_id=outcomes[0].proposal_id,candidate_hash=proposal['candidate_hash']),headers=headers),'actual-confirmation')
    action=base64.b64decode(confirmation['action_utf8_base64']);adopted=expect(client.post('/v1/trip-actions',content=action,headers=binary),'actual-legacy-adopt')['receipt'];tid=adopted['trip_id']
   original=database.trip_repository(scope_for(ISSUER,subject)).detail(tid);doc=json.loads(original.content);r['original_version']=original.version
   schedules=[(event('2026-11-02','23:30:00'),event('2026-11-03','00:30:00')),(event('2026-11-03','09:15:00'),event('2026-11-03','10:00:00')),(event('2026-11-04','08:00:00'),event('2026-11-04','09:00:00'))]
   if CASE=='testScopedDayChineseLargest':
    # Independent explicit synthetic declarations for the READY date positive.
    # Unknown/cross-day scope is retained in its own real zero-model negative.
    schedules=[(event('2026-11-02','09:00:00'),event('2026-11-02','10:00:00')),(event('2026-11-03','09:15:00'),event('2026-11-03','10:00:00')),(event('2026-11-04','08:00:00'),event('2026-11-04','09:00:00')),(event('2026-11-05','09:00:00'),event('2026-11-05','10:00:00'))]
   r['fixture_profile']='synthetic-fully-known-day-v1' if CASE=='testScopedDayChineseLargest' else 'synthetic-undetermined-crossday-v1'
   unknown={key:dict(state='unknown') for key in ('date','time','timezone','utc_offset')}
   items=[]
   for index,item in enumerate(doc['items']):
    start,end=schedules[index] if index<len(schedules) else (unknown,unknown)
    items.append(dict(id=item['id'],schedule=dict(start=start,end=end),fixed=known(False)))
   initialization=dict(version='TRIP-initialize.1',request_id='synthetic-initialize-source',trip_id=tid,expected_version=original.version,original_hash=hashlib.sha256(original.content).hexdigest(),items=items)
   source=create_local_needs_app(conninfo_path=connection,auth_dir=auth,run_context=context,confirmation_signer=signer)
   with TestClient(source) as client:
    prep=expect(client.post('/v1/trip-source-initializations',content=packed(dict(version='TRIP-source-initialize.1',needs_reference=dict(id='visit',expected_version=1),initialization=initialization)),headers=binary),'source-aware-prepare')['preparation']
    r['association']=prep['item_source_association'];assert r['association']['status']=='UNKNOWN'
    saved=expect(client.post('/v1/trip-source-initialization-saves',content=packed(dict(version='TRIP-source-initialize-save.1',action_id='synthetic-source-save',proposal_id=prep['proposal_id'],candidate_hash=prep['candidate_hash'])),headers=binary),'source-aware-save')['receipt'];assert saved['trip_id']==tid and saved['committed_version']==2
   with TestClient(create_local_structured_read_app(conninfo_path=connection,auth_dir=auth,run_context=context)) as client:
    listing=expect(client.get('/v1/trip-structured-list',headers=headers),'actual-structured-list');detail=expect(client.get('/v5/trip-structured',params={'trip_id':tid},headers=headers),'actual-structured-detail')
    r['discovered']=listing['trips'];r['structured']=detail['trip'];assert detail['trip']['version']==2 and detail['trip']['content']['content_version']=='structured.1'
   from cj_memory.typed_local import TypedConfiguration
   from cj_memory.typed_api import create_local_typed_app
   from cj_memory.edit_runtime import EditRuntimeConfiguration
   from cj_draft.scoped_publisher import local_configuration
   from cj_trip.local_scoped_app import create_local_scoped_app
   from cj_message.travel import Selection
   from cj_feasibility.solver import Limits
   import message_edit_profile
   with TestClient(api) as client:
    def namespace(label):
     return expect(client.post('/v1/travel-context-actions',content=packed(dict(version='TRAVEL-context-action.1',action_id=label,operation='create',travel_context=None)),headers=binary),label)['receipt']['travel_context']
    selected_namespace=namespace('synthetic-explicit-namespace');other_namespace=namespace('synthetic-independent-namespace')
   profile=dict(subjects=['self'],slots={slot:dict(kind='preference',collection_allowed=True,semantic_resolved=True) for slot in ('food','pace')},extents=['long_term','current'],context_ids=[])
   collection=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',expires_at=datetime.fromtimestamp(context.current.meter.period_end,timezone.utc).isoformat(),profiles={subject:profile}),travel_contexts={subject:[selected_namespace['id'],other_namespace['id']]})
   typed=TypedConfiguration.from_bytes(packed(collection));memory=EditRuntimeConfiguration.from_bytes(packed(dict(version='local-memory-edit-run.1',collection=collection,selections={subject:dict(subject='self',slots=['food','pace'],max_bytes=2000)})))
   with TestClient(create_local_typed_app(conninfo_path=connection,auth_dir=auth,configuration=typed)) as client:
    for item,slot,text,ns in [('long','food','SYNTHETIC LONG vegetarian',None),('current','pace','SYNTHETIC CURRENT slow',selected_namespace),('other','pace','SYNTHETIC OTHER do not leak',other_namespace)]:
     command=dict(version='MEMORY-manual.2',operation_id='synthetic-memory-'+item,item_id='synthetic-memory-'+item,subject='self',slot=slot,kind='preference',text=text,extent='long_term' if ns is None else 'current',context=None if ns is None else dict(kind='travel',id=ns['id'],expected_version=ns['version']),occurred_at='SYNTHETIC date unknown')
     expect(client.post('/v2/memories',content=packed(command),headers=binary),'actual-typed-memory-'+item)
   credentials={scope_for(ISSUER,subject):headers['Authorization'][7:]}
   limits=Limits(datetime(2026,11,1,tzinfo=timezone.utc),7*86400,1,10_000_000,60,120,128,.05,.05,100)
   edit_db,configuration=local_configuration(conninfo_path=connection,auth_dir=auth,run_context=context,memory=memory,credentials=credentials.__getitem__,confirmation=signer,limits=limits,language='en')
   message_edit_profile.activate(connection,subject,context,configuration,Selection(selected_namespace['id'],selected_namespace['version']))
   edit_api=create_local_app(conninfo_path=connection,auth_dir=auth,run_context=context,travel_context=True,edit_configuration=configuration,needs_profile='manual-v1',history_configuration=load_history_configuration(auth))
   if CASE=='testScopedCandidateLateAccount':
    other_headers={'Authorization':'Bearer '+native_tokens['B']}
    with TestClient(edit_api) as client:expect(client.get('/v1/message-receipts',params=dict(message_id='synthetic-session-probe'),headers=other_headers),'actual-B-session-readiness')
   class ScopedFake(FakeProvider):
    def __init__(self):super().__init__();self.inputs=[]
    def stream(self,messages,system=None):
     self.calls+=1;self.inputs.append(messages);yield ''
     prompt=json.loads(system);assert prompt['version']=='TRIP-scoped-model.1'
     yield packed(dict(version=prompt['edit_version'],request_id=prompt['request_id'],trip_id=prompt['trip_id'],expected_version=prompt['expected_version'],original_hash=prompt['original_hash'],title=None,order=None,changes=[dict(item_id=prompt['selected_item_ids'][0],field='text',value='SYNTHETIC lighter choice / 本次轻松一点')])).decode()
   formal=detail['trip'];spec=dict(id=tid,title=formal['content']['title'],version=formal['version'],content_sha256=formal['content_sha256'],item_ids=[item['id'] for item in formal['content']['items']])
   cid=CASE
   with TestClient(edit_api) as client:expect(client.put('/v1/conversations',params=dict(conversation_id=cid),headers=headers),'native-original-chat')
   structured=create_local_structured_read_app(conninfo_path=connection,auth_dir=auth,run_context=context)
   scoped_app=create_local_scoped_app(database=edit_db,configuration=configuration)
   typed_app=create_local_typed_app(conninfo_path=connection,auth_dir=auth,configuration=typed)
   fake=ScopedFake();finished=[];actual_message_receipts=[];worker_errors=[];stop=threading.Event();audit=[];lock=threading.RLock()
   late_captured=threading.Event();late_release=threading.Event();late_state={}
   async def observed(scope,receive,send):
    path=scope.get('path','')
    if scope.get('type')!='http':return await edit_api(scope,receive,send)
    entry=dict(method=scope['method'],path=path);audit.append(entry);chunks=[];reply=[]
    if path in ('/v1/trip-scoped-action-receipts','/v1/trip-scoped-discovery'):entry['original_query']=parse_qs(scope.get('query_string',b'').decode('ascii'))
    async def received():
     message=await receive()
     if message['type']=='http.request':chunks.append(message.get('body',b''))
     return message
    drop_ack=CASE=='testScopedCandidateACKLoss' and path=='/v1/trip-scoped-actions' and scope['method']=='POST'
    hold_discovery=CASE=='testScopedCandidateLateAccount' and path=='/v1/trip-scoped-discovery'
    actual_reply=[]
    async def sent(message):
     if message['type']=='http.response.start':entry['status']=message['status']
     if path=='/v4/messages' and message['type']=='http.response.body':reply.append(message.get('body',b''))
     if drop_ack or hold_discovery:actual_reply.append(message)
     else:await send(message)
    target=structured if path in ('/v1/trip-structured-list','/v5/trip-structured') else scoped_app if path.startswith('/v1/trip-scoped-') else typed_app if path.startswith(('/v2/memor','/v2/memory-')) else edit_api
    await target(scope,received,sent)
    if drop_ack:
     # Fault only after the unmodified C API completed its real transaction.
     # Withhold its original 200 body; this is explicit proxy ACK loss, not a
     # forged successful receipt or a replacement action/model result.
     assert entry['status']==200
     original_body=b''.join(part.get('body',b'') for part in actual_reply if part['type']=='http.response.body')
     entry.update(actual_backend_reply_sha256=hashlib.sha256(original_body).hexdigest(),delivered_status=503,committed_response_suppressed=True)
     trace=str(uuid.uuid4());failure=packed(dict(request_id=trace,error=dict(code='TRIP_OUTCOME_UNKNOWN',category='dependency',message_en='Synthetic committed response loss',message_zh='合成已提交回包丢失',outcome='unknown',recovery='reconcile_original')))
     await send(dict(type='http.response.start',status=503,headers=[(b'content-type',b'application/json'),(b'cache-control',b'no-store'),(b'x-request-id',trace.encode())]))
     await send(dict(type='http.response.body',body=failure))
    if hold_discovery:
     assert entry['status']==200
     started=time.monotonic();late_state['captured_original_status']=200;late_captured.set()
     import asyncio
     released=await asyncio.to_thread(late_release.wait,25)
     assert released,'late original delivery was never released'
     late_state['release_elapsed_seconds']=time.monotonic()-started
     for message in actual_reply:await send(message)
     late_state['original_response_delivered']=True
    if path=='/v1/trip-scoped-discovery':entry['completed']=True
    if path=='/v4/messages' and entry.get('status')==200:actual_message_receipts.append(json.loads(b''.join(reply))['receipt'])
    if scope['method']=='POST':
     raw=b''.join(chunks);entry['input_sha256']=hashlib.sha256(raw).hexdigest()
     if path=='/v1/trip-scoped-actions':entry['original_action_id']=json.loads(raw)['action_id']
   server=uvicorn.Server(uvicorn.Config(observed,host='127.0.0.1',port=0,log_level='error',access_log=False))
   import socket
   sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen();endpoint='http://127.0.0.1:'+str(sock.getsockname()[1])
   api_thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);api_thread.start()
   def worker():
    while not stop.wait(.05):
     try:
      results=run_once(edit_db,fake,auth)
      if results:
       with lock:
        finished.extend(dict(status=x.status,proposal_id=x.proposal_id) for x in results)
        r['native_worker_outcomes']=list(finished);r['native_provider_calls']=fake.calls;save()
     except Exception as error:
      worker_errors.append(type(error).__name__);stop.set()
   worker_thread=threading.Thread(target=worker,daemon=True);worker_thread.start()
   def proof():
    owner=scope_for(ISSUER,subject)
    with edit_db.connect(owner) as conn:
     role=conn.execute('SELECT current_user').fetchone()[0];assert role=='cj_m1_runtime'
     rows=conn.execute('SELECT message_id,raw_input,run_id FROM cj_message_receipt WHERE conversation_id=%s',(cid,)).fetchall()
     formal_rows=conn.execute('SELECT trip_id,version,content FROM cj_trip_record').fetchall()
     operations=conn.execute('SELECT count(*) FROM cj_run_metered_operation o JOIN cj_message_receipt m ON (m.scope,m.run_id)=(o.scope,o.run_id) WHERE m.conversation_id=%s',(cid,)).fetchone()[0]
     pending=conn.execute('SELECT count(*) FROM cj_trip_scoped_basis').fetchone()[0]
    assert len(rows)==1 and len(formal_rows)==1 and formal_rows[0][0]==tid and formal_rows[0][1]==2 and bytes(formal_rows[0][2])==packed(formal['content'])
    command=json.loads(bytes(rows[0][1]));assert command['version']=='MESSAGE-send.4' and command['creation_intent']=='none' and command['trip_id'] is None and command['modification_intent']=='propose_scoped_edit'
    with TestClient(edit_api) as client:
     display=expect(client.get('/v4/run-display',params=dict(message_id=rows[0][0]),headers=headers),'oracle-original-run');draft=expect(client.get('/v5/run-draft-status',params=dict(message_id=rows[0][0]),headers=headers),'oracle-original-draft')
    reference=display['reference'];assert reference==draft['reference'] and reference['trip_context']==command['trip_context'] and reference['namespace']['id']==selected_namespace['id'] and reference['needs_reference']==dict(id='visit',expected_version=1)
    posts=[x for x in audit if x['method']=='POST' and x['path']=='/v4/messages']
    forbidden=[x for x in audit if x['method'] not in ('GET','HEAD') and not (x['method']=='POST' and x['path']=='/v4/messages')]
    assert [x['input_sha256'] for x in posts]==[hashlib.sha256(bytes(row[1])).hexdigest() for row in rows]
    inputs=json.dumps(fake.inputs,ensure_ascii=False)
    value=dict(runtime_role=role,messages=len(rows),posts=len(posts),model_calls=fake.calls,registered_operations=operations,
     formal_version=formal_rows[0][1],formal_count=len(formal_rows),pending_proposals=pending,forbidden_writes=len(forbidden),
     status=display['snapshot']['status'],draft_outcome=draft['draft_outcome'],trip_id=reference['trip_context']['id'],content_sha256=reference['trip_context']['content_sha256'],namespace=reference['namespace']['id'],needs_version=reference['needs_reference']['expected_version'],item_ids=reference['trip_context']['item_ids'],day=None if reference['trip_context']['day'] is None else reference['trip_context']['day']['date'],
     memory_long='SYNTHETIC LONG' in inputs,memory_current='SYNTHETIC CURRENT' in inputs,memory_other='SYNTHETIC OTHER' in inputs)
    r['proof']=value;r['observed_requests']=list(audit);r['worker_outcomes']=list(finished);r['proposal_ids_are_backend_oracles_only']=True;save();return value
   def discovery_refusal_proof():
    assert CASE=='testScopedCandidateDiscoveryUnavailable' and len(actual_message_receipts)==1
    deadline=time.monotonic()+5
    while True:
     reads=[x for x in audit if x['path']=='/v1/trip-scoped-discovery']
     if len(reads)==2 and all(x.get('completed') for x in reads):break
     if time.monotonic()>deadline:raise TimeoutError('two original discovery refusals')
     time.sleep(.05)
    original=actual_message_receipts[0]
    assert all(x['status']==503 and x['original_query']==dict(message_id=[original['message_id']],run_id=[original['run_id']]) for x in reads)
    with edit_db.connect(scope_for(ISSUER,subject)) as conn:
     assert conn.execute('SELECT count(*) FROM cj_trip_scoped_action').fetchone()[0]==0
     trips=conn.execute('SELECT trip_id,version,content FROM cj_trip_record').fetchall()
     messages=conn.execute('SELECT count(*) FROM cj_message_receipt WHERE conversation_id=%s',(cid,)).fetchone()[0]
     operations=conn.execute('SELECT count(*) FROM cj_run_metered_operation o JOIN cj_message_receipt m ON (m.scope,m.run_id)=(o.scope,o.run_id) WHERE m.conversation_id=%s',(cid,)).fetchone()[0]
    assert messages==operations==fake.calls==len(trips)==1 and trips[0][0]==tid and trips[0][1]==2 and bytes(trips[0][2])==packed(formal['content'])
    assert not any(x['path']=='/v1/trip-scoped-actions' for x in audit)
    r['discovery_refusal_proof']=dict(reads=2,statuses=[x['status'] for x in reads],same_original_association=True,messages=1,model_calls=1,registered_operations=1,actions=0,formal_version=2)
    save();return r['discovery_refusal_proof']
   def late_proof():
    assert late_captured.is_set() and late_release.is_set() and late_state.get('original_response_delivered')
    # The real protected A/200 response was released after B became current.
    # The public client has a 15-second request timeout, so keep this delivery
    # within that bound rather than calling a disconnected response 'late'.
    assert late_state['release_elapsed_seconds']<14
    base=proof();assert base['formal_version']==2 and base['model_calls']==base['registered_operations']==1 and base['forbidden_writes']==0
    with edit_db.connect(scope_for(ISSUER,subject)) as conn:assert conn.execute('SELECT count(*) FROM cj_trip_scoped_action').fetchone()[0]==0
    r['late_proof']=dict(late_state,account_switched_before_release=True,formal_version=2,actions=0,model_calls=1);save();return r['late_proof']
   def invalidate_candidate():
    assert CASE in ('testScopedCandidateConflict','testScopedCandidateWithdrawal','testScopedCandidateStaleAcceptance','testScopedCandidateDiscoveryUnavailable') and len(actual_message_receipts)==1
    original=actual_message_receipts[0]
    if CASE in ('testScopedCandidateConflict','testScopedCandidateStaleAcceptance'):
     with TestClient(scoped_app) as client:
      candidate=expect(client.get('/v1/trip-scoped-discovery',params=dict(message_id=original['message_id'],run_id=original['run_id']),headers=headers),'concurrent-original-discovery')['discovery']['proposal']
      assert candidate is not None
      command=dict(version='TRIP-scoped-action.1',action_id='synthetic-concurrent-accept',kind='accept',proposal_id=candidate['proposal_id'],candidate_hash=candidate['candidate_hash'])
      receipt=expect(client.post('/v1/trip-scoped-actions',content=packed(command),headers=binary),'concurrent-explicit-accept')['receipt']
      assert receipt['committed_version']==3
    else:
     with TestClient(typed_app) as client:
      current=expect(client.get('/v2/memory-items',params=dict(item_id='synthetic-memory-long'),headers=headers),'original-memory-detail')['item']
      command=dict(version='MEMORY-STOP-USE@2',action_id='synthetic-withdraw-before-accept',operation='withdraw',item_id='synthetic-memory-long',expected_version=current['version'],source_id=current['command']['source_id'],expected_source_version=current['command']['source_version'])
      receipt=expect(client.post('/v2/memory-withdrawal-actions',content=packed(command),headers=binary),'actual-memory-withdrawal')['receipt']
      assert receipt['status']=='withdrawn'
    r['candidate_invalidation']=dict(case=CASE,receipt=receipt);save();return dict(status='actual source changed')
   def decision_proof():
    owner=scope_for(ISSUER,subject)
    with edit_db.connect(owner) as conn:
     trips=conn.execute('SELECT trip_id,version,content FROM cj_trip_record').fetchall()
     actions=conn.execute('SELECT action_id,original_input FROM cj_trip_scoped_action').fetchall()
     operations=conn.execute('SELECT count(*) FROM cj_run_metered_operation o JOIN cj_message_receipt m ON (m.scope,m.run_id)=(o.scope,o.run_id) WHERE m.conversation_id=%s',(cid,)).fetchone()[0]
    assert len(trips)==operations==fake.calls==1
    negative=CASE in ('testScopedCandidateConflict','testScopedCandidateWithdrawal','testScopedCandidateStaleAcceptance')
    kind='reject' if CASE in ('testScopedCandidateReject','testScopedCandidateConflict') else 'accept'
    version=3 if CASE in ('testScopedCandidateConflict','testScopedCandidateStaleAcceptance') else (2 if kind=='reject' or CASE=='testScopedCandidateWithdrawal' else 3)
    assert trips[0][0]==tid and trips[0][1]==version
    doc=json.loads(bytes(trips[0][2]));before=formal['content']
    assert doc['title']==before['title'] and doc['sources']==before['sources']
    for old,new in zip(before['items'],doc['items']):
     if old['id']!='item-2' or version==2:assert old==new
    if version==3:assert doc['items'][1]['text']=='SYNTHETIC lighter choice / 本次轻松一点'
    requests=[x for x in audit if x['path']=='/v1/trip-scoped-discovery']
    writes=[x for x in audit if x['path']=='/v1/trip-scoped-actions' and x['method']=='POST']
    queries=[x for x in audit if x['path']=='/v1/trip-scoped-action-receipts']
    assert requests and len(writes)==1
    app_id=writes[0]['original_action_id']
    assert all(q['original_query']==dict(action_id=[app_id]) for q in queries)
    if negative:
     assert not any(action[0]==app_id for action in actions)
     assert writes[0]['status']==(409 if CASE=='testScopedCandidateConflict' else 503)
     assert len(actions)==(0 if CASE=='testScopedCandidateWithdrawal' else 1)
    else:
     assert len(actions)==1 and actions[0][0]==app_id and writes[0]['input_sha256']==hashlib.sha256(bytes(actions[0][1])).hexdigest()
    if CASE=='testScopedCandidateACKLoss':assert writes[0].get('committed_response_suppressed') and writes[0]['status']==200 and writes[0]['delivered_status']==503
    value=dict(formal_version=trips[0][1],formal_count=len(trips),actions=len(actions),app_committed_actions=0 if negative else 1,model_calls=fake.calls,registered_operations=operations,kind=kind,original_action_id=app_id,original_action_sha256=writes[0]['input_sha256'],receipt_queries=len(queries))
    r['decision_proof']=value;save();return value
   class Control(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
     try:
      path=urlparse(self.path);assert parse_qs(path.query).get('case')==[CASE]
      if path.path=='/prepare':value=dict(case_id=CASE,endpoint=endpoint,conversation=cid,namespace=selected_namespace['id'],accounts=native_tokens,subjects=dict(A=subject,**({'B':other_subject} if CASE=='testScopedCandidateLateAccount' else {})),formal_trips=[spec])
      elif path.path=='/wait-discovery':
       assert CASE=='testScopedCandidateLateAccount' and late_captured.wait(20);value=dict(status='original protected 200 held')
      elif path.path=='/release-discovery':
       assert CASE=='testScopedCandidateLateAccount' and late_captured.is_set();late_release.set();value=dict(status='release requested')
      elif path.path=='/discovery-refusal-proof':value=discovery_refusal_proof()
      elif path.path=='/late-proof':value=late_proof()
      elif path.path=='/invalidate-candidate':value=invalidate_candidate()
      elif path.path=='/decision-proof':value=decision_proof()
      elif path.path=='/wait-completed':
       deadline=time.monotonic()+90
       while not finished:
        if worker_errors or time.monotonic()>deadline:raise TimeoutError('formal worker completion')
        time.sleep(.05)
       assert len(finished)==1 and finished[0]['status']=='completed'
       if CASE=='testScopedUndeterminedDayWithoutModel':assert finished[0]['proposal_id'] is None and fake.calls==0
       else:assert finished[0]['proposal_id'] and fake.calls==1
       value=proof()
      else:raise ValueError('unknown control')
      raw=json.dumps(value).encode();self.send_response(200);self.end_headers();self.wfile.write(raw)
     except Exception as error:
      r.setdefault('control_errors',[]).append(dict(type=type(error).__name__));save();self.send_response(500);self.end_headers();self.wfile.write(type(error).__name__.encode())
   control=ThreadingHTTPServer(('127.0.0.1',0),Control);threading.Thread(target=control.serve_forever,daemon=True).start()
   original_size=None
   try:
    module_spec=importlib.util.spec_from_file_location('scoped_builder',ROOT/'scripts/check_ios_trip_confirm.py');module=importlib.util.module_from_spec(module_spec);module_spec.loader.exec_module(module)
    builder=object.__new__(module.XCTestDriver);builder.directory=OUT/'project';builder.directory.mkdir();builder.write_project(0)
    (builder.directory/'G2CControl.swift').write_text((HERE/'DevelopmentScopedMessageUITests.swift').read_text().replace('__FIXTURE_URL__',f'http://127.0.0.1:{control.server_port}'))
    project=builder.directory/'G2CAcceptance.xcodeproj';pbx=project/'project.pbxproj';bundle='space.go2china.scoped.acceptance'
    text=pbx.read_text().replace('space.go2china.foundation.local',bundle).replace('space.go2china.foundation.control',bundle+'.control')
    entitlements=builder.directory/'Scoped.entitlements';entitlements.write_bytes(plistlib.dumps({'application-identifier':bundle,'keychain-access-groups':[bundle]}));pbx.write_text(text.replace(json.dumps(str(ROOT/'ios/App/Development.entitlements')),json.dumps(str(entitlements))))
    original_size=subprocess.check_output(['xcrun','simctl','ui',ARGS.simulator,'content_size'],text=True).strip()
    desired='accessibility-extra-extra-extra-large' if CASE.endswith('Largest') else 'large'
    subprocess.run(['xcrun','simctl','ui',ARGS.simulator,'content_size',desired],check=True,capture_output=True);r['simulator_content_size']=subprocess.check_output(['xcrun','simctl','ui',ARGS.simulator,'content_size'],text=True).strip();assert r['simulator_content_size']==desired;save()
    result=OUT/(CASE+'.xcresult');command=['xcodebuild','-project',str(project),'-scheme','G2CControl','-configuration','Debug','-destination','platform=iOS Simulator,id='+ARGS.simulator,'-derivedDataPath',str(BUILD),'-resultBundlePath',str(result),'-scmProvider','system','-skipPackageUpdates','-onlyUsePackageVersionsFromResolvedFile','-parallel-testing-enabled','NO','-collect-test-diagnostics','never','ARCHS=arm64','ONLY_ACTIVE_ARCH=YES','CODE_SIGNING_ALLOWED=YES','CODE_SIGN_IDENTITY=-','-only-testing:G2CControl/DevelopmentScopedMessageUITests/'+CASE,'test']
    print('SCOPED '+CASE,flush=True);run=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=1800)
    log=run.stdout+run.stderr
    for temporary_token in native_tokens.values():log=log.replace(temporary_token,'<redacted-local-token>')
    assert all(temporary_token not in log for temporary_token in native_tokens.values())
    r['redacted_log_accounts']=sorted(native_tokens);r['token_scan_accounts']=sorted(native_tokens)
    (OUT/(CASE+'.log')).write_text(log);r['cases'][CASE]='FAIL' if run.returncode else 'VERIFYING';save();run.check_returncode()
    summary=json.loads(subprocess.check_output(['xcrun','xcresulttool','get','test-results','summary','--path',str(result)]));(OUT/'test-summary.json').write_text(json.dumps(summary,indent=2));assert summary['passedTests']==1 and summary['failedTests']==summary['skippedTests']==0
    if CASE=='testScopedCandidateLateAccount':late_proof()
    if CASE=='testScopedCandidateDiscoveryUnavailable':discovery_refusal_proof()
    verified=r['proof'] if CASE=='testScopedCandidateDiscoveryUnavailable' or CASE in ('testScopedCandidateAccept','testScopedCandidateReject','testScopedCandidateACKLoss','testScopedCandidateConflict','testScopedCandidateWithdrawal','testScopedCandidateStaleAcceptance') else proof()
    if CASE in ('testScopedCandidateAccept','testScopedCandidateReject','testScopedCandidateACKLoss','testScopedCandidateConflict','testScopedCandidateWithdrawal','testScopedCandidateStaleAcceptance'):assert decision_proof()['receipt_queries']>=1
    assert verified['messages']==verified['posts']==1 and verified['forbidden_writes']==0 and not worker_errors
    if CASE=='testScopedUndeterminedDayWithoutModel':assert verified['model_calls']==verified['registered_operations']==verified['pending_proposals']==0 and verified['draft_outcome']=='validation_failed'
    else:assert verified['model_calls']==verified['registered_operations']==verified['pending_proposals']==1 and verified['draft_outcome']=='published'
    container=Path(subprocess.check_output(['xcrun','simctl','get_app_container',ARGS.simulator,bundle,'data'],text=True).strip())
    for file in container.rglob('*'):
     if file.is_file() and not file.is_symlink():
      data=file.read_bytes();assert all(temporary_token.encode() not in data for temporary_token in native_tokens.values()) and b'-----BEGIN PRIVATE KEY-----' not in data
    assert r['head']==subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'head changed during acceptance'
    assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest for name,digest in r['source_hashes'].items()),'source changed during acceptance'
    r['token_key_scan']='PASS';r['cases'][CASE]='PASS';r['status']='PASS';save()
   finally:
    r['observed_requests']=list(audit);r['worker_errors']=list(worker_errors);save()
    if original_size is not None:subprocess.run(['xcrun','simctl','ui',ARGS.simulator,'content_size',original_size],check=True,capture_output=True)
    late_release.set();stop.set();worker_thread.join(10);server.should_exit=True;api_thread.join(10);sock.close();control.shutdown();control.server_close()
  r['private_pg_stopped']=True
except BaseException as error:
 r['status']='FAIL';r['error']=type(error).__name__;raise
finally:save()
