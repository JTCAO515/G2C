"""Partial #228 native typed-root acceptance; never claims the complete frame 4.

Real signed loopback producers, fresh private PG, official explicit budget and
formal run_once/FakeProvider. No injected business rows, quota, HTTP refusal or
UI model. Evidence stays external and every failed run gets a new directory.
"""
import argparse,hashlib,importlib.util,json,os,plistlib,subprocess,sys,tempfile,threading,time,uuid
from datetime import datetime,timedelta,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs,urlparse

ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
BUNDLE='space.go2china.typed-memory.acceptance'

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulator',required=True);parser.add_argument('--run-context',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--build-dir',type=Path,required=True)
    args=parser.parse_args();output=args.output.resolve();build=args.build_dir.resolve()
    if output.is_relative_to(ROOT) or build.is_relative_to(ROOT):raise ValueError('external evidence required')
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT):raise ValueError('commit candidate first')
    os.umask(0o077);output.mkdir(parents=True,mode=0o700)
    if (output/'report.json').exists():raise ValueError('preserve old report')
    for key in tuple(os.environ):
        if key.startswith(('PG','LIBPQ','CJ_LOCAL_','SIMCTL_CHILD_','G2C_DEV_')) or key in ('DATABASE_URL','CJ_DATABASE_URL'):os.environ.pop(key)
    os.environ.update(CJ_ENV='local',DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer')
    sys.path.insert(0,str(ROOT/'scripts'))
    import psycopg,uvicorn,dev_auth,migrate
    from fastapi.testclient import TestClient
    from pg_suites import cluster
    from cj_api.local_app import (create_local_app,LocalDatabase,ISSUER,scope_for,load_confirmation_signer,load_history_configuration)
    from cj_api.local_run_context import load_run_context
    from cj_message.travel import ABI
    from cj_agent.provider import FakeProvider
    from cj_memory.typed_api import create_local_typed_app
    from cj_memory.typed_local import TypedConfiguration
    from cj_memory.typed_runtime import TypedRuntimeConfiguration
    from run_worker import run_once
    context=load_run_context(args.run_context)
    if context.version!='CJ-LOCAL-RUN@2':raise ValueError('explicit @2 required')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    sources=[*list((ROOT/'ios/App').glob('*.swift')),HERE/'DevelopmentTypedMemoryUITests.swift',Path(__file__)]
    for name in ('CJShell','CJMemoryClient','CJMessageClient','CJRunClient'):
        sources+=list((ROOT/'ios/Modules'/name/'Sources').rglob('*.swift'))
    report=dict(status='RUNNING',head=head,cases={},scope='partial typed App save/read plus actual same-conversation recall; NOT complete #228 frame4',
        source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        git_trees={name:subprocess.check_output(['git','rev-parse','HEAD:'+name],cwd=ROOT,text=True).strip() for name in ('ios','backend','contracts','scripts')},
        run_context=json.loads(args.run_context.read_text()),
        unrun=['new-chat/restart/other-travel actual recall','complete #228 frame4','Chinese/max font','lifecycle/unknown/interoperability matrix','real services/models/cloud/fees','physical device/VoiceOver'])
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
                app=create_local_app(conninfo_path=conn,auth_dir=auth,run_context=context,travel_context=True,
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
                slots={'preference':dict(kind='preference',collection_allowed=True,semantic_resolved=True)}
                profile=dict(subjects=['self'],slots=slots,extents=['long_term','current'],context_ids=[])
                collection=dict(version='local-memory-typed.1',collection=dict(version='local-memory-policy.1',
                    expires_at=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),profiles={subject:profile for subject in subjects.values()}),
                    travel_contexts={subjects['A']:travels,subjects['B']:[]})
                typed=TypedConfiguration.from_bytes(json.dumps(collection).encode())
                runtime=TypedRuntimeConfiguration.from_bytes(json.dumps(dict(version='local-memory-run.2',collection=collection,
                    selections={subject:dict(subject='self',slots=['preference'],max_bytes=2000) for subject in subjects.values()})).encode())
                memory=create_local_typed_app(conninfo_path=conn,auth_dir=auth,configuration=typed)
                database=LocalDatabase(conn,run_context=context,travel_context=True)
                audit=[];errors=[];iterations=[0];outcomes=[];stop=threading.Event()
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
                        event=dict(host=label,method=scope['method'],path=scope['path'],status=None);raw=bytearray()
                        with lock:audit.append(event)
                        async def received():
                            message=await receive()
                            if label=='memory' and scope['method']=='POST' and message['type']=='http.request':raw.extend(message.get('body',b''))
                            return message
                        async def sent(message):
                            if message['type']=='http.response.start':event['status']=message['status']
                            await send(message)
                        await application(scope,received,sent)
                        if raw:
                            event['input_sha256']=hashlib.sha256(raw).hexdigest()
                            if event['status']==200:event['operation_id']=json.loads(raw)['operation_id']
                    return invoke
                servers=[];threads=[]
                for application,label in ((app,'main'),(memory,'memory')):
                    server=uvicorn.Server(uvicorn.Config(observed(application,label),host='127.0.0.1',port=0,log_level='error'))
                    thread=threading.Thread(target=server.run,daemon=True);thread.start();servers.append(server);threads.append(thread)
                    deadline=time.monotonic()+20
                    while not server.started:
                        if not thread.is_alive() or time.monotonic()>deadline:raise RuntimeError('signed API startup')
                        time.sleep(.05)
                endpoints=['http://127.0.0.1:'+str(server.servers[0].sockets[0].getsockname()[1]) for server in servers]
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
                    result=dict(items=values,role=list(role),message_count=messages,model_calls=model.calls,formal_worker_iterations=iterations[0],
                        worker_errors=list(errors),requests=list(audit),outcomes=list(outcomes),memory_inputs=list(model.memory_inputs),registered_operations=registered)
                    report['proof']=result;save();return result
                class Control(BaseHTTPRequestHandler):
                    def log_message(self,*_):pass
                    def do_GET(self):
                        try:
                            parsed=urlparse(self.path)
                            if parsed.path=='/prepare':value=dict(endpoint=endpoints[0],memory_endpoint=endpoints[1],accounts=tokens,subjects=subjects,travel_ids=travels,
                                travel_profile=json.dumps(dict(version='app-travel.1',travel_ids=travels)),
                                memory_profile=json.dumps(dict(version='app-memory.2',subjects=['self'],slots=slots,extents=['long_term','current'])))
                            elif parsed.path=='/items':value={('long_term' if x['command']['context'] is None else 'travel'):x['command']['item_id'] for x in items()}
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
                control=ThreadingHTTPServer(('127.0.0.1',0),Control);threading.Thread(target=control.serve_forever,daemon=True).start()
                try:
                    spec=importlib.util.spec_from_file_location('typed_builder',ROOT/'scripts/check_ios_trip_confirm.py')
                    builder_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder_module)
                    builder=object.__new__(builder_module.XCTestDriver);builder.directory=output/'project';builder.directory.mkdir();builder.write_project(0)
                    (builder.directory/'G2CControl.swift').write_text((HERE/'DevelopmentTypedMemoryUITests.swift').read_text().replace('__FIXTURE_URL__',f'http://127.0.0.1:{control.server_port}'))
                    project=builder.directory/'G2CAcceptance.xcodeproj';pbx=project/'project.pbxproj'
                    text=pbx.read_text().replace('space.go2china.foundation.local',BUNDLE).replace('space.go2china.foundation.control',BUNDLE+'.control')
                    entitlements=builder.directory/'Typed.entitlements';entitlements.write_bytes(plistlib.dumps({'application-identifier':BUNDLE,'keychain-access-groups':[BUNDLE]}))
                    pbx.write_text(text.replace(json.dumps(str(ROOT/'ios/App/Development.entitlements')),json.dumps(str(entitlements))))
                    command=['xcodebuild','-project',str(project),'-scheme','G2CControl','-configuration','Debug',
                        '-destination','platform=iOS Simulator,id='+args.simulator,'-derivedDataPath',str(build),'-resultBundlePath',str(output/'english.xcresult'),
                        '-scmProvider','system','-skipPackageUpdates','-onlyUsePackageVersionsFromResolvedFile','-parallel-testing-enabled','NO','-collect-test-diagnostics','never',
                        'ARCHS=arm64','ONLY_ACTIVE_ARCH=YES','CODE_SIGNING_ALLOWED=YES','CODE_SIGN_IDENTITY=-',
                        '-only-testing:G2CControl/DevelopmentTypedMemoryUITests/testEnglishSaveReadAndOwnedTravel','test']
                    result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=1800)
                    log=result.stdout+result.stderr
                    for token in tokens.values():log=log.replace(token,'<redacted-local-token>')
                    (output/'english.log').write_text(log)
                    report['cases']['testEnglishSaveReadAndOwnedTravel']='PASS' if result.returncode==0 else 'FAIL'
                    value=proof();result.check_returncode()
                    summary=json.loads(subprocess.check_output(['xcrun','xcresulttool','get','test-results','summary','--path',str(output/'english.xcresult')]))
                    (output/'english-summary.json').write_text(json.dumps(summary,indent=2))
                    assert (summary['passedTests'],summary['failedTests'],summary['skippedTests'])==(1,0,0)
                    assert value['role']==['cj_m1_runtime','cj_m1_runtime'] and len(value['items'])==2 and not errors and iterations[0]>0
                    assert value['message_count']==2 and model.calls==2
                    assert dict(registered=value['registered_operations'])['registered'] and dict(value['registered_operations']).get('model')==2
                    assert len(model.memory_inputs)==2
                    assert all(payload['version']=='MEMORY-RUN-CONSUME@2' and [row['text'] for row in payload['items']]==['Travel A quiet room / 本次A安静房间'] for payload in model.memory_inputs)
                    by_text={item['command']['text']:item for item in value['items']}
                    assert by_text['Typed long-term tea / 新长期 e\u0301']['command']['context'] is None
                    assert by_text['Travel A quiet room / 本次A安静房间']['command']['context']==dict(kind='travel',id=travels[0],expected_version=1)
                    posts=[event for event in audit if event['host']=='memory' and event['method']=='POST']
                    assert len(posts)==2 and all(event['path']=='/v2/memories' and event['status']==200 for event in posts)
                    assert not any(event['method']=='POST' and event['path'].startswith('/v1/trip') for event in audit)
                    with TestClient(memory) as client:
                        for event in posts:
                            receipt=client.get('/v2/memory-receipts',params={'operation_id':event['operation_id']},headers=headers['A'])
                            receipt.raise_for_status();assert receipt.json()['receipt']['input_sha256']==event['input_sha256']
                        for item in value['items']:
                            foreign=client.get('/v2/memory-items',params={'item_id':item['command']['item_id']},headers=headers['B'])
                            assert foreign.status_code==200 and foreign.json()['item'] is None
                    container=Path(subprocess.check_output(['xcrun','simctl','get_app_container',args.simulator,BUNDLE,'data'],text=True).strip())
                    for path in container.rglob('*'):
                        if path.is_file() and not path.is_symlink():
                            data=path.read_bytes()
                            assert not any(token.encode() in data for token in tokens.values()) and b'-----BEGIN PRIVATE KEY-----' not in data
                            assert not any(text.encode() in data for text in ('Typed long-term tea / 新长期 e\u0301','Travel A quiet room / 本次A安静房间'))
                    report.update(status='PARTIAL_PASS',token_key_scan='PASS',plaintext_scan='PASS');save()
                finally:
                    stop.set();worker_thread.join(10)
                    for server in servers:server.should_exit=True
                    for thread in threads:thread.join(10)
                    control.shutdown();control.server_close()
                    if worker_thread.is_alive() or any(thread.is_alive() for thread in threads):raise RuntimeError('local runtime failed to stop')
            report['private_pg_stopped']=True;save()
    except BaseException as error:report.update(status='FAIL',error=type(error).__name__);raise
    finally:save()

if __name__=='__main__':main()
