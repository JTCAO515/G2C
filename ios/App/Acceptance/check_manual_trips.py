"""Actual App manual Trip diagnostics against an explicitly pinned local backend.

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
p.add_argument('--case',choices=['testNeedsManualTitleSave','testNeedsManualFixedRoundTrip','testNeedsManualTimeTextSave','testNeedsManualSaveACKLoss','testNeedsManualSaveConflict','testNeedsManualLateAccount','testNeedsManualPrepareCancellation'],required=True)
a=p.parse_args();BACKEND=a.backend_root.resolve();OUT=a.output.resolve();BUILD=a.build_dir.resolve();CASE=a.case
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
from cj_api.local_app import create_local_app,LocalDatabase,ISSUER,scope_for,load_confirmation_signer
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
for module in ('CJShell','CJTripClient','CJMessageClient','CJNeedsClient','CJAuth'):
 source_files+=list((APP/'ios/Modules'/module/'Sources').rglob('*.swift'))
def fingerprint(root,paths):return {str(path.relative_to(root)):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}
backend_files=[BACKEND/name for name in subprocess.check_output(['git','ls-files','backend','scripts','contracts','pyproject.toml','uv.lock'],cwd=BACKEND,text=True).splitlines()]
r=dict(status='RUNNING',layer='actual Simulator/signed API/private PG/pinned backend candidate',app_head=head(APP),backend_head=head(BACKEND),backend_root_verified=True,source_hashes=fingerprint(APP,source_files),backend_hashes=fingerprint(BACKEND,backend_files),responses=[],unrun=['main backend delivery if pin unmerged','real services/models/fees/cloud/device'])
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
   if CASE=='testNeedsManualLateAccount':subjects['B']='manual-native-b-'+uuid.uuid4().hex
   dev_auth.init(auth,list(subjects.values()))
   context=load_run_context(a.run_context.resolve())
   for owner in subjects.values():
    subprocess.run([sys.executable,'-B',str(BACKEND/'scripts/local_run_context.py'),'--conninfo-json',str(connection),'--auth-dir',str(auth),'--run-context',str(a.run_context.resolve()),'--subject',owner,'init-budget'],cwd=BACKEND,check=True,capture_output=True)
    dev_auth.activate_travel(connection,owner,context,'MESSAGE-TRAVEL-CONSUMER@1')
   signer=load_confirmation_signer(auth);tokens={label:dev_auth.token(auth,owner,120) for label,owner in subjects.items()}
   token=tokens['A'];headers={'Authorization':'Bearer '+token};binary={**headers,'Content-Type':'application/octet-stream'}
   api=create_local_app(conninfo_path=connection,auth_dir=auth,run_context=context,travel_context=True,needs_profile='manual-v1',confirmation_signer=signer)
   with TestClient(api) as client:
    check(client.post('/v1/needs-actions',content=packed(dict(action_id='source',needs_id='visit',expected_version=0,source=dict(kind='manual',text='SYNTHETIC explicit source'),changes=dict(fixed_items=[item('a','09:00','10:00',True),item('b','11:00','12:00',False)]))),headers=binary),'needs')
    namespace=check(client.post('/v1/travel-context-actions',content=packed(dict(version='TRAVEL-context-action.1',action_id='namespace',operation='create',travel_context=None)),headers=binary),'namespace')['receipt']['travel_context']
    chat=check(client.put('/v1/conversations',params=dict(conversation_id='source'),headers=headers),'chat')
    original=check(client.post('/v2/messages',content=packed(dict(version='MESSAGE-send.2',conversation_id='source',message_id='source-message',text='SYNTHETIC use declared constraints',trip_id=None,creation_intent='consider_trip',expected_generation=chat['generation'],expected_sequence=0,travel_context=dict(id=namespace['id'],expected_version=1),needs_reference=dict(id='visit',expected_version=1))),headers=binary),'message')
   database=LocalDatabase(connection,run_context=context,travel_context=True,needs_context=True);model=NeedsPlanFakeProvider()
   outcomes=run_once(database,model,auth,draft_profile='needs-structured.1');assert len(outcomes)==1 and outcomes[0].status=='completed' and outcomes[0].proposal_id
   r['source_provider_calls']=model.calls
   needs_app=create_local_needs_app(conninfo_path=connection,auth_dir=auth,run_context=context,confirmation_signer=signer)
   with TestClient(needs_app) as client:
    proposal=check(client.get('/v2/trip-needs-proposals',params=dict(proposal_id=outcomes[0].proposal_id),headers=headers),'source-proposal')['proposal']
    receipt=check(client.post('/v1/trip-needs-actions',content=packed(dict(version='TRIP-needs-action.1',action_id='source-accept',kind='accept',proposal_id=proposal['proposal_id'],candidate_hash=proposal['candidate_hash'])),headers=binary),'source-adopt')['receipt']
   tid=receipt['trip_id'];structured=create_local_structured_read_app(conninfo_path=connection,auth_dir=auth,run_context=context)
   with TestClient(structured) as client:formal=check(client.get('/v5/trip-structured',params=dict(trip_id=tid),headers=headers),'formal')['trip']
   assert formal['content']['content_version']=='structured.2' and formal['version']==1
   r['source_formal']=formal;r['source_message']=original['receipt'];save()
   audit=[];latest_preparation={};late_captured=threading.Event();late_release=threading.Event();late_state={}
   async def observed(scope,receive,send):
    if scope.get('type')!='http':return await api(scope,receive,send)
    path=scope['path'];authorization=dict(scope['headers']).get(b'authorization',b'').decode('ascii');label=next((label for label,value in tokens.items() if authorization=='Bearer '+value),None);entry=dict(method=scope['method'],path=path,account=label);audit.append(entry);parts=[];actual_reply=[];reply_parts=[]
    drop_ack=CASE=='testNeedsManualSaveACKLoss' and path=='/v1/trip-needs-saves' and scope['method']=='POST'
    hold_prepare=CASE in ('testNeedsManualLateAccount','testNeedsManualPrepareCancellation') and path=='/v1/trip-needs-edits' and scope['method']=='POST'
    if scope.get('query_string'):entry['query']=parse_qs(scope['query_string'].decode('ascii'))
    async def received():
     value=await receive()
     if value['type']=='http.request':parts.append(value.get('body',b''))
     return value
    async def sent(value):
     if value['type']=='http.response.start':entry['status']=value['status']
     if value['type']=='http.response.body':reply_parts.append(value.get('body',b''))
     if drop_ack or hold_prepare:actual_reply.append(value)
     else:await send(value)
    target=structured if path in ('/v1/trip-structured-list','/v5/trip-structured') else needs_app if path.startswith('/v1/trip-needs-') else api
    await target(scope,received,sent)
    if path=='/v1/trip-needs-edits' and scope['method']=='POST' and entry['status']==200:latest_preparation['value']=json.loads(b''.join(reply_parts))['preparation']
    if path=='/v1/trip-needs-edits' and scope['method']=='GET' and entry['status']==200:entry['preparation_present']=json.loads(b''.join(reply_parts))['preparation'] is not None
    if path=='/v1/trip-needs-action-receipts' and entry['status']==200:entry['receipt_present']=json.loads(b''.join(reply_parts))['receipt'] is not None
    if hold_prepare:
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
   server=uvicorn.Server(uvicorn.Config(observed,host='127.0.0.1',port=0,log_level='error',access_log=False))
   sock=socket.socket();sock.bind(('127.0.0.1',0));sock.listen();endpoint='http://127.0.0.1:'+str(sock.getsockname()[1]);thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
   def proof(stage=None):
    if CASE=='testNeedsManualLateAccount':
     assert late_captured.is_set() and late_release.is_set() and late_state.get('original_response_sent')
     prepares=[x for x in audit if x['path']=='/v1/trip-needs-edits' and x['method']=='POST']
     assert len(prepares)==1 and prepares[0]['account']=='A' and prepares[0]['status']==200
     assert not any(x['method']=='POST' and x['path']!='/v1/trip-needs-edits' for x in audit)
     assert any(x['account']=='B' and x['path']=='/v1/message-receipts' and x.get('status')==200 for x in audit)
     assert any(x['account']=='B' and x['path']=='/v1/trip-structured-list' and x.get('status')==200 for x in audit)
     with TestClient(needs_app) as client:foreign=check(client.get('/v1/trip-needs-edits',params=dict(request_id=prepares[0]['original_id']),headers={'Authorization':'Bearer '+tokens['B']}),'other-owner-original')['preparation']
     assert foreign is None
     with database.connect(scope_for(ISSUER,subject)) as conn:trips=conn.execute('SELECT trip_id,version,content FROM cj_trip_record').fetchall()
     assert len(trips)==1 and trips[0][0]==tid and trips[0][1]==1 and json.loads(bytes(trips[0][2]))==formal['content']
     assert model.calls==r['source_provider_calls']
     value=dict(late_state,verified_B_before_release=True,formal_version=1,formal_unchanged=True,prepare_posts=1,saves=0,edit_model_calls=0,foreign_original=None)
     r['proof']=value;save();return value
    if CASE=='testNeedsManualPrepareCancellation':
     assert late_captured.is_set() and late_release.is_set() and late_state.get('original_response_sent')
     prepares=[x for x in audit if x['path']=='/v1/trip-needs-edits' and x['method']=='POST'];queries=[x for x in audit if x['path']=='/v1/trip-needs-edits' and x['method']=='GET']
     assert len(prepares)==1 and prepares[0]['account']=='A' and prepares[0]['status']==200
     assert len(queries)>=1 and all(q['query']==dict(request_id=[prepares[0]['original_id']]) and q['status']==200 and q['preparation_present'] for q in queries)
     assert not any(x['method']=='POST' and x['path']!='/v1/trip-needs-edits' for x in audit) and model.calls==r['source_provider_calls']
     with database.connect(scope_for(ISSUER,subject)) as conn:
      role=conn.execute('SELECT current_user').fetchone()[0];trips=conn.execute('SELECT trip_id,version,content FROM cj_trip_record').fetchall()
     assert role=='cj_m1_runtime' and len(trips)==1 and trips[0][0]==tid and trips[0][1]==1 and json.loads(bytes(trips[0][2]))==formal['content']
     value=dict(late_state,runtime_role=role,formal_version=1,formal_unchanged=True,prepare_posts=1,original_queries=len(queries),same_original_id=True,saves=0,edit_model_calls=0)
     r['proof']=value;save();return value
    fixed_case=CASE=='testNeedsManualFixedRoundTrip'
    expected_version=2 if not fixed_case or stage=='locked' else 3
    expected_count=1 if not fixed_case or stage=='locked' else 2
    with database.connect(scope_for(ISSUER,subject)) as conn:
     role=conn.execute('SELECT current_user').fetchone()[0];trips=conn.execute('SELECT trip_id,version,content FROM cj_trip_record').fetchall()
    assert role=='cj_m1_runtime' and len(trips)==1 and trips[0][0]==tid and trips[0][1]==expected_version
    current=json.loads(bytes(trips[0][2]))
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
   class Control(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
     try:
      url=urlparse(self.path);assert parse_qs(url.query).get('case')==[CASE]
      if url.path=='/prepare':value=dict(case_id=CASE,endpoint=endpoint,conversation='source',namespace=namespace['id'],accounts=tokens,subjects=subjects,formal_trips=[dict(id=tid,title=formal['content']['title'],version=1,content_sha256=formal['content_sha256'],item_ids=[x['id'] for x in formal['content']['items']])],manual_profile=True,manual_only=True)
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
    verified=proof()
    if CASE not in ('testNeedsManualLateAccount','testNeedsManualPrepareCancellation'):assert verified['receipt_queries']>=1
    container=Path(subprocess.check_output(['xcrun','simctl','get_app_container',a.simulator,bundle,'data'],text=True).strip())
    for f in container.rglob('*'):
     if f.is_file() and not f.is_symlink():assert all(secret.encode() not in f.read_bytes() for secret in tokens.values()) and b'-----BEGIN PRIVATE KEY-----' not in f.read_bytes()
    assert head(APP)==r['app_head'] and head(BACKEND)==r['backend_head']
    assert all(hashlib.sha256((APP/f).read_bytes()).hexdigest()==h for f,h in r['source_hashes'].items())
    assert all(hashlib.sha256((BACKEND/f).read_bytes()).hexdigest()==h for f,h in r['backend_hashes'].items())
    r['status']='PASS_APP_WITH_PINNED_CANDIDATE_BACKEND';r['token_key_scan']='PASS'
   finally:
    late_release.set();r['observed_requests']=audit;save();server.should_exit=True;thread.join(10);sock.close();control.shutdown();control.server_close()
  r['private_pg_stopped']=True
except BaseException as error:r['status']='FAIL';r['error']=type(error).__name__;raise
finally:save()
