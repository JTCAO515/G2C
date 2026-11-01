"""Actual App Trip/manual/planning diagnostics against an explicitly pinned local backend.

An unmerged backend pin is candidate evidence, never main or Issue acceptance.
Source creation uses its unmodified run_once/draft_profile, original C writer,
registered Meter, signed APIs and private runtime-role PG. No Trip is seeded.
"""
import argparse,base64,hashlib,importlib.util,json,os,plistlib,socket,subprocess,sys,tempfile,threading,time,uuid
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlparse,parse_qs
APP=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--backend-root',type=Path,required=True);p.add_argument('--backend-head',required=True)
p.add_argument('--run-context',type=Path,required=True);p.add_argument('--simulator',required=True)
p.add_argument('--output',type=Path,required=True);p.add_argument('--build-dir',type=Path,required=True)
p.add_argument('--case',choices=['testNeedsManualTitleSave','testNeedsManualFixedRoundTrip','testNeedsManualTimeTextSave','testNeedsManualSaveACKLoss','testNeedsManualSaveConflict','testNeedsManualLateAccount','testNeedsManualPrepareCancellation','testNeedsManualCanonicalFixedRefusal','testNeedsManualInvalidWindow','testNeedsPlanningPrefix','testNeedsPlanningAccept','testNeedsPlanningReject','testNeedsPlanningACKLoss','testNeedsPlanningDiscoveryUnavailable','testNeedsPlanningStaleAccept','testNeedsPlanningConflict','testNeedsPlanningLateAccount','testNeedsPlanningInterruptedAccept','testNeedsPlanningManualComposition','testNeedsPlanningCurrentFixedAccept','testNeedsPlanningCurrentUnlockedReject','testNeedsPlanningOriginalsLargest','testNeedsPlanningCurrentFixedACKLoss'],required=True)
a=p.parse_args();BACKEND=a.backend_root.resolve();OUT=a.output.resolve();BUILD=a.build_dir.resolve();CASE=a.case;PLANNING_PREFIX=CASE.startswith('testNeedsPlanning')
HISTORY_LARGEST=CASE=='testNeedsPlanningOriginalsLargest'
CURRENT_REPLAN=CASE in ('testNeedsPlanningCurrentFixedAccept','testNeedsPlanningCurrentUnlockedReject','testNeedsPlanningCurrentFixedACKLoss')
PLANNING_DECISION=CURRENT_REPLAN or CASE in ('testNeedsPlanningAccept','testNeedsPlanningReject','testNeedsPlanningACKLoss','testNeedsPlanningStaleAccept','testNeedsPlanningConflict','testNeedsPlanningInterruptedAccept','testNeedsPlanningManualComposition')
PLANNING_NO_DECISION=CASE in ('testNeedsPlanningDiscoveryUnavailable','testNeedsPlanningLateAccount')
if OUT.is_relative_to(APP) or BUILD.is_relative_to(APP):raise ValueError('external evidence required')
head=lambda root:subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
assert head(BACKEND)==a.backend_head and not subprocess.check_output(['git','status','--porcelain'],cwd=BACKEND)
assert not subprocess.check_output(['git','status','--porcelain'],cwd=APP),'commit App candidate first'
os.umask(0o077);OUT.mkdir(parents=True,mode=0o700)
if (OUT/'report.json').exists():raise ValueError('preserve prior evidence')
for key in tuple(os.environ):
 if key.startswith(('PG','LIBPQ','CJ_LOCAL_','G2C_DEV_')):os.environ.pop(key)
os.environ['CJ_ENV']='local';sys.path.insert(0,str(BACKEND/'scripts'))
import dev_auth,migrate,psycopg,uvicorn
from pg_suites import cluster
from fastapi.testclient import TestClient
from cj_api.local_app import create_local_app,LocalDatabase,ISSUER,scope_for,load_confirmation_signer,load_history_configuration
from cj_api.local_run_context import load_run_context
from cj_api.local_plan_model import NeedsPlanFakeProvider
from cj_trip.local_needs_app import create_local_needs_app
from cj_trip.local_structured_read import create_local_structured_read_app
from cj_trip.domain import packed
from run_worker import run_once
import run_worker,cj_api.local_app,cj_trip.local_needs_app,cj_draft.needs_local
modules=[run_worker,cj_api.local_app,cj_trip.local_needs_app,cj_draft.needs_local]
assert all(Path(m.__file__).is_relative_to(BACKEND) for m in modules),'wrong backend import root'
source_files=[*list((APP/'ios/App').glob('*.swift')),HERE/'DevelopmentScopedMessageUITests.swift',Path(__file__)]
for module in ('CJShell','CJTripClient','CJMessageClient','CJNeedsClient','CJAuth','CJManualPreviewClient','CJRunClient'):
 source_files+=list((APP/'ios/Modules'/module/'Sources').rglob('*.swift'))
def fingerprint(root,paths):return {str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
backend_files=[BACKEND/name for name in subprocess.check_output(['git','ls-files','backend','scripts','contracts','pyproject.toml','uv.lock'],cwd=BACKEND,text=True).splitlines()]
r=dict(status='RUNNING',layer='actual Simulator/signed API/private PG/pinned backend candidate',app_head=head(APP),backend_head=head(BACKEND),backend_root_verified=True,source_hashes=fingerprint(APP,source_files),backend_hashes=fingerprint(BACKEND,backend_files),responses=[],unrun=['main backend delivery if pin unmerged','real services/models/fees/cloud/device'])
if PLANNING_PREFIX:
 r['unrun']+=['source-input.2 main delivery until B378 merges' if CURRENT_REPLAN else 'source-input.2 formal replanning']
 if PLANNING_DECISION:r['verified_scope']='original NEEDS planning discovery/decision/recovery'
 elif PLANNING_NO_DECISION:
  r['verified_scope']='planning discovery refusal/account lifetime only'
  r['unrun']+=['decision and original action recovery not exercised by this zero-action case']
 else:
  r['verified_scope']='explicit MESSAGE-send.2 / original RUN published prefix only'
  r['unrun']+=['planning discovery/decision not exercised by prefix-only case']
if HISTORY_LARGEST:
 r['verified_scope']='largest Chinese planning originals navigation only; zero App messages/model/Trip writes'
 r['unrun']+=['discovery/decision/recovery not exercised by navigation-only case']
def save():(OUT/'report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2))
def check(resp,phase):
 r['responses'].append(dict(phase=phase,status=resp.status_code,error=resp.json().get('error')));save();assert resp.status_code==200,(phase,resp.status_code,resp.text);return resp.json()
def known(v):return dict(state='known',value=v)
def edge(clock):return dict(date=known('2026-11-02'),time=known(clock),timezone=known('Asia/Shanghai'),place=dict(state='unknown'))
def item(key,start,end,locked):return dict(item_id=key,kind='appointment',description='SYNTHETIC declared '+key,applies_to=['self'],locked=known(locked),booking_status=known('booked'),start=edge(start),end=edge(end))
save()
try:
 with tempfile.TemporaryDirectory(prefix='cj286-manual-',dir='/tmp') as t:
  root=Path(t)
  with cluster('manualapp',port=55929,role='cj286_manual_initializer',root=root/'pg') as cfg:
   with psycopg.connect(**cfg,autocommit=True) as conn:
    chain=migrate.load();migrate.up(conn,chain,chain[-1]['version'])
   connection=root/'connection.json';connection.write_text(json.dumps(cfg));auth=root/'auth';subject='manual-native-'+uuid.uuid4().hex;subjects={'A':subject}
   if CASE in ('testNeedsManualLateAccount','testNeedsPlanningLateAccount'):subjects['B']='manual-native-b-'+uuid.uuid4().hex
   dev_auth.init(auth,list(subjects.values()))
   context=load_run_context(a.run_context.resolve())
   for owner in subjects.values():
    subprocess.run([sys.executable,'-B',str(BACKEND/'scripts/local_run_context.py'),'--conninfo-json',str(connection),'--auth-dir',str(auth),'--run-context',str(a.run_context.resolve()),'--subject',owner,'init-budget'],cwd=BACKEND,check=True,capture_output=True)
    dev_auth.activate_travel(connection,owner,context,'MESSAGE-TRAVEL-CONSUMER@1')
   signer=load_confirmation_signer(auth);tokens={label:dev_auth.token(auth,owner,120) for label,owner in subjects.items()}
   token=tokens['A'];headers={'Authorization':'Bearer '+token};binary={**headers,'Content-Type':'application/octet-stream'}
   api=create_local_app(conninfo_path=connection,auth_dir=auth,history_configuration=load_history_configuration(auth),run_context=context,travel_context=True,needs_profile='manual-v1',confirmation_signer=signer)
   with TestClient(api) as client:
    check(client.post('/v1/needs-actions',content=packed(dict(action_id='source',needs_id='visit',expected_version=0,source=dict(kind='manual',text='SYNTHETIC explicit source'),changes=dict(fixed_items=[item('a','09:00','10:00',True),item('b','11:00','12:00',False)]))),headers=binary),'needs')
    namespace=check(client.post('/v1/travel-context-actions',content=packed(dict(version='TRAVEL-context-action.1',action_id='namespace',operation='create',travel_context=None)),headers=binary),'namespace')['receipt']['travel_context']
    chat=check(client.put('/v1/conversations',params=dict(conversation_id='source'),headers=headers),'chat')
    if not PLANNING_PREFIX:original=check(client.post('/v2/messages',content=packed(dict(version='MESSAGE-send.2',conversation_id='source',message_id='source-message',text='SYNTHETIC use declared constraints',trip_id=None,creation_intent='consider_trip',expected_generation=chat['generation'],expected_sequence=0,travel_context=dict(id=namespace['id'],expected_version=1),needs_reference=dict(id='visit',expected_version=1))),headers=binary),'message')
   database=LocalDatabase(connection,run_context=context,travel_context=True,needs_context=True);model=NeedsPlanFakeProvider()
   needs_app=create_local_needs_app(conninfo_path=connection,auth_dir=auth,run_context=context,confirmation_signer=signer)
   structured=create_local_structured_read_app(conninfo_path=connection,auth_dir=auth,run_context=context)
   outcomes=[];message_ready=threading.Event();worker_done=threading.Event();prefix_stop=threading.Event();worker_errors=[];message_receipt={}
   r['source_provider_calls']=0
   if not PLANNING_PREFIX:
    outcomes=run_once(database,model,auth,draft_profile='needs-structured.1');assert len(outcomes)==1 and outcomes[0].status=='completed' and outcomes[0].proposal_id
    r['source_provider_calls']=model.calls
    with TestClient(needs_app) as client:
     proposal=check(client.get('/v2/trip-needs-proposals',params=dict(proposal_id=outcomes[0].proposal_id),headers=headers),'source-proposal')['proposal']
     receipt=check(client.post('/v1/trip-needs-actions',content=packed(dict(version='TRIP-needs-action.1',action_id='source-accept',kind='accept',proposal_id=proposal['proposal_id'],candidate_hash=proposal['candidate_hash'])),headers=binary),'source-adopt')['receipt']
    tid=receipt['trip_id']
    with TestClient(structured) as client:formal=check(client.get('/v5/trip-structured',params=dict(trip_id=tid),headers=headers),'formal')['trip']
    assert formal['content']['content_version']=='structured.2' and formal['version']==1
    r['source_formal']=formal;r['source_message']=original['receipt'];save()
   current_ready=threading.Event();current_done=threading.Event();current_errors=[];current_outcomes=[];message_receipts=[];current_source={}
   if CURRENT_REPLAN:
    from cj_api.local_plan_model import CurrentTripPlanFakeProvider
    current_model=CurrentTripPlanFakeProvider()
   audit=[];planning_discoveries=[];latest_preparation={};late_captured=threading.Event();late_release=threading.Event();late_state={}
   async def observed(scope,receive,send):
    if scope.get('type')!='http':return await api(scope,receive,send)
    path=scope['path'];authorization=dict(scope['headers']).get(b'authorization',b'').decode('ascii');label=next((label for label,value in tokens.items() if authorization=='Bearer '+value),None);entry=dict(method=scope['method'],path=path,account=label);audit.append(entry);parts=[];actual_reply=[];reply_parts=[]
    drop_ack=scope['method']=='POST' and ((CASE=='testNeedsManualSaveACKLoss' and path=='/v1/trip-needs-saves') or (CASE=='testNeedsPlanningACKLoss' and path=='/v1/trip-needs-actions'))
    if CASE=='testNeedsPlanningCurrentFixedACKLoss' and scope['method']=='POST' and path=='/v1/trip-needs-actions' and len(message_receipts)==2:drop_ack=True
    hold_prepare=CASE in ('testNeedsManualLateAccount','testNeedsManualPrepareCancellation') and path=='/v1/trip-needs-edits' and scope['method']=='POST'
    hold_planning=(CASE=='testNeedsPlanningLateAccount' and path=='/v1/trip-needs-discovery') or (CASE=='testNeedsPlanningInterruptedAccept' and path=='/v1/trip-needs-actions' and scope['method']=='POST')
    if scope.get('query_string'):entry['query']=parse_qs(scope['query_string'].decode('ascii'))
    async def received():
     value=await receive()
     if value['type']=='http.request':parts.append(value.get('body',b''))
     return value
    async def sent(value):
     if value['type']=='http.response.start':entry['status']=value['status']
     if value['type']=='http.response.body':reply_parts.append(value.get('body',b''))
     if drop_ack or hold_prepare or hold_planning:actual_reply.append(value)
     else:await send(value)
    target=structured if path in ('/v1/trip-structured-list','/v5/trip-structured') else needs_app if path.startswith('/v1/trip-needs-') else api
    await target(scope,received,sent)
    if path=='/v1/trip-needs-discovery' and entry['status']==200:planning_discoveries.append(json.loads(b''.join(reply_parts))['discovery'])
    if path=='/v1/trip-needs-edits' and scope['method']=='POST' and entry['status']==200:latest_preparation['value']=json.loads(b''.join(reply_parts))['preparation']
    if path=='/v1/trip-needs-edits' and scope['method']=='GET' and entry['status']==200:entry['preparation_present']=json.loads(b''.join(reply_parts))['preparation'] is not None
    if path=='/v1/trip-needs-action-receipts' and entry['status']==200:entry['receipt_present']=json.loads(b''.join(reply_parts))['receipt'] is not None
    if hold_prepare or hold_planning:
     assert entry['status']==200
     started=time.monotonic();late_state['original_protected_status']=200;late_state['reply_sha256']=hashlib.sha256(b''.join(reply_parts)).hexdigest();late_captured.set()
     import asyncio
     assert await asyncio.to_thread(late_release.wait,40),'held original preparation never released'
     late_state['release_elapsed_seconds']=time.monotonic()-started
     for value in actual_reply:await send(value)
     late_state['original_response_sent']=True
    if drop_ack:
     # Explicit proxy response loss after the original C transaction returned 200.
     assert entry['status']==200
     original_body=b''.join(part.get('body',b'') for part in actual_reply if part['type']=='http.response.body')
     entry.update(actual_backend_reply_sha256=hashlib.sha256(original_body).hexdigest(),delivered_status=503,committed_response_suppressed=True)
     trace=str(uuid.uuid4());failure=packed(dict(request_id=trace,error=dict(code='TRIP_OUTCOME_UNKNOWN',category='dependency',message_en='Synthetic committed response loss',message_zh='合成已提交回包丢失',outcome='unknown',recovery='reconcile_original')))
     await send(dict(type='http.response.start',status=503,headers=[(b'content-type',b'application/json'),(b'cache-control',b'no-store'),(b'x-request-id',trace.encode())]))
     await send(dict(type='http.response.body',body=failure))
    if scope['method']=='POST':
     raw=b''.join(parts);entry['input_sha256']=hashlib.sha256(raw).hexdigest();value=json.loads(raw);entry['original_id']=value.get('action_id') or value.get('edit',{}).get('request_id')
     if CASE=='testNeedsManualInvalidWindow' and path=='/v1/trip-needs-edits':entry['original_edit']=value
     if path=='/v1/trip-needs-actions':entry['decision']=value['kind'];entry['proposal_id']=value['proposal_id'];entry['candidate_hash']=value['candidate_hash']
     if PLANNING_PREFIX and path=='/v2/messages' and entry['status']==200:
      entry['message_id']=value['message_id'];receipt=json.loads(b''.join(reply_parts))['receipt'];message_receipts.append(receipt)
      if len(message_receipts)==1:message_receipt['value']=receipt;message_ready.set()
      else:
       assert CURRENT_REPLAN and len(message_receipts)==2;current_ready.set()
   def prefix_worker():
    try:
     if not message_ready.wait(600) or prefix_stop.is_set():return
     outcomes.extend(run_once(database,model,auth,draft_profile='needs-structured.1'))
     r['prefix_worker_outcomes']=[dict(status=x.status,proposal_id=x.proposal_id) for x in outcomes]
     r['proposal_ids_are_backend_oracles_only']=True;r['source_provider_calls']=model.calls;save()
    except Exception as error:worker_errors.append(type(error).__name__)
    finally:worker_done.set()
   def current_worker():
    try:
     if not current_ready.wait(600) or prefix_stop.is_set():return
     current_outcomes.extend(run_once(database,current_model,auth,draft_profile='needs-current-trip.1'))
     r['current_worker_outcomes']=[dict(status=x.status,proposal_id=x.proposal_id) for x in current_outcomes];save()
    except Exception as error:current_errors.append(type(error).__name__)
    finally:current_done.set()
   if PLANNING_PREFIX:
    worker_thread=threading.Thread(target=prefix_worker,daemon=True);worker_thread.start()
   if CURRENT_REPLAN:
    current_thread=threading.Thread(target=current_worker,daemon=True);current_thread.start()
   server=uvicorn.Server(uvicorn.Config(observed,host='127.0.0.1',port=0,log_level='error',access_log=False))
   sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen();endpoint='http://127.0.0.1:'+str(sock.getsockname()[1]);thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
   def current_formal():
    with database.connect(scope_for(ISSUER,subject)) as conn:
     role=conn.execute('SELECT current_user').fetchone()[0];trips=conn.execute('SELECT trip_id,version,content FROM cj_trip_record').fetchall()
    assert role=='cj_m1_runtime' and len(trips)==1 and trips[0][0]==tid
    return role,trips[0][1],json.loads(bytes(trips[0][2]))
   def prefix_not_sent():
    assert PLANNING_PREFIX and not message_ready.is_set() and model.calls==0
    assert not any(x['method']=='POST' for x in audit)
    with database.connect(scope_for(ISSUER,subject)) as conn:
     role=conn.execute('SELECT current_user').fetchone()[0]
     count=conn.execute('SELECT count(*) FROM cj_message_receipt WHERE conversation_id=%s',('source',)).fetchone()[0]
    assert role=='cj_m1_runtime' and count==0
    r['prefix_no_send_checks']=r.get('prefix_no_send_checks',0)+1;save();return dict(messages=0,model_calls=0)
   def proof(stage=None):
    if PLANNING_PREFIX:
     assert worker_done.wait(20) and not worker_errors and len(outcomes)==1 and outcomes[0].status=='completed' and outcomes[0].proposal_id
     with database.connect(scope_for(ISSUER,subject)) as conn:
      role=conn.execute('SELECT current_user').fetchone()[0]
      rows=conn.execute('SELECT message_id,raw_input,run_id FROM cj_message_receipt WHERE conversation_id=%s',('source',)).fetchall()
      formal_count=conn.execute('SELECT count(*) FROM cj_trip_record').fetchone()[0]
      pending=conn.execute('SELECT count(*) FROM cj_trip_proposal').fetchone()[0]
      operations=conn.execute('SELECT count(*) FROM cj_run_metered_operation o JOIN cj_message_receipt m ON (m.scope,m.run_id)=(o.scope,o.run_id) WHERE m.conversation_id=%s',('source',)).fetchone()[0]
     r['prefix_measurements']=dict(runtime_role=role,messages=len(rows),formal_count=formal_count,pending_proposals=pending,registered_operations=operations,model_calls=model.calls);save()
     assert role=='cj_m1_runtime' and len(rows)==1 and formal_count==0 and pending==1 and operations==2 and model.calls==2
     command=json.loads(bytes(rows[0][1]));assert command['version']=='MESSAGE-send.2' and command['trip_id'] is None and command['creation_intent']=='consider_trip'
     assert command['needs_reference']==dict(id='visit',expected_version=1) and command['travel_context']==dict(id=namespace['id'],expected_version=1)
     assert message_receipt['value']['message_id']==rows[0][0] and message_receipt['value']['run_id']==rows[0][2]
     posts=[x for x in audit if x['method']=='POST'];assert len(posts)==1 and posts[0]['path']=='/v2/messages' and posts[0]['input_sha256']==hashlib.sha256(bytes(rows[0][1])).hexdigest()
     with TestClient(api) as client:draft=check(client.get('/v3/run-draft-status',params=dict(message_id=rows[0][0]),headers=headers),'prefix-original-draft')
     assert draft['message_id']==rows[0][0] and draft['run_id']==rows[0][2] and draft['run_status']=='completed' and draft['draft_outcome']=='published'
     with TestClient(needs_app) as client:pending_proposal=check(client.get('/v2/trip-needs-proposals',params=dict(proposal_id=outcomes[0].proposal_id),headers=headers),'prefix-backend-oracle')['proposal']
     assert pending_proposal['status']=='pending' and pending_proposal['expected_version']==0 and pending_proposal['content']['content_version']=='structured.2'
     assert r['prefix_no_send_checks']>=2
     value=dict(runtime_role=role,messages=1,posts=1,model_calls=2,registered_operations=2,pending_proposals=1,formal_count=0,actions=0,namespace=namespace['id'],needs_version=1,message_id=rows[0][0],run_id=rows[0][2],original_input_sha256=hashlib.sha256(bytes(rows[0][1])).hexdigest(),no_send_checks=r['prefix_no_send_checks'])
     r['proof']=value;save();return value

    if CASE=='testNeedsManualLateAccount':
     assert late_captured.is_set() and late_release.is_set() and late_state.get('original_response_sent')
     prepares=[x for x in audit if x['path']=='/v1/trip-needs-edits' and x['method']=='POST']
     assert len(prepares)==1 and prepares[0]['account']=='A' and prepares[0]['status']==200
     assert not any(x['method']=='POST' and x['path']!='/v1/trip-needs-edits' for x in audit)
     assert any(x['account']=='B' and x['path']=='/v1/message-receipts' and x.get('status')==200 for x in audit)
     assert any(x['account']=='B' and x['path']=='/v1/trip-structured-list' and x.get('status')==200 for x in audit)
     with TestClient(needs_app) as client:foreign=check(client.get('/v1/trip-needs-edits',params=dict(request_id=prepares[0]['original_id']),headers={'Authorization':'Bearer '+tokens['B']}),'other-owner-original')['preparation']
     assert foreign is None
     role,version,current=current_formal();assert version==1 and current==formal['content']
     assert model.calls==r['source_provider_calls']
     value=dict(late_state,runtime_role=role,verified_B_before_release=True,formal_version=1,formal_unchanged=True,prepare_posts=1,saves=0,edit_model_calls=0,foreign_original=None)
     r['proof']=value;save();return value
    if CASE=='testNeedsManualPrepareCancellation':
     assert late_captured.is_set() and late_release.is_set() and late_state.get('original_response_sent')
     prepares=[x for x in audit if x['path']=='/v1/trip-needs-edits' and x['method']=='POST'];queries=[x for x in audit if x['path']=='/v1/trip-needs-edits' and x['method']=='GET']
     assert len(prepares)==1 and prepares[0]['account']=='A' and prepares[0]['status']==200
     assert len(queries)>=1 and all(q['query']==dict(request_id=[prepares[0]['original_id']]) and q['status']==200 and q['preparation_present'] for q in queries)
     assert not any(x['method']=='POST' and x['path']!='/v1/trip-needs-edits' for x in audit) and model.calls==r['source_provider_calls']
     role,version,current=current_formal();assert version==1 and current==formal['content']
     value=dict(late_state,runtime_role=role,formal_version=1,formal_unchanged=True,prepare_posts=1,original_queries=len(queries),same_original_id=True,saves=0,edit_model_calls=0)
     r['proof']=value;save();return value
    if CASE in ('testNeedsManualCanonicalFixedRefusal','testNeedsManualInvalidWindow'):
     prepares=[x for x in audit if x['path']=='/v1/trip-needs-edits' and x['method']=='POST'];queries=[x for x in audit if x['path']=='/v1/trip-needs-edits' and x['method']=='GET']
     assert len(prepares)==1 and prepares[0]['status']==409
     if CASE=='testNeedsManualInvalidWindow':
      original=prepares[0]['original_edit'];edit=original['edit'];schedule=json.loads(json.dumps(formal['content']['items'][1]['schedule']))
      schedule['start']['time']=known('11:15');schedule['end']['time']=known('10:30')
      assert original['version']=='TRIP-needs-edit.1' and original['needs_reference']==dict(id='visit',expected_version=1)
      assert edit['trip_id']==tid and edit['expected_version']==1 and edit['title'] is None and edit['order'] is None
      assert edit['changes']==[dict(item_id='b',field='schedule',value=schedule)]
     assert len(queries)>=1 and all(q['query']==dict(request_id=[prepares[0]['original_id']]) and q['status']==200 and q['preparation_present'] is False for q in queries)
     assert not any(x['method']=='POST' and x['path']!='/v1/trip-needs-edits' for x in audit) and model.calls==r['source_provider_calls']
     role,version,current=current_formal();assert version==1 and current==formal['content']
     with TestClient(api) as client:needs=check(client.get('/v1/needs',params=dict(needs_id='visit'),headers=headers),'canonical-needs')['needs']
     assert needs['version']==1 and needs['fields']['fixed_items'][0]['locked']==known(True)
     value=dict(runtime_role=role,formal_version=1,formal_unchanged=True,prepare_posts=1,prepare_status=409,original_queries=len(queries),same_original_id=True,null_preparation=True,needs_unchanged=True,saves=0,edit_model_calls=0)
     r['proof']=value;save();return value
    fixed_case=CASE=='testNeedsManualFixedRoundTrip'
    expected_version=2 if not fixed_case or stage=='locked' else 3
    expected_count=1 if not fixed_case or stage=='locked' else 2
    role,version,current=current_formal();assert version==expected_version
    if fixed_case:
     assert current['title']==formal['content']['title'] and current['sources']==formal['content']['sources']
     assert current['items'][0]==formal['content']['items'][0]
     original_item=dict(formal['content']['items'][1]);original_item['fixed']=known(stage=='locked')
     assert current['items'][1]==original_item
     with TestClient(api) as client:needs=check(client.get('/v1/needs',params=dict(needs_id='visit'),headers=headers),'current-needs')['needs']
     assert needs['version']==1 and needs['fields']['fixed_items'][1]['locked']==known(False)
    elif CASE=='testNeedsManualTimeTextSave':
     assert current['title']==formal['content']['title'] and current['sources']==formal['content']['sources']
     assert current['items'][0]==formal['content']['items'][0]
     expected=json.loads(json.dumps(formal['content']['items'][1]));expected['text']='SYNTHETIC explicit time and text / 明确修改'
     expected['schedule']['start']['time']=known('11:15');expected['schedule']['end']['time']=known('12:15')
     assert current['items'][1]==expected
    else:
     assert current['title']=='SYNTHETIC manual saved title / 手动保存标题' and current['items']==formal['content']['items'] and current['sources']==formal['content']['sources']
    prepares=[x for x in audit if x['path']=='/v1/trip-needs-edits' and x['method']=='POST'];saves=[x for x in audit if x['path']=='/v1/trip-needs-saves' and x['method']=='POST'];queries=[x for x in audit if x['path']=='/v1/trip-needs-action-receipts']
    assert len(prepares)==len(saves)==expected_count and all(x['status']==200 for x in prepares)
    assert all(x['status']==(409 if CASE=='testNeedsManualSaveConflict' else 200) for x in saves)
    if CASE=='testNeedsManualSaveConflict':assert r['competing_receipt']['committed_version']==2 and all(q['receipt_present'] is False for q in queries)
    if CASE=='testNeedsManualSaveACKLoss':assert saves[0].get('committed_response_suppressed') and saves[0]['delivered_status']==503
    ids={x['original_id'] for x in saves};assert all(q['query'].get('action_id',[None])[0] in ids and q['status']==200 for q in queries)
    assert model.calls==r['source_provider_calls'] and not any(x['method']=='POST' and x['path'] not in ('/v1/trip-needs-edits','/v1/trip-needs-saves') for x in audit)
    value=dict(runtime_role=role,formal_version=expected_version,formal_count=1,prepares=expected_count,saves=expected_count,save_ids=sorted(ids),receipt_queries=len(queries),source_provider_calls=model.calls,edit_model_calls=0,unselected_exact=True,needs_unchanged=True if fixed_case else None,stage=stage)
    r['proof']=value;r.setdefault('proof_history',[]).append(value);save();return value
   def planning_no_decision_proof():
    assert PLANNING_NO_DECISION and worker_done.is_set() and not worker_errors and model.calls==2
    posts=[x for x in audit if x['method']=='POST'];assert len(posts)==1 and posts[0]['path']=='/v2/messages'
    reads=[x for x in audit if x['path']=='/v1/trip-needs-discovery'];original=message_receipt['value']
    assert reads and all(x['query']==dict(message_id=[original['message_id']],run_id=[original['run_id']]) for x in reads)
    with database.connect(scope_for(ISSUER,subject)) as conn:formal=conn.execute('SELECT count(*) FROM cj_trip_record').fetchone()[0]
    assert formal==0
    if CASE=='testNeedsPlanningDiscoveryUnavailable':
     assert len(reads)>=2 and all(x['status']==503 for x in reads) and r['needs_correction']['receipt']['version']==2
    else:
     assert late_captured.is_set() and late_release.is_set() and late_state.get('original_response_sent') and reads[0]['status']==200
     assert any(x['account']=='B' and x['path']=='/v1/message-receipts' and x.get('status')==200 for x in audit)
     with TestClient(needs_app) as client:foreign=client.get('/v1/trip-needs-discovery',params=dict(message_id=original['message_id'],run_id=original['run_id']),headers={'Authorization':'Bearer '+tokens['B']})
     assert foreign.status_code==503 and 'discovery' not in foreign.json()
    value=dict(runtime_role='cj_m1_runtime',messages=1,model_calls=2,registered_operations=2,actions=0,formal_count=0,discovery_reads=len(reads),no_redispatch=True,account_late=CASE=='testNeedsPlanningLateAccount',late=dict(late_state))
    r['no_decision_proof']=value;save();return value
   def planning_decision_proof():
    assert PLANNING_DECISION and worker_done.is_set() and not worker_errors and model.calls==2
    assert planning_discoveries and planning_discoveries[0]['state']=='published'
    found=planning_discoveries[0];candidate=found['proposal']
    assert found['reference']['message_id']==message_receipt['value']['message_id'] and found['reference']['run_id']==message_receipt['value']['run_id']
    assert found['needs_reference']==dict(id='visit',expected_version=1) and found['source_profile']=='TRIP-source-input.1' and found['planning_context'] is None
    acts=[x for x in audit if x['method']=='POST' and x['path']=='/v1/trip-needs-actions'];messages=[x for x in audit if x['method']=='POST' and x['path']=='/v2/messages']
    expected_status=409 if CASE=='testNeedsPlanningConflict' else 503 if CASE=='testNeedsPlanningStaleAccept' else 200
    assert len(acts)==len(messages)==1 and acts[0]['status']==expected_status and acts[0]['proposal_id']==candidate['proposal_id'] and acts[0]['candidate_hash']==candidate['candidate_hash']
    assert all(x['method']!='POST' or x['path'] in ('/v2/messages','/v1/trip-needs-actions') for x in audit)
    kind='reject' if CASE=='testNeedsPlanningReject' else 'accept';assert acts[0]['decision']==kind
    if CASE=='testNeedsPlanningACKLoss':assert acts[0]['committed_response_suppressed'] and acts[0]['delivered_status']==503
    if CASE=='testNeedsPlanningInterruptedAccept':assert late_state.get('original_response_sent') and late_captured.is_set() and late_release.is_set()
    with TestClient(needs_app) as client:receipt=check(client.get('/v1/trip-needs-action-receipts',params=dict(action_id=acts[0]['original_id']),headers=headers),'planning-original-action')['receipt']
    with database.connect(scope_for(ISSUER,subject)) as conn:
     role=conn.execute('SELECT current_user').fetchone()[0];trips=conn.execute('SELECT trip_id,version,content FROM cj_trip_record').fetchall()
    assert role=='cj_m1_runtime'
    refused=CASE in ('testNeedsPlanningConflict','testNeedsPlanningStaleAccept')
    if refused:
     assert receipt is None
     if CASE=='testNeedsPlanningConflict':assert r['competing_planning_receipt']['committed_version']==1 and len(trips)==1 and trips[0][0]==candidate['trip_id'] and trips[0][1]==1
     else:assert trips==[] and r['needs_correction']['receipt']['version']==2
    else:
     assert receipt and receipt['action_id']==acts[0]['original_id'] and receipt['kind']==kind and receipt['trip_id']==candidate['trip_id'] and receipt['candidate_hash']==candidate['candidate_hash']
     if kind=='accept':assert receipt['committed_version']==1 and len(trips)==1 and trips[0][0]==candidate['trip_id'] and trips[0][1]==1 and json.loads(bytes(trips[0][2]))==candidate['content']
     else:assert receipt['committed_version'] is None and trips==[]
    queries=[x for x in audit if x['path']=='/v1/trip-needs-action-receipts'];assert all(q['status']==200 and q['query']==dict(action_id=[acts[0]['original_id']]) and q['receipt_present'] is not refused for q in queries)
    reads=[x for x in audit if x['path']=='/v1/trip-needs-discovery'];assert all(q['query']==dict(message_id=[message_receipt['value']['message_id']],run_id=[message_receipt['value']['run_id']]) for q in reads)
    value=dict(runtime_role=role,messages=1,model_calls=2,registered_operations=2,actions=1,kind=kind,formal_count=len(trips),original_receipt_null=refused,original_action_id=acts[0]['original_id'],original_action_sha256=acts[0]['input_sha256'],receipt_queries=len(queries),discovery_reads=len(reads),trip_id=candidate['trip_id'],actual_status=expected_status,proposal_ids_are_backend_oracles_only=True)
    r['decision_proof']=value;save();return value
   def planning_composition_proof():
    assert (CASE=='testNeedsPlanningManualComposition' or CURRENT_REPLAN) and worker_done.is_set() and not worker_errors and model.calls==2
    candidate=planning_discoveries[0]['proposal']
    messages=[x for x in audit if x['method']=='POST' and x['path']=='/v2/messages'];acts=[x for x in audit if x['method']=='POST' and x['path']=='/v1/trip-needs-actions']
    prepares=[x for x in audit if x['method']=='POST' and x['path']=='/v1/trip-needs-edits'];saves=[x for x in audit if x['method']=='POST' and x['path']=='/v1/trip-needs-saves']
    assert len(messages)==len(acts)==len(prepares)==len(saves)==1 and all(x['status']==200 for x in messages+acts+prepares+saves)
    assert all(x['method']!='POST' or x['path'] in ('/v2/messages','/v1/trip-needs-actions','/v1/trip-needs-edits','/v1/trip-needs-saves') for x in audit)
    with TestClient(needs_app) as client:
     accepted=check(client.get('/v1/trip-needs-action-receipts',params=dict(action_id=acts[0]['original_id']),headers=headers),'composition-planning-receipt')['receipt']
     manual=check(client.get('/v1/trip-needs-action-receipts',params=dict(action_id=saves[0]['original_id']),headers=headers),'composition-manual-receipt')['receipt']
    assert accepted['committed_version']==1 and manual['committed_version']==2 and accepted['trip_id']==manual['trip_id']==candidate['trip_id'] and acts[0]['original_id']!=saves[0]['original_id']
    with database.connect(scope_for(ISSUER,subject)) as conn:
     role=conn.execute('SELECT current_user').fetchone()[0];trips=conn.execute('SELECT trip_id,version,content FROM cj_trip_record').fetchall()
    assert role=='cj_m1_runtime' and len(trips)==1 and trips[0][0]==candidate['trip_id'] and trips[0][1]==2
    content=json.loads(bytes(trips[0][2]));assert content['title']=='SYNTHETIC manual after App adoption / 采用后手改' and content['items']==candidate['content']['items'] and content['sources']==candidate['content']['sources']
    queries=[x for x in audit if x['path']=='/v1/trip-needs-action-receipts' and x['query']==dict(action_id=[acts[0]['original_id']])];assert len(queries)>=1 and all(x['status']==200 and x['receipt_present'] for x in queries)
    value=dict(runtime_role=role,message_posts=1,model_calls=2,registered_operations=2,planning_action_posts=1,manual_prepare_posts=1,manual_save_posts=1,formal_count=1,formal_version=2,historical_planning_receipt_version=1,manual_receipt_version=2,trip_id=candidate['trip_id'],original_planning_id=acts[0]['original_id'],original_planning_sha256=acts[0]['input_sha256'],original_manual_id=saves[0]['original_id'],original_manual_sha256=saves[0]['input_sha256'],planning_receipt_queries=len(queries),unselected_exact=True)
    r['composition_proof']=value;save();return value
   def current_planning_blocked():
    assert CURRENT_REPLAN and not current_ready.is_set()
    assert len([x for x in audit if x['method']=='POST' and x['path']=='/v1/trip-needs-edits'])==1
    assert len([x for x in audit if x['method']=='POST' and x['path']=='/v1/trip-needs-saves'])==1
    assert len(message_receipts)==1 and model.calls==2 and current_model.calls==0
    r['current_write_blocked_before_reconciliation']=True;save();return dict(new_prepare_posts=0,new_save_posts=0)
   def current_planning_source():
    assert CURRENT_REPLAN and not current_source and not current_ready.is_set()
    assert r['current_write_blocked_before_reconciliation']
    first_prepare=next(x for x in audit if x['method']=='POST' and x['path']=='/v1/trip-needs-edits');first_save=next(x for x in audit if x['method']=='POST' and x['path']=='/v1/trip-needs-saves')
    assert any(x['method']=='GET' and x['path']=='/v1/trip-needs-edits' and x['query']==dict(request_id=[first_prepare['original_id']]) and x['status']==200 and x['preparation_present'] for x in audit)
    assert any(x['method']=='GET' and x['path']=='/v1/trip-needs-action-receipts' and x['query']==dict(action_id=[first_save['original_id']]) and x['status']==200 and x['receipt_present'] for x in audit)
    tid=planning_discoveries[0]['proposal']['trip_id']
    with TestClient(structured) as client:source=check(client.get('/v5/trip-structured',params=dict(trip_id=tid),headers=headers),'source2-current-trip')['trip']
    source_version=5 if CASE.endswith('Reject') else 3
    assert source['version']==source_version and source['content']['title']=='SYNTHETIC manual after App adoption / 采用后手改'
    original=planning_discoveries[0]['proposal']['content'];expected=json.loads(json.dumps(original));expected['title']=source['content']['title'];expected['items'][1]['fixed']=known(not CASE.endswith('Reject'))
    if CASE.endswith('Reject'):
     expected['items'][1]['text']='SYNTHETIC current replan edit / 后续规划手改'
     expected['items'][1]['schedule']['start']['time']=known('11:15');expected['items'][1]['schedule']['end']['time']=known('12:15')
    assert source['content']==expected
    assert len([x for x in audit if x['method']=='POST' and x['path']=='/v1/trip-needs-saves'])==source_version-1
    current_source.update(source);r['source2_current_trip']=source;save();return dict(trip_id=tid,version=source_version,content_sha256=source['content_sha256'])
   def current_planning_published():
    assert CURRENT_REPLAN and current_done.wait(30) and not current_errors and len(current_outcomes)==1 and current_outcomes[0].status=='completed'
    assert len(message_receipts)==2 and model.calls==current_model.calls==2
    return dict(completed=True)
   def current_planning_proof():
    current_planning_published();assert len(planning_discoveries)==2
    discovery=planning_discoveries[1];candidate=discovery['proposal'];source=current_source
    assert discovery['source_profile']=='TRIP-source-input.2' and discovery['planning_context']==dict(trip_id=source['trip_id'],version=source['version'],content_sha256=source['content_sha256'])
    assert candidate['trip_id']!=source['trip_id'] and candidate['expected_version']==0 and candidate['content']==source['content']
    original=message_receipts[1];reads=[x for x in audit if x['path']=='/v1/trip-needs-discovery'];assert reads[-1]['query']==dict(message_id=[original['message_id']],run_id=[original['run_id']])
    posts=[x for x in audit if x['method']=='POST'];messages=[x for x in posts if x['path']=='/v2/messages'];acts=[x for x in posts if x['path']=='/v1/trip-needs-actions'];prepares=[x for x in posts if x['path']=='/v1/trip-needs-edits'];saves=[x for x in posts if x['path']=='/v1/trip-needs-saves']
    manual_count=source['version']-1
    assert len(messages)==len(acts)==2 and len(prepares)==len(saves)==manual_count and len(posts)==4+2*manual_count and all(x['status']==200 for x in posts)
    kind='reject' if CASE.endswith('Reject') else 'accept';action=acts[1];assert acts[0]['decision']=='accept' and action['decision']==kind and action['proposal_id']==candidate['proposal_id'] and action['candidate_hash']==candidate['candidate_hash']
    assert acts[0]['original_id']!=action['original_id']
    if CASE=='testNeedsPlanningCurrentFixedACKLoss':assert action['committed_response_suppressed'] and action['delivered_status']==503
    with TestClient(needs_app) as client:receipt=check(client.get('/v1/trip-needs-action-receipts',params=dict(action_id=action['original_id']),headers=headers),'source2-original-receipt')['receipt']
    assert receipt['trip_id']==candidate['trip_id'] and receipt['committed_version']==(None if kind=='reject' else 1)
    with TestClient(api) as client:needs=check(client.get('/v1/needs',params=dict(needs_id='visit'),headers=headers),'source2-canonical-needs')['needs']
    assert needs['version']==1 and needs['fields']['fixed_items'][1]['locked']==known(False)
    with database.connect(scope_for(ISSUER,subject)) as conn:
     role=conn.execute('SELECT current_user').fetchone()[0];trips=conn.execute('SELECT trip_id,version,content FROM cj_trip_record').fetchall();count=conn.execute('SELECT count(*) FROM cj_message_receipt WHERE conversation_id=%s',('source',)).fetchone()[0];ops=conn.execute('SELECT count(*) FROM cj_run_metered_operation o JOIN cj_message_receipt m ON (m.scope,m.run_id)=(o.scope,o.run_id) WHERE m.conversation_id=%s',('source',)).fetchone()[0]
    assert role=='cj_m1_runtime' and count==2 and ops==4
    records={x[0]:(x[1],bytes(x[2])) for x in trips};assert records[source['trip_id']]==(source['version'],packed(source['content']))
    assert hashlib.sha256(records[source['trip_id']][1]).hexdigest()==source['content_sha256']
    assert len(records)==(1 if kind=='reject' else 2)
    if kind=='accept':assert records[candidate['trip_id']]==(1,packed(candidate['content']))
    queries=[x for x in audit if x['path']=='/v1/trip-needs-action-receipts' and x['query']==dict(action_id=[action['original_id']])];assert all(x['status']==200 and x['receipt_present'] for x in queries)
    value=dict(runtime_role=role,message_posts=2,model_calls=4,registered_operations=4,planning_posts=2,manual_prepares=manual_count,manual_saves=manual_count,source_trip_id=source['trip_id'],source_version=source['version'],source_content_sha256=source['content_sha256'],source_unchanged=True,source_bytes_unchanged=True,proposed_trip_id=candidate['trip_id'],original_action_id=action['original_id'],original_action_sha256=action['input_sha256'],kind=kind,formal_count=len(records),receipt_queries=len(queries),canonical_needs_unchanged=True,trip_local_fixed_preserved=True,commit_ack_suppressed=CASE=='testNeedsPlanningCurrentFixedACKLoss')
    r['current_planning_proof']=value;save();return value
   class Control(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
     try:
      url=urlparse(self.path);assert parse_qs(url.query).get('case')==[CASE]
      if url.path=='/prepare':value=dict(case_id=CASE,endpoint=endpoint,conversation='source',namespace=namespace['id'],accounts=tokens,subjects=subjects,formal_trips=[] if PLANNING_PREFIX else [dict(id=tid,title=formal['content']['title'],version=1,content_sha256=formal['content_sha256'],item_ids=[x['id'] for x in formal['content']['items']])],manual_profile=True,manual_only=not PLANNING_PREFIX,needs_planning=PLANNING_PREFIX)
      elif url.path=='/prefix-not-sent':value=prefix_not_sent()
      elif url.path=='/wait-planning-response':
       assert CASE in ('testNeedsPlanningLateAccount','testNeedsPlanningInterruptedAccept') and late_captured.wait(20);value=dict(status='actual protected200 held')
      elif url.path=='/release-planning-response':
       assert CASE in ('testNeedsPlanningLateAccount','testNeedsPlanningInterruptedAccept') and late_captured.is_set()
       if CASE=='testNeedsPlanningLateAccount':assert any(x['account']=='B' and x['path']=='/v1/message-receipts' and x.get('status')==200 for x in audit)
       late_release.set();value=dict(status='original200 released after lifecycle boundary')
      elif url.path=='/invalidate-planning-needs':
       assert CASE in ('testNeedsPlanningDiscoveryUnavailable','testNeedsPlanningStaleAccept') and 'needs_correction' not in r
       corrected=item('a','09:00','10:00',True);corrected['description']='SYNTHETIC explicitly corrected source'
       raw=packed(dict(action_id='source-correction',needs_id='visit',expected_version=1,source=dict(kind='manual',text='SYNTHETIC explicit source correction'),changes=dict(fixed_items=[corrected,item('b','11:00','12:00',False)])))
       with TestClient(api) as client:value=check(client.post('/v1/needs-actions',content=raw,headers=binary),'actual-needs-correction')
       r['needs_correction']=value;save()
      elif url.path=='/compete-planning':
       assert CASE=='testNeedsPlanningConflict' and 'competing_planning_receipt' not in r
       proposal=planning_discoveries[0]['proposal'];raw=packed(dict(version='TRIP-needs-action.1',action_id='competing-plan-accept',kind='accept',proposal_id=proposal['proposal_id'],candidate_hash=proposal['candidate_hash']))
       with TestClient(needs_app) as client:value=check(client.post('/v1/trip-needs-actions',content=raw,headers=binary),'actual-competing-plan')
       r['competing_planning_receipt']=value['receipt'];save()
      elif url.path=='/planning-no-decision-proof':value=planning_no_decision_proof()
      elif url.path=='/wait-manual-preparation':
       assert CASE in ('testNeedsManualLateAccount','testNeedsManualPrepareCancellation') and late_captured.wait(20);value=dict(status='actual protected 200 held')
      elif url.path=='/release-manual-preparation':
       assert CASE in ('testNeedsManualLateAccount','testNeedsManualPrepareCancellation') and late_captured.is_set()
       if CASE=='testNeedsManualLateAccount':assert any(x['account']=='B' and x['path']=='/v1/message-receipts' and x.get('status')==200 for x in audit)
       late_release.set();value=dict(status='release after explicit lifecycle change')
      elif url.path=='/manual-compete':
       assert CASE=='testNeedsManualSaveConflict' and 'competing_receipt' not in r
       original=latest_preparation['value'];raw=packed(dict(version='TRIP-needs-save.1',action_id='competing-original-save',proposal_id=original['proposal_id'],candidate_hash=original['candidate_hash']))
       with TestClient(needs_app) as client:value=check(client.post('/v1/trip-needs-saves',content=raw,headers=binary),'competing-save')
       r['competing_receipt']=value['receipt'];save()
      elif url.path=='/current-planning-blocked':value=current_planning_blocked()
      elif url.path=='/current-planning-source':value=current_planning_source()
      elif url.path=='/current-planning-published':value=current_planning_published()
      elif url.path=='/current-planning-proof':value=current_planning_proof()
      elif url.path=='/planning-composition-proof':value=planning_composition_proof()
      elif url.path=='/planning-decision-proof':value=planning_decision_proof()
      elif url.path=='/manual-save-proof':value=proof()
      elif url.path=='/manual-fixed-on-proof':value=proof('locked')
      else:raise ValueError('unknown control')
      raw=json.dumps(value).encode();self.send_response(200);self.end_headers();self.wfile.write(raw)
     except Exception as error:r.setdefault('control_errors',[]).append(type(error).__name__);save();self.send_response(500);self.end_headers();self.wfile.write(type(error).__name__.encode())
   control=ThreadingHTTPServer(('127.0.0.1',0),Control);threading.Thread(target=control.serve_forever,daemon=True).start()
   try:
    spec=importlib.util.spec_from_file_location('manual_native_builder',APP/'scripts/check_ios_trip_confirm.py');builder_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder_module)
    builder=object.__new__(builder_module.XCTestDriver);builder.directory=OUT/'project';builder.directory.mkdir();builder.write_project(0)
    (builder.directory/'G2CControl.swift').write_text((HERE/'DevelopmentScopedMessageUITests.swift').read_text().replace('__FIXTURE_URL__',f'http://127.0.0.1:{control.server_port}'))
    project=builder.directory/'G2CAcceptance.xcodeproj';pbx=project/'project.pbxproj';bundle='space.go2china.scoped.acceptance'
    text=pbx.read_text().replace('space.go2china.foundation.local',bundle).replace('space.go2china.foundation.control',bundle+'.control')
    entitlements=builder.directory/'Manual.entitlements';entitlements.write_bytes(plistlib.dumps({'application-identifier':bundle,'keychain-access-groups':[bundle]}));pbx.write_text(text.replace(json.dumps(str(APP/'ios/App/Development.entitlements')),json.dumps(str(entitlements))))
    result=OUT/(CASE+'.xcresult');cmd=['xcodebuild','-project',str(project),'-scheme','G2CControl','-configuration','Debug','-destination','platform=iOS Simulator,id='+a.simulator,'-derivedDataPath',str(BUILD),'-resultBundlePath',str(result),'-scmProvider','system','-skipPackageUpdates','-onlyUsePackageVersionsFromResolvedFile','-parallel-testing-enabled','NO','-collect-test-diagnostics','never','ARCHS=arm64','ONLY_ACTIVE_ARCH=YES','CODE_SIGNING_ALLOWED=YES','CODE_SIGN_IDENTITY=-','-only-testing:G2CControl/DevelopmentScopedMessageUITests/'+CASE,'test']
    print('MANUAL '+CASE+' backend='+r['backend_head'],flush=True);run=subprocess.run(cmd,cwd=APP,capture_output=True,text=True,timeout=1800)
    log=run.stdout+run.stderr
    for secret in tokens.values():log=log.replace(secret,'<redacted-local-token>')
    (OUT/'native.log').write_text(log);run.check_returncode()
    summary=json.loads(subprocess.check_output(['xcrun','xcresulttool','get','test-results','summary','--path',str(result)]));r['test_summary']=summary;assert summary['passedTests']==1 and summary['failedTests']==summary['skippedTests']==0
    verified=prefix_not_sent() if HISTORY_LARGEST else current_planning_proof() if CURRENT_REPLAN else planning_composition_proof() if CASE=='testNeedsPlanningManualComposition' else planning_decision_proof() if PLANNING_DECISION else planning_no_decision_proof() if PLANNING_NO_DECISION else proof()
    if CURRENT_REPLAN:assert verified['receipt_queries']>=1
    elif CASE=='testNeedsPlanningManualComposition':assert verified['planning_receipt_queries']>=2
    elif PLANNING_DECISION:assert verified['receipt_queries']>=1
    if not PLANNING_PREFIX and CASE not in ('testNeedsManualLateAccount','testNeedsManualPrepareCancellation','testNeedsManualCanonicalFixedRefusal','testNeedsManualInvalidWindow'):assert verified['receipt_queries']>=1
    container=Path(subprocess.check_output(['xcrun','simctl','get_app_container',a.simulator,bundle,'data'],text=True).strip())
    for f in container.rglob('*'):
     if f.is_file() and not f.is_symlink():assert all(secret.encode() not in f.read_bytes() for secret in tokens.values()) and b'-----BEGIN PRIVATE KEY-----' not in f.read_bytes()
    assert head(APP)==r['app_head'] and head(BACKEND)==r['backend_head']
    assert all(hashlib.sha256((APP/f).read_bytes()).hexdigest()==h for f,h in r['source_hashes'].items())
    assert all(hashlib.sha256((BACKEND/f).read_bytes()).hexdigest()==h for f,h in r['backend_hashes'].items())
    r['status']='PASS_APP_WITH_PINNED_CANDIDATE_BACKEND';r['token_key_scan']='PASS'
   finally:
    prefix_stop.set();message_ready.set();current_ready.set()
    if PLANNING_PREFIX:worker_thread.join(20)
    if CURRENT_REPLAN:current_thread.join(20)
    late_release.set();r['observed_requests']=audit;save();server.should_exit=True;thread.join(10);sock.close();control.shutdown();control.server_close()
  r['private_pg_stopped']=True
except BaseException as error:r['status']='FAIL';r['error']=type(error).__name__;raise
finally:save()
