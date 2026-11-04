"""Partial #228 native typed-root acceptance; never claims the complete frame 4.

Real signed loopback producers, fresh private PG, official explicit budget and
formal run_once/FakeProvider. No injected business rows, quota, HTTP refusal or
UI model. Evidence stays external and every failed run gets a new directory.
"""
import argparse,asyncio,hashlib,importlib.util,json,os,plistlib,secrets,subprocess,sys,tempfile,threading,time,uuid
from datetime import datetime,timedelta,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs,urlparse
from urllib.request import Request,urlopen

ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
BUNDLE='space.go2china.typed-memory.acceptance'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    target=parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--simulator');target.add_argument('--device')
    parser.add_argument('--local-tls',type=Path);parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--run-context',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--build-dir',type=Path,required=True)
    parser.add_argument('--case',choices=['testEnglishSaveReadAndOwnedTravel','testChineseLargeSaveReadAndRecall','testUnknownReopenAndLifecycleRecall','testSwitchAccountAfterActualCommit','testReleaseTypedFlagsRemainClosed','testLegacyUnknownCannotBypassTypedMode','testRealConflictKeepsOriginalAndAllowsFreshSave','testTypedUnknownCannotReactivateLegacyWriter','testTypedQuestionsEnglish','testTypedQuestionsChineseLargest','testTypedGroupsPaged','testTypedGroupsLateAccount'],default='testEnglishSaveReadAndOwnedTravel')
    args=parser.parse_args();output=args.output.resolve();build=args.build_dir.resolve()
    tls=None
    if args.device:
        if not args.local_tls:parser.error('--device requires the approved --local-tls profile')
        from m4_device import LocalTLS,configure_project
        from m4_native import DeviceNative,authenticated_control
        tls=LocalTLS.load(args.local_tls)
    elif args.local_tls or args.prepare_only:parser.error('Device options require --device')
    chinese=args.case in ('testChineseLargeSaveReadAndRecall','testTypedQuestionsChineseLargest')
    collection_questions=args.case in ('testTypedQuestionsEnglish','testTypedQuestionsChineseLargest')
    collection_groups=args.case in ('testTypedGroupsPaged','testTypedGroupsLateAccount')
    groups_late=args.case=='testTypedGroupsLateAccount'
    unknown=args.case=='testUnknownReopenAndLifecycleRecall'
    switching=args.case=='testSwitchAccountAfterActualCommit'
    release=args.case=='testReleaseTypedFlagsRemainClosed'
    legacy=args.case=='testLegacyUnknownCannotBypassTypedMode'
    conflict=args.case=='testRealConflictKeepsOriginalAndAllowsFreshSave'
    reverse=args.case=='testTypedUnknownCannotReactivateLegacyWriter'
    if output.is_relative_to(ROOT) or build.is_relative_to(ROOT):raise ValueError('external evidence required')
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT):raise ValueError('commit candidate first')
    os.umask(0o077);output.mkdir(parents=True,mode=0o700)
    if (output/'report.json').exists():raise ValueError('preserve old report')
    for key in tuple(os.environ):
        if key.startswith(('PG','LIBPQ','CJ_LOCAL_','SIMCTL_CHILD_','G2C_DEV_')) or key in ('DATABASE_URL','CJ_DATABASE_URL'):os.environ.pop(key)
    os.environ.update(CJ_ENV='local',DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer',OS_ACTIVITY_MODE='disable')
    sys.path.insert(0,str(ROOT/'scripts'))
    import psycopg,uvicorn,dev_auth,migrate
    from fastapi.testclient import TestClient
    from pg_suites import cluster
    from cj_api.local_app import (create_local_app,LocalDatabase,ISSUER,scope_for,load_confirmation_signer,load_history_configuration)
    from cj_api.local_run_context import load_run_context
    from cj_message.travel import ABI
    from cj_agent.provider import FakeProvider
    from cj_memory.local import LocalMemoryConfiguration
    from cj_memory.typed_api import create_local_typed_app
    from cj_memory.typed_local import TypedConfiguration
    from cj_memory.typed_runtime import TypedRuntimeConfiguration
    from run_worker import run_once
    context=load_run_context(args.run_context)
    if context.version!='CJ-LOCAL-RUN@2':raise ValueError('explicit @2 required')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    sources=[*list((ROOT/'ios/App').glob('*.swift')),HERE/'DevelopmentTypedMemoryUITests.swift',Path(__file__)]
    if tls:sources += [HERE/name for name in ('m4_device.py','m4_native.py','m4_artifacts.py','M4DeviceControl.swift','M4DeviceTestSession.swift')]
    for name in ('CJShell','CJMemoryClient','CJMessageClient','CJRunClient'):
        sources+=list((ROOT/'ios/Modules'/name/'Sources').rglob('*.swift'))
    report=dict(status='RUNNING',head=head,cases={},scope=args.case+('; #332 optional questions and loaded-page groups only' if collection_questions else '; complete frame 4 still requires the whole matrix'),
        source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        git_trees={name:subprocess.check_output(['git','rev-parse','HEAD:'+name],cwd=ROOT,text=True).strip() for name in ('ios','backend','contracts','scripts')},
        run_context=json.loads(args.run_context.read_text()),
        unrun=['complete #228 frame4 matrix','other native cases','lifecycle/unknown/interoperability matrix','real services/models/cloud/fees','physical device/VoiceOver'])
    if collection_questions or collection_groups:report['unrun']=['#332 remaining native cases/pagination/late/Release matrix','real services/models/cloud/fees','physical device/VoiceOver']
    if tls:report.update(layer='signed approved iPhone/local pinned HTTPS/private PG/formal run_once/FakeProvider',
        raw_native_bundle_shareable=False,build_inputs_shareable=False,
        unrun=['remaining owning matrix cases','real services/models/cloud/fees','VoiceOver','actual system font setting record'])
    lock=threading.RLock()
    def save():
        with lock:(output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    save()
    try:
        with tempfile.TemporaryDirectory(prefix='cj228t-',dir='/tmp') as temporary:
            root=Path(temporary)
            with cluster('typedui',port=55791,role='cj228t_initializer',root=root/'pg') as config:
                with psycopg.connect(**config,autocommit=True) as connection:
                    chain=migrate.load();migrate.up(connection,chain,chain[-1]['version'])
                conn=root/'connection.json';conn.write_text(json.dumps(config));conn.chmod(0o600)
                subjects={key:'cj228t-'+uuid.uuid4().hex for key in ('A','B')}
                auth=root/'auth';dev_auth.init(auth,list(subjects.values()))
                tokens={key:dev_auth.token(auth,subject,120) for key,subject in subjects.items()}
                headers={key:{'Authorization':'Bearer '+token} for key,token in tokens.items()}
                for subject in subjects.values():
                    subprocess.run([sys.executable,'-B',str(ROOT/'scripts/local_run_context.py'),'--conninfo-json',str(conn),
                        '--auth-dir',str(auth),'--run-context',str(args.run_context.resolve()),'--subject',subject,'init-budget'],
                        cwd=ROOT,check=True,capture_output=True)
                    dev_auth.activate_travel(conn,subject,context,ABI)
                slots={'preference':dict(kind='preference',collection_allowed=True,semantic_resolved=True)}
                if (collection_questions and chinese) or collection_groups:
                    slots.update(a_fact=dict(kind='fact',collection_allowed=True,semantic_resolved=True),b_experience=dict(kind='experience',collection_allowed=True,semantic_resolved=True))
                if collection_groups:
                    for index in range(22):
                        kind='fact' if index<10 else 'experience' if index<20 else 'preference'
                        slots['group_slot_'+str(index).zfill(2)]=dict(kind=kind,collection_allowed=True,semantic_resolved=True)
                if reverse:slots['legacy.read']=dict(kind='preference',collection_allowed=True,semantic_resolved=True)
                legacy_profile=dict(subjects=['self'],slots=slots,extents=['long_term'],context_ids=[])
                legacy_policy=dict(version='local-memory-policy.1',expires_at=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),profiles={subject:legacy_profile for subject in subjects.values()})
                app=create_local_app(memory_configuration=LocalMemoryConfiguration.from_bytes(json.dumps(legacy_policy).encode()),conninfo_path=conn,auth_dir=auth,run_context=context,travel_context=True,
                    confirmation_signer=load_confirmation_signer(auth),history_configuration=load_history_configuration(auth))
                travels=[]
                with TestClient(app) as client:
                    for _ in range(2):
                        response=client.post('/v1/travel-context-actions',content=json.dumps(dict(version='TRAVEL-context-action.1',
                            action_id=uuid.uuid4().hex,operation='create',travel_context=None)).encode(),
                            headers={**headers['A'],'Content-Type':'application/octet-stream'})
                        response.raise_for_status();travels.append(response.json()['receipt']['travel_context']['id'])
                    for conversation in ('typed-chat-1','typed-chat-2','typed-chat-3'):
                        client.put('/v1/conversations',params={'conversation_id':conversation},headers=headers['A']).raise_for_status()
                profile=dict(subjects=['self'],slots=slots,extents=['long_term','current'],context_ids=[])
                collection=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',
                    expires_at=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),profiles={subject:profile for subject in subjects.values()}),
                    travel_contexts={subjects['A']:travels,subjects['B']:[]})
                typed=TypedConfiguration.from_bytes(json.dumps(collection).encode())
                runtime=TypedRuntimeConfiguration.from_bytes(json.dumps(dict(version='local-memory-run.2',collection=collection,
                    selections={subject:dict(subject='self',slots=['preference'],max_bytes=2000) for subject in subjects.values()})).encode())
                memory=create_local_typed_app(conninfo_path=conn,auth_dir=auth,configuration=typed)
                database=LocalDatabase(conn,run_context=context,travel_context=True)
                group_seeds=[]
                if collection_groups:
                    with TestClient(memory) as client:
                        for index in range(22):
                            kind='fact' if index<10 else 'experience' if index<20 else 'preference'
                            slot='group_slot_'+str(index).zfill(2)
                            command=dict(version='MEMORY-manual.2',operation_id='group-save-'+str(index),item_id='group-'+str(index).zfill(2),subject='self',slot=slot,kind=kind,text='SYNTHETIC grouped '+kind+' '+str(index),extent='long_term',context=None,occurred_at='SYNTHETIC time unknown')
                            raw=json.dumps(command,ensure_ascii=False,separators=(',',':')).encode()
                            response=client.post('/v2/memories',content=raw,headers={**headers['A'],'Content-Type':'application/octet-stream'})
                            report.setdefault('group_seed_attempts',[]).append(dict(index=index,status=response.status_code,error=response.json().get('error'),input_sha256=hashlib.sha256(raw).hexdigest()))
                            save();response.raise_for_status()
                            group_seeds.append(dict(command=command,input_sha256=hashlib.sha256(raw).hexdigest(),receipt=response.json()))
                    report['group_seed_receipts']=group_seeds;save()
                audit=[];errors=[];iterations=[0];outcomes=[];stop=threading.Event();fixture_actions=[]
                network=dict(lose=None,hold=False);held=threading.Event();released=threading.Event();response_sent=threading.Event()
                class ObservedMemoryProvider(FakeProvider):
                    def __init__(self):super().__init__();self.memory_inputs=[]
                    def stream(self,inputs,system=None):
                        # Consume only the actual C snapshot injected by the formal
                        # worker, never an expected test value or App chat cache.
                        payload=json.loads(inputs[0]['content'].split('\n',1)[1])
                        if payload['version']!='MEMORY-RUN-CONSUME@2':raise ValueError('typed runtime snapshot required')
                        with lock:self.memory_inputs.append(payload)
                        self.calls+=1
                        yield 'Current persisted memory: ' + ' | '.join(item['text'] for item in payload['items'])
                model=ObservedMemoryProvider()
                def worker():
                    try:
                        while not stop.is_set():
                            completed=run_once(database,model,auth,memory_configuration=runtime)
                            with lock:outcomes.extend(dict(message_id=o.message_id,run_id=o.run_id,status=o.status) for o in completed)
                            iterations[0]+=1;stop.wait(.1)
                    except BaseException as error:errors.append(type(error).__name__);stop.set()
                worker_thread=threading.Thread(target=worker,daemon=True);worker_thread.start()
                def observed(application,label):
                    async def invoke(scope,receive,send):
                        if scope['type']!='http':return await application(scope,receive,send)
                        bearer=dict(scope['headers']).get(b'authorization',b'')
                        account=next((key for key,token in tokens.items() if bearer==('Bearer '+token).encode()),None)
                        event=dict(host=label,method=scope['method'],path=scope['path'],status=None,account=account);raw=bytearray()
                        if collection_groups and scope['path']=='/v2/memories':event['query']=parse_qs(scope.get('query_string',b'').decode())
                        with lock:audit.append(event)
                        async def received():
                            message=await receive()
                            if scope['method']=='POST' and scope['path'].startswith(('/v2/memor','/v1/memor')) and message['type']=='http.request':raw.extend(message.get('body',b''))
                            return message
                        captured=[]
                        async def sent(message):
                            if message['type']=='http.response.start':event['status']=message['status']
                            captured.append(message)
                        await application(scope,received,sent)
                        if raw:
                            event['input_sha256']=hashlib.sha256(raw).hexdigest()
                            if event['status'] is not None:
                                field='operation_id' if scope['path'] in ('/v2/memories','/v1/memories') else 'action_id'
                                event[field]=json.loads(raw)[field]
                                event['fixture']=any(event[field]==row['action_id'] for row in fixture_actions)
                            if event['status']!=200:
                                body=b''.join(message.get('body',b'') for message in captured)
                                error=json.loads(body)['error'];event['producer_error']=dict(code=error['code'],outcome=error['outcome'])
                        kind='legacy' if scope['path']=='/v1/memories' else 'save' if scope['path']=='/v2/memories' else 'management'
                        committed=scope['method']=='POST' and scope['path'].startswith(('/v2/memor','/v1/memor')) and event['status']==200
                        if committed and network['lose']==kind:
                            network['lose']=None;event['actual_200_ack_lost']=True;save()
                            await send(captured[0])
                            # Lose only the network body AFTER the real producer
                            # committed. Do not fabricate a business rejection.
                            raise RuntimeError('controlled ACK loss after actual commit')
                        delayed=network['hold'] and (committed or (groups_late and label=='memory' and scope['path']=='/v2/memories' and scope['method']=='GET' and account=='A' and event['status']==200))
                        if delayed:
                            network['hold']=False;event['held_at']=time.monotonic();held.set();save()
                            if not await asyncio.to_thread(released.wait,30):raise TimeoutError('actual response release required')
                        for message in captured:await send(message)
                        if delayed:event['released_at']=time.monotonic();response_sent.set()
                    return invoke
                servers=[];threads=[]
                for application,label in ((app,'main'),(memory,'memory')):
                    server=uvicorn.Server(uvicorn.Config(observed(application,label),host=tls.host if tls else '127.0.0.1',port=0,log_level='error',
                        **(tls.uvicorn_options() if tls else {})))
                    thread=threading.Thread(target=server.run,daemon=True);thread.start();servers.append(server);threads.append(thread)
                    deadline=time.monotonic()+20
                    while not server.started:
                        if not thread.is_alive() or time.monotonic()>deadline:raise RuntimeError('signed API startup')
                        time.sleep(.05)
                endpoints=[('https://'+tls.host if tls else 'http://127.0.0.1')+':'+str(server.servers[0].sockets[0].getsockname()[1]) for server in servers]
                def items():
                    with TestClient(memory) as client:
                        response=client.get('/v2/memories',params={'limit':20},headers=headers['A']);response.raise_for_status()
                        return response.json()['items']
                def proof():
                    values=items()
                    with database.connect(scope_for(ISSUER,subjects['A'])) as connection:
                        role=connection.execute('SELECT current_user,current_role').fetchone()
                        messages=connection.execute('SELECT count(*) FROM cj_message_receipt').fetchone()[0]
                        registered=connection.execute('SELECT kind,count(*) FROM cj_run_metered_operation GROUP BY kind ORDER BY kind').fetchall()
                        sources=connection.execute('SELECT source_id,version,active,approved_input FROM cj_memory_source ORDER BY source_id').fetchall()
                    result=dict(items=values,role=list(role),message_count=messages,model_calls=model.calls,formal_worker_iterations=iterations[0],
                        worker_errors=list(errors),requests=list(audit),outcomes=list(outcomes),memory_inputs=list(model.memory_inputs),registered_operations=registered,
                        fixture_actions=fixture_actions,source_rows=[dict(source_id=sid,version=version,active=active,approved_sha256=hashlib.sha256(bytes(raw)).hexdigest()) for sid,version,active,raw in sources])
                    report['proof']=result
                    report.setdefault('consumption_proofs',{})[str(messages)]=result
                    save();return result
                def groups_proof():
                    assert collection_groups and len(group_seeds)==22
                    rows=[];after=None
                    with TestClient(memory) as client:
                        for _ in range(4):
                            query=dict(limit=20)
                            if after is not None:query['after']=after
                            response=client.get('/v2/memories',params=query,headers=headers['A']);response.raise_for_status();page=response.json()['items']
                            if not page:break
                            rows+=page;after=page[-1]['command']['item_id']
                        other=client.get('/v2/memories',params=dict(limit=20),headers=headers['B']);other.raise_for_status();assert other.json()['items']==[]
                    assert [x['command']['item_id'] for x in rows]==['group-'+str(i).zfill(2) for i in range(22)]
                    assert [x['command']['text'] for x in rows]==[x['command']['text'] for x in group_seeds]
                    assert not any(x['method']=='POST' for x in audit) and model.calls==0 and not outcomes and not errors
                    with database.connect(scope_for(ISSUER,subjects['A'])) as connection:
                        role=connection.execute('SELECT current_user').fetchone()[0];sources=connection.execute('SELECT source_id,approved_input FROM cj_memory_source ORDER BY source_id').fetchall()
                    assert role=='cj_m1_runtime' and len(sources)==22
                    reads=[x for x in audit if x['host']=='memory' and x['path']=='/v2/memories']
                    if groups_late:
                        held_reads=[x for x in reads if 'released_at' in x];assert len(held_reads)==1 and held_reads[0]['account']=='A' and held_reads[0]['status']==200
                        assert held_reads[0]['released_at']-held_reads[0]['held_at']<14
                        assert any(x['account']=='B' and x['status']==200 for x in reads)
                    else:
                        assert [x['query'] for x in reads]==[{'limit':['20']},{'limit':['20'],'after':['group-19']},{'limit':['20'],'after':['group-21']}]
                    value=dict(role=role,records=22,app_writes=0,model_calls=0,all_original_texts_preserved=True,source_hashes={sid:hashlib.sha256(bytes(raw)).hexdigest() for sid,raw in sources},reads=reads,late=groups_late)
                    report['groups_proof']=value;save();return value
                class Control(BaseHTTPRequestHandler):
                    def log_message(self,*_):pass
                    def do_GET(self):
                        try:
                            parsed=urlparse(self.path)
                            if parsed.path=='/prepare':value=dict(endpoint=endpoints[0],memory_endpoint=endpoints[1],accounts={} if tls else tokens,subjects=subjects,travel_ids=travels,
                                travel_profile=json.dumps(dict(version='app-travel.1',travel_ids=travels)),
                                question_count=(3 if chinese else 2) if collection_questions else None,legacy_profile=json.dumps(legacy_profile),memory_profile=json.dumps(dict(version='app-memory.2',subjects=['self'],slots=slots,extents=['long_term','current'])))
                            elif parsed.path=='/groups-proof':value=groups_proof()
                            elif parsed.path=='/collection-no-write':
                                assert collection_questions and not items() and model.calls==0
                                assert not any(x['method']=='POST' for x in audit)
                                value=dict(writes=0,model_calls=0,stage='browse/skip/review')
                                report.setdefault('collection_zero_write_proofs',[]).append(value);save()
                            elif parsed.path=='/collection-saved':
                                assert collection_questions
                                value=proof();assert len(value['items'])==1 and value['message_count']==model.calls==0
                                command=value['items'][0]['command'];assert command['subject']=='self' and command['slot']=='preference' and command['kind']=='preference'
                                assert command['context']==(dict(kind='travel',id=travels[0],expected_version=1) if chinese else None)
                                writes=[x for x in audit if x['host']=='memory' and x['method']=='POST']
                                assert len(writes)==1 and writes[0]['path']=='/v2/memories' and writes[0]['status']==200
                            elif parsed.path=='/arm-loss':
                                kind=parse_qs(parsed.query)['kind'][0]
                                if kind not in ('save','management','legacy'):raise ValueError('explicit loss kind required')
                                network['lose']=kind;value={}
                            elif parsed.path=='/arm-hold':network['hold']=True;value={}
                            elif parsed.path=='/wait-held':
                                if not held.wait(15):raise TimeoutError('real response not captured')
                                value={}
                            elif parsed.path=='/release-held':
                                released.set()
                                if not response_sent.wait(10):raise TimeoutError('real response not released')
                                value={}
                            elif parsed.path=='/concurrent-pause':
                                item,=items()
                                action=dict(version='MEMORY-management.2',action_id=uuid.uuid4().hex,operation='pause',
                                    item_id=item['command']['item_id'],expected_version=item['version'],expected_source_version=item['command']['source_version'])
                                raw=json.dumps(action,separators=(',',':')).encode()
                                row=dict(action_id=action['action_id'],input_sha256=hashlib.sha256(raw).hexdigest());fixture_actions.append(row)
                                request=Request(endpoints[1]+'/v2/memory-management-actions',data=raw,
                                    headers={**headers['A'],'Content-Type':'application/octet-stream'},method='POST')
                                if tls:
                                    # Same observed signed ASGI producer and PG;
                                    # this fixture writer does not use App TLS.
                                    with TestClient(observed(memory,'memory')) as client:
                                        response=client.post('/v2/memory-management-actions',content=raw,
                                            headers={**headers['A'],'Content-Type':'application/octet-stream'})
                                        if response.status_code!=200:raise RuntimeError('real concurrent action rejected')
                                        value=response.json()
                                else:
                                    with urlopen(request,timeout=10) as response:
                                        if response.status!=200:raise RuntimeError('real concurrent action rejected')
                                        value=json.load(response)
                                row['receipt']=value['receipt']
                                if row['receipt']['input_sha256']!=row['input_sha256'] or row['receipt']['version']!=2:raise RuntimeError('real concurrent receipt mismatch')
                            elif parsed.path=='/items':value={('long_term' if x['command']['context'] is None else 'travel'):x['command']['item_id'] for x in items()}
                            elif parsed.path=='/originals':value=dict(legacy=[x['operation_id'] for x in audit if x['method']=='POST' and x['path']=='/v1/memories' and x['status']==200],saves=[x['operation_id'] for x in audit if x['host']=='memory' and x['method']=='POST' and x['path']=='/v2/memories'],
                                management=[x['action_id'] for x in audit if x['host']=='memory' and x['method']=='POST' and x['path']=='/v2/memory-management-actions' and not x.get('fixture',False)])
                            elif parsed.path=='/wait-completed':
                                count=int(parse_qs(parsed.query)['count'][0]);deadline=time.monotonic()+30
                                while sum(o['status']=='completed' for o in outcomes)<count:
                                    if errors or time.monotonic()>deadline:raise RuntimeError('formal worker did not complete requested messages')
                                    time.sleep(.05)
                                value=proof()
                            else:raise ValueError('unknown local control')
                            raw=json.dumps(value).encode();self.send_response(200);self.end_headers();self.wfile.write(raw)
                        except Exception as error:
                            report.setdefault('control_errors',[]).append(type(error).__name__);save();self.send_response(500);self.end_headers()
                control_token=secrets.token_urlsafe(32) if tls else None;native=None
                control=ThreadingHTTPServer((tls.host if tls else '127.0.0.1',0),
                    authenticated_control(Control,control_token,lambda _: native.stage()) if tls else Control)
                if tls:tls.secure_http_server(control)
                threading.Thread(target=control.serve_forever,daemon=True).start()
                try:
                    spec=importlib.util.spec_from_file_location('typed_builder',ROOT/'scripts/check_ios_trip_confirm.py')
                    builder_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder_module)
                    builder=object.__new__(builder_module.XCTestDriver);builder.directory=output/'project';builder.directory.mkdir();builder.write_project(0)
                    control_url=('https://'+tls.host if tls else 'http://127.0.0.1')+':'+str(control.server_port)
                    (builder.directory/'G2CControl.swift').write_text((HERE/'DevelopmentTypedMemoryUITests.swift').read_text().replace('__FIXTURE_URL__',control_url))
                    project=builder.directory/'G2CAcceptance.xcodeproj';pbx=project/'project.pbxproj'
                    text=pbx.read_text().replace('space.go2china.foundation.local',BUNDLE).replace('space.go2china.foundation.control',BUNDLE+'.control')
                    entitlements=builder.directory/'Typed.entitlements';entitlements.write_bytes(plistlib.dumps({'application-identifier':BUNDLE,'keychain-access-groups':[BUNDLE]}))
                    text=text.replace(json.dumps(str(ROOT/'ios/App/Development.entitlements')),json.dumps(str(entitlements)))
                    if release:
                        # Add the existing App Release configuration to this
                        # external test runner, without changing repository CI.
                        line=next(line for line in text.splitlines() if 'A00000000000000000000004 = ' in line)
                        text=text.replace(line,line+'\n'+line.replace('A00000000000000000000004','A0000000000000000000000C',1).replace('name = Debug;','name = Release;',1)).replace('buildConfigurations = (A00000000000000000000004);','buildConfigurations = (A00000000000000000000004, A0000000000000000000000C);')
                    pbx.write_text(text)
                    if tls:
                        _,configuration_file,_=configure_project(project,tls,control_url,control_token,bundle=BUNDLE,include_release=True)
                        native=DeviceNative(args.device,BUNDLE,project,configuration_file,build,ROOT,output,tokens,control_token,report)
                        selected=['DevelopmentTypedMemoryUITests/'+args.case]
                        configuration='Release' if release else 'Debug'
                        report['cases'][args.case]='UNRUN';save()
                        if release:native.build_for_testing('Debug',selected,dict(os.environ))
                        native.build_for_testing(configuration,selected,dict(os.environ))
                        if not args.prepare_only:
                            summary=native.run(configuration,selected,dict(os.environ))
                            (output/'native-summary.json').write_text(json.dumps(summary,indent=2))
                            value=proof()
                    else:
                        command=['xcodebuild','-project',str(project),'-scheme','G2CControl','-configuration','Release' if release else 'Debug',
                            '-destination','platform=iOS Simulator,id='+args.simulator,'-derivedDataPath',str(build),'-resultBundlePath',str(output/'native.xcresult'),
                            '-scmProvider','system','-skipPackageUpdates','-onlyUsePackageVersionsFromResolvedFile','-parallel-testing-enabled','NO','-collect-test-diagnostics','never',
                            'ARCHS=arm64','ONLY_ACTIVE_ARCH=YES','CODE_SIGNING_ALLOWED=YES','CODE_SIGN_IDENTITY=-',
                            '-only-testing:G2CControl/DevelopmentTypedMemoryUITests/'+args.case,'test']
                        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=1800)
                        log=result.stdout+result.stderr
                        for token in tokens.values():log=log.replace(token,'<redacted-local-token>')
                        (output/'native.log').write_text(log)
                        report['cases'][args.case]='PASS' if result.returncode==0 else 'FAIL'
                        value=proof();result.check_returncode()
                        summary=json.loads(subprocess.check_output(['xcrun','xcresulttool','get','test-results','summary','--path',str(output/'native.xcresult')]))
                        (output/'native-summary.json').write_text(json.dumps(summary,indent=2))
                        assert (summary['passedTests'],summary['failedTests'],summary['skippedTests'])==(1,0,0)
                    if not args.prepare_only:
                        assert value['role']==['cj_m1_runtime','cj_m1_runtime'] and not errors and iterations[0]>0
                        posts=[event for event in audit if event['host']=='memory' and event['method']=='POST' and not event.get('fixture',False)]
                        if collection_groups:
                            expected=[x['command']['text'] for x in group_seeds];groups_proof()
                            assert len(posts)==0 and value['message_count']==model.calls==0
                        elif collection_questions:
                            expected=['SYNTHETIC questions preference / 问题偏好 e\u0301']
                            assert len(value['items'])==1 and value['message_count']==model.calls==1 and len(posts)==1
                            assert dict(value['registered_operations']).get('model')==1 and len(report['collection_zero_write_proofs'])==2
                            command=value['items'][0]['command'];assert command['slot']=='preference' and command['kind']=='preference' and command['subject']=='self'
                            assert command['text']==expected[0]
                            assert command['context']==(dict(kind='travel',id=travels[0],expected_version=1) if chinese else None)
                            assert [row['text'] for row in model.memory_inputs[0]['items']]==[command['text']]
                            assert posts[0]['path']=='/v2/memories' and posts[0]['status']==200
                        elif unknown:
                            expected=['Unknown original long term / 未知原文 e\u0301','Recovered travel current / 恢复本次原文','Unknown original long term / 未知原文 e\u0301']
                            assert len(value['items'])==2 and value['message_count']==model.calls==3
                            assert dict(value['registered_operations']).get('model')==3
                            assert [[row['text'] for row in payload['items']] for payload in model.memory_inputs]==[[text] for text in expected]
                            assert [payload['items'][0]['version'] for payload in model.memory_inputs]==[1,3,1]
                            assert len(posts)==5 and all(event['status']==200 for event in posts)
                            assert sum(event['path']=='/v2/memories' for event in posts)==2
                            assert sum(event['path']=='/v2/memory-management-actions' for event in posts)==2
                            assert sum(event['path']=='/v2/memory-withdrawal-actions' for event in posts)==1
                            assert sum(event.get('actual_200_ack_lost',False) for event in posts)==2
                            assert len({event.get('operation_id',event.get('action_id')) for event in posts})==5
                            current=next(item for item in value['items'] if item['command']['context'] is not None)
                            assert current['status']=='withdrawn' and current['version']==4 and current['command']['text']==expected[1]
                            # The stopped original and approved input remain stored.
                            assert current['command']['source_id'] in {row['source_id'] for row in value['source_rows']}
                        elif reverse:
                            expected=['Original legacy read remains available / 保留旧只读回执','Typed unknown cannot downgrade / 新版未知不能回退写入','Fresh compatible typed action / 兼容入口新保存']
                            assert len(value['items'])==3 and value['message_count']==model.calls==0
                            assert {item['command']['text'] for item in value['items']}==set(expected)
                            posts=[event for event in audit if event['method']=='POST' and event['path'] in ('/v1/memories','/v2/memories')]
                            assert [event['path'] for event in posts]==['/v1/memories','/v2/memories','/v2/memories']
                            assert all(event['status']==200 for event in posts) and posts[1].get('actual_200_ack_lost')
                            assert sum(event['method']=='GET' and event['path']=='/v1/memory-receipts' and event['status']==200 for event in audit)>=2
                        elif conflict:
                            expected=['Conflict source / 并发原条目','Fresh after actual conflict / 明确冲突后新保存','Conflicting original edit / 冲突原文 e\u0301']
                            assert len(value['items'])==2 and value['message_count']==model.calls==0
                            assert len(posts)==3 and [event['status'] for event in posts]==[200,409,200]
                            assert posts[1]['producer_error']==dict(code='MEMORY_CONFLICT',outcome='failed')
                            assert len(fixture_actions)==1 and fixture_actions[0]['receipt']['status']=='disabled'
                            by_text={item['command']['text']:item for item in value['items']}
                            assert set(by_text)==set(expected[:2]) and by_text[expected[0]]['status']=='disabled' and by_text[expected[0]]['version']==2
                            assert by_text[expected[1]]['status']=='active' and by_text[expected[1]]['version']==1
                        elif legacy:
                            expected=['Legacy unresolved original / 旧版未知原文 e\u0301','Fresh typed save after legacy reconciliation / 核实后新保存','Duplicate active long-term / 保留原条目']
                            assert len(value['items'])==2 and value['message_count']==model.calls==0
                            by_text={item['command']['text']:item for item in value['items']}
                            assert set(by_text)==set(expected[:2]) and by_text[expected[0]]['command']['context'] is None
                            assert by_text[expected[1]]['command']['context']==dict(kind='travel',id=travels[0],expected_version=1)
                            posts=[event for event in audit if event['method']=='POST' and event['path'] in ('/v1/memories','/v2/memories')]
                            assert len(posts)==3 and [event['status'] for event in posts]==[200,200,503]
                            assert [event['path'] for event in posts]==['/v1/memories','/v2/memories','/v2/memories']
                            assert posts[0].get('actual_200_ack_lost') and not posts[1].get('actual_200_ack_lost')
                            assert posts[2]['producer_error']['outcome']=='unknown'
                            assert any(event['path']=='/v1/memory-receipts' and event['method']=='GET' and event['status']==200 for event in audit)
                        elif switching:
                            expected=['Account A delayed original / A迟到原文']
                            assert len(value['items'])==1 and value['message_count']==model.calls==0
                            assert len(posts)==1 and posts[0]['status']==200 and 'released_at' in posts[0]
                            assert posts[0]['released_at']-posts[0]['held_at']<10
                            assert any(event['method']=='GET' and event['path']=='/v2/memories' and event['account']=='B' and event['status']==200 for event in audit)
                        elif release:
                            expected=[]
                            assert value['items']==[] and value['message_count']==model.calls==0 and audit==[]
                        else:
                            assert value['role']==['cj_m1_runtime','cj_m1_runtime'] and len(value['items'])==(2 if chinese else 3) and not errors and iterations[0]>0
                            calls=1 if chinese else 6
                            assert value['message_count']==calls and model.calls==calls
                            assert dict(value['registered_operations']).get('model')==calls
                            expected=['中文本次偏好 / 安静房间 e\u0301'] if chinese else ['Travel A quiet room / 本次A安静房间',*['Travel A updated value / A当前新值']*3,
                                'Typed long-term tea / 新长期 e\u0301','Travel B separate value / B独立值']
                            assert len(model.memory_inputs)==len(expected)
                            for payload,text in zip(model.memory_inputs,expected):
                                assert payload['version']=='MEMORY-RUN-CONSUME@2' and [row['text'] for row in payload['items']]==[text]
                            # The frozen edit creates a NEW source at source_version=1;
                            # it increments the ITEM version, never the new source's version.
                            assert [payload['items'][0]['version'] for payload in model.memory_inputs]==([1] if chinese else [1,2,2,2,1,1])
                            assert [payload['items'][0]['source_version'] for payload in model.memory_inputs]==[1]*calls
                            if not chinese:
                                old_source=model.memory_inputs[0]['items'][0]['source_id'];new_source=model.memory_inputs[1]['items'][0]['source_id']
                                assert old_source!=new_source
                                assert all(payload['items'][0]['source_id']==new_source for payload in model.memory_inputs[1:4])
                                before={row['source_id']:row for row in report['consumption_proofs']['1']['source_rows']}
                                after={row['source_id']:row for row in value['source_rows']}
                                assert old_source in after and new_source in after and after[old_source]['approved_sha256']==before[old_source]['approved_sha256']
                            by_text={item['command']['text']:item for item in value['items']}
                            assert by_text['中文长期偏好 / 长期 e\u0301' if chinese else 'Typed long-term tea / 新长期 e\u0301']['command']['context'] is None
                            assert by_text['中文本次偏好 / 安静房间 e\u0301' if chinese else 'Travel A updated value / A当前新值']['command']['context']==dict(kind='travel',id=travels[0],expected_version=1)
                            if not chinese:assert by_text['Travel B separate value / B独立值']['command']['context']==dict(kind='travel',id=travels[1],expected_version=1)
                            posts=[event for event in audit if event['host']=='memory' and event['method']=='POST' and not event.get('fixture',False)]
                            assert len(posts)==(2 if chinese else 4) and all(event['status']==200 for event in posts)
                            assert sum(event['path']=='/v2/memories' for event in posts)==(2 if chinese else 3) and sum(event['path']=='/v2/memory-management-actions' for event in posts)==(0 if chinese else 1)
                        assert not any(event['method']=='POST' and event['path'].startswith('/v1/trip') for event in audit)
                        with TestClient(memory) as client:
                            for event in posts:
                                if event['path'] in ('/v1/memories','/v2/memories'):path=event['path'].replace('/memories','/memory-receipts');query={'operation_id':event['operation_id']}
                                else:path='/v2/memory-management-receipts';query={'action_id':event['action_id']}
                                if path.startswith('/v1/'):
                                    with TestClient(app) as old:receipt=old.get(path,params=query,headers=headers['A'])
                                else:receipt=client.get(path,params=query,headers=headers['A'])
                                receipt.raise_for_status()
                                if event['status']==200:assert receipt.json()['receipt']['input_sha256']==event['input_sha256']
                                else:
                                    assert receipt.json()['receipt'] is None
                                    assert conflict and event['producer_error']['outcome']=='failed' or legacy and event['producer_error']['outcome']=='unknown'
                                if path.startswith('/v1/'):
                                    with TestClient(app) as old:foreign=old.get(path,params=query,headers=headers['B'])
                                else:foreign=client.get(path,params=query,headers=headers['B'])
                                assert foreign.status_code==200 and foreign.json()['receipt'] is None
                            for item in value['items']:
                                foreign=client.get('/v2/memory-items',params={'item_id':item['command']['item_id']},headers=headers['B'])
                                assert foreign.status_code==200 and foreign.json()['item'] is None
                        container=native.scan(configuration) if tls else Path(subprocess.check_output(['xcrun','simctl','get_app_container',args.simulator,BUNDLE,'data'],text=True).strip())
                        for path in container.rglob('*'):
                            if path.is_file() and not path.is_symlink():
                                data=path.read_bytes()
                                assert not any(token.encode() in data for token in tokens.values()) and b'-----BEGIN PRIVATE KEY-----' not in data
                                assert not any(text.encode() in data for text in set(expected+[item['command']['text'] for item in value['items']]))
                        report.update(status='VERIFYING_CLEANUP',token_key_scan='PASS',plaintext_scan='PASS');save()
                    else:report.update(status='PREPARED_EXECUTION_UNRUN',token_key_scan='UNRUN: device App container',plaintext_scan='UNRUN: device App container');save()
                finally:
                    released.set();stop.set();worker_thread.join(10)
                    for server in servers:server.should_exit=True
                    for thread in threads:thread.join(10)
                    control.shutdown();control.server_close()
                    if tls:
                        try:
                            if native is not None:native.cleanup_input()
                        finally:(output/'project/M4ControlBootstrap.plist').unlink(missing_ok=True)
                        for path in output.rglob('*'):
                            if path.is_file() and not path.is_symlink():
                                assert not any(secret.encode() in path.read_bytes() for secret in [*tokens.values(),control_token]),'credential in evidence export'
                        report['artifact_token_scan']='PASS';save()
                    if worker_thread.is_alive() or any(thread.is_alive() for thread in threads):raise RuntimeError('local runtime failed to stop')
            report['private_pg_stopped']=True
            assert head==subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'head changed during acceptance'
            assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest for name,digest in report['source_hashes'].items()),'source changed during acceptance'
            if not args.prepare_only:
                report['status']='PARTIAL_PASS';report['cases'][args.case]='PASS'
            save()
    except BaseException as error:
        report.update(status='FAIL',error=type(error).__name__)
        if tls and 'device_tests' in report:report['cases'][args.case]='FAIL'
        raise
    finally:save()

if __name__=='__main__':main()
