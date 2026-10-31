"""#21 independent send.3 App acceptance; no formal Trip source is fabricated.

Actual signed API/private PG/unchanged run_once/FakeProvider. These cases prove
unbound clarification and genuine MEMORY upgrade refusal only. Bound Trip/day/
item, timeline, maps, real providers and devices remain explicitly UNRUN.
"""
import argparse,hashlib,importlib.util,json,os,plistlib,subprocess,sys,tempfile,threading,time,traceback,uuid
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs,urlparse

ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
BUNDLE='space.go2china.discussions.acceptance'
CASES=['testUnboundEnglish','testUnboundChineseLarge','testMemoryUpgradeRefused','testNewChatEnglish','testNewChatChineseLarge','testNewChatUnknownReopen','testDiscussionUnknownReopen','testDiscussionCancel']
sys.path.insert(0,str(ROOT/'scripts'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulator',required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--build-dir',type=Path,required=True);parser.add_argument('--run-context',type=Path,required=True)
    parser.add_argument('--case',choices=CASES);args=parser.parse_args()
    output=args.output.resolve();build=args.build_dir.resolve()
    if output.is_relative_to(ROOT) or build.is_relative_to(ROOT):raise ValueError('external evidence required')
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT):raise ValueError('commit candidate first')
    os.umask(0o077);output.mkdir(parents=True,mode=0o700)
    if (output/'report.json').exists():raise ValueError('preserve original report')
    env={k:v for k,v in os.environ.items() if not k.startswith(('PG','LIBPQ','SIMCTL_CHILD_','G2C_DEV_','CJ_LOCAL_'))}
    for key in tuple(os.environ):
        if key.startswith(('PG','LIBPQ','CJ_LOCAL_')):os.environ.pop(key)
    env.update(CJ_ENV='local',DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer');os.environ['CJ_ENV']='local'
    import psycopg,uvicorn,dev_auth,migrate,message_trip_profile
    from fastapi.testclient import TestClient
    from pg_suites import cluster
    from cj_api.local_app import app_from_environment,LocalDatabase,ISSUER,scope_for
    from cj_api.local_run_context import load_run_context
    from cj_agent.provider import FakeProvider
    from run_worker import run_once
    context=load_run_context(args.run_context)
    if context.version!='CJ-LOCAL-RUN@2':raise ValueError('explicit registered @2 required')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    sources=[*list((ROOT/'ios/App').glob('*.swift')),HERE/'DevelopmentTripDiscussionUITests.swift',Path(__file__)]
    for name in ('CJShell','CJMessageClient','CJRunClient','CJTripClient'):
        sources+=list((ROOT/'ios/Modules'/name/'Sources').rglob('*.swift'))
    report=dict(status='RUNNING',head=head,cases={},unrun=['bound formal Trip/day/item and current structured source','timeline/maps/provider point alignment','real accounts/models/services/fees/cloud','physical device/VoiceOver'],
        source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},run_context=json.loads(args.run_context.read_text()))
    lock=threading.RLock()
    def save():(output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    save()
    try:
        with tempfile.TemporaryDirectory(prefix='cj21-discussion-',dir='/tmp') as temporary:
            root=Path(temporary)
            with cluster('tripdiscussionui',port=55823,role='cj21_discussion_initializer',root=root/'pg') as config:
                with psycopg.connect(**config,autocommit=True) as conn:
                    chain=migrate.load();migrate.up(conn,chain,chain[-1]['version'])
                connection=root/'connection.json';connection.write_text(json.dumps(config));connection.chmod(0o600)
                subjects={case:{key:'cj21-'+uuid.uuid4().hex for key in ('A','B')} for case in CASES}
                auth=root/'auth';dev_auth.init(auth,[s for row in subjects.values() for s in row.values()])
                tokens={case:{key:dev_auth.token(auth,subject,120) for key,subject in row.items()} for case,row in subjects.items()}
                memory_subject=subjects['testMemoryUpgradeRefused']['A']
                policy=dict(version='local-memory-policy.1',expires_at=datetime.fromtimestamp(context.current.meter.period_end,timezone.utc).isoformat(),
                    profiles={memory_subject:dict(subjects=['self'],slots={'fact':dict(kind='fact',collection_allowed=True,semantic_resolved=True)},extents=['long_term'],context_ids=[])})
                policy_path=root/'policy.json';policy_path.write_text(json.dumps(policy));policy_path.chmod(0o600)
                for target in (os.environ,env):target.update(CJ_LOCAL_CONNINFO=str(connection),CJ_LOCAL_AUTH_DIR=str(auth),CJ_LOCAL_RUN_CONTEXT=str(args.run_context.resolve()),CJ_LOCAL_MEMORY_POLICY=str(policy_path))
                def operator(subject,*command):
                    subprocess.run([sys.executable,'-B',str(ROOT/'scripts/local_run_context.py'),'--conninfo-json',str(connection),'--auth-dir',str(auth),
                        '--run-context',str(args.run_context.resolve()),'--subject',subject,*command],cwd=ROOT,env=env,check=True,capture_output=True)
                for row in subjects.values():
                    for subject in row.values():operator(subject,'init-budget')
                original_app=app_from_environment()
                with TestClient(original_app) as client:
                    for case,row in subjects.items():
                        if case.startswith('testNewChat'):continue # the actual App must create these chats
                        for key in row:
                            response=client.put('/v1/conversations',params={'conversation_id':case},headers={'Authorization':'Bearer '+tokens[case][key]});assert response.status_code==200
                    memory_command=dict(operation_id='synthetic-memory',item_id='synthetic-retained-memory',subject='self',slot='fact',kind='fact',
                        text='SYNTHETIC retained memory; do not disable',occurred_at='SYNTHETIC date unknown',extent='long_term',context_id=None)
                    result=client.post('/v1/memories',content=json.dumps(memory_command).encode(),headers={'Authorization':'Bearer '+tokens['testMemoryUpgradeRefused']['A'],'Content-Type':'application/octet-stream'})
                    assert result.status_code==200
                refused=False
                for case,row in subjects.items():
                    for key,subject in row.items():
                        if subject==memory_subject:
                            try:dev_auth.activate_travel(connection,subject,context,'MESSAGE-TRAVEL-CONSUMER@1')
                            except ValueError as error:
                                assert str(error)=='typed memory consumer is not installed';refused=True
                            else:raise AssertionError('existing MEMORY was silently upgraded')
                        else:
                            assert dev_auth.activate_travel(connection,subject,context,'MESSAGE-TRAVEL-CONSUMER@1')=='activated'
                            assert message_trip_profile.activate(connection,subject,context,'MESSAGE-TRIP-CONSUMER@1')=='activated'
                assert refused
                for target in (os.environ,env):target.update(CJ_LOCAL_TRAVEL_CONTEXT='message-travel.1',CJ_LOCAL_TRIP_CONTEXT='message-trip.1')
                app=app_from_environment();database=LocalDatabase(connection,run_context=context,travel_context=True,trip_context=True)
                class HeldFake(FakeProvider):
                    def __init__(self):super().__init__();self.entered=threading.Event();self.release=threading.Event()
                    def stream(self,messages,system=None):
                        for index,chunk in enumerate(super().stream(messages,system)):
                            if index==0:
                                self.entered.set()
                                if not self.release.wait(90):raise TimeoutError('actual FakeProvider release')
                            yield chunk
                models={case:HeldFake() if case=='testDiscussionCancel' else FakeProvider() for case in CASES};outcomes={case:[] for case in CASES};active=[None];audit=[];worker_errors=[];stop=threading.Event()
                conversations={case:case for case in CASES};lost_responses=set()
                async def observed(scope,receive,send):
                    if scope['type']!='http':return await app(scope,receive,send)
                    authorization=dict(scope['headers']).get(b'authorization',b'').decode()
                    case=next((case for case,row in tokens.items() if any(authorization=='Bearer '+value for value in row.values())),None)
                    event=dict(case=case,method=scope['method'],path=scope['path']);audit.append(event);body=bytearray()
                    if scope['path']=='/v3/message-send-status':
                        event['query']={key:value for key,value in parse_qs(scope['query_string'].decode('ascii')).items() if key in ('conversation_id','message_id')}
                    if case and scope['method']=='PUT' and scope['path']=='/v1/conversations':
                        query=parse_qs(scope['query_string'].decode('ascii'));assert set(query)=={'conversation_id'} and len(query['conversation_id'])==1
                        cid=query['conversation_id'][0];assert cid.startswith('discussion.') and str(uuid.UUID(cid.removeprefix('discussion.'))).upper()==cid.removeprefix('discussion.')
                        event['conversation_id']=cid;conversations[case]=cid
                    async def inspected():
                        value=await receive()
                        if value['type']=='http.request':body.extend(value.get('body',b''))
                        if value['type']=='http.request' and not value.get('more_body',False) and scope['path']=='/v3/messages':event['input_sha256']=hashlib.sha256(body).hexdigest()
                        if value['type']=='http.request' and not value.get('more_body',False) and scope['path']=='/v3/run-cancellations':
                            command=json.loads(body);assert set(command)=={'version','message_id'} and command['version']=='RUN-cancel.3'
                            event.update(message_id=command['message_id'],input_sha256=hashlib.sha256(body).hexdigest())
                        return value
                    async def captured(value):
                        if value['type']=='http.response.start':event['status']=value['status']
                        opening_loss=case=='testNewChatUnknownReopen' and event['method']=='PUT' and event['path']=='/v1/conversations'
                        message_loss=case=='testDiscussionUnknownReopen' and event['method']=='POST' and event['path']=='/v3/messages'
                        if (opening_loss or message_loss) and value['type']=='http.response.body' and event.get('status')==200 and case not in lost_responses:
                            # Middleware can split JSON into a data chunk plus an
                            # empty terminal chunk. Withhold the FIRST body chunk:
                            # dropping only the terminator loses no JSON bytes.
                            lost_responses.add(case);event['ack_lost_after_200']=True
                            event['withheld_body_bytes']=len(value.get('body',b''))
                            raise ConnectionResetError('local transport ACK loss after actual successful chat commit')
                        await send(value)
                    await app(scope,inspected,captured)
                server=uvicorn.Server(uvicorn.Config(observed,host='127.0.0.1',port=0,log_level='critical'))
                thread=threading.Thread(target=server.run,daemon=True);thread.start();deadline=time.monotonic()+20
                while not server.started:
                    if time.monotonic()>deadline:raise TimeoutError('local API startup')
                    time.sleep(.05)
                endpoint='http://127.0.0.1:'+str(server.servers[0].sockets[0].getsockname()[1])
                def worker():
                    try:
                        while not stop.is_set():
                            with lock:case=active[0]
                            if case:
                                result=run_once(database,models[case],auth)
                                with lock:outcomes[case]+=[dict(message_id=x.message_id,status=x.status) for x in result]
                            stop.wait(.05)
                    except BaseException as error:worker_errors.append(type(error).__name__)
                worker_thread=threading.Thread(target=worker,daemon=True);worker_thread.start()
                def proof(case):
                    scope=scope_for(ISSUER,subjects[case]['A'])
                    cid=conversations[case]
                    with database.connect(scope) as conn:
                        role=conn.execute('SELECT current_user').fetchone()[0]
                        rows=conn.execute('SELECT message_id,raw_input,run_id FROM cj_message_receipt WHERE conversation_id=%s ORDER BY sequence',(cid,)).fetchall()
                        chats=conn.execute('SELECT conversation_id,generation,last_sequence FROM cj_message_chat WHERE active').fetchall()
                        pending=conn.execute('SELECT count(*) FROM cj_message_delivery WHERE NOT acknowledged').fetchone()[0]
                        memory=conn.execute('SELECT item_id,version FROM cj_memory_item').fetchall()
                        profile=conn.execute('SELECT version FROM cj_message_trip_profile WHERE scope=%s',(scope,)).fetchone()
                        operations=conn.execute('SELECT o.operation_key,o.registration_id FROM cj_run_metered_operation o JOIN cj_message_receipt m ON (m.scope,m.run_id)=(o.scope,o.run_id) WHERE m.conversation_id=%s',(cid,)).fetchall()
                    report.setdefault('observations',{})[case]=dict(runtime_role=role,pending=pending,messages=len(rows),memory_items=len(memory),trip_profile=profile[0] if profile else None,model_calls=models[case].calls,registered_operations=len(operations))
                    report['observed_requests']=list(audit);report['worker_outcomes']=dict(outcomes);save()
                    status=None;text='';reference=None
                    if rows:
                        raw=bytes(rows[-1][1]);value=json.loads(raw)
                        assert value['version']=='MESSAGE-send.3' and value['creation_intent']=='none' and value['trip_context'] is None and value['needs_reference'] is None
                        with TestClient(app) as client:
                            response=client.get('/v3/run-display',params={'message_id':rows[-1][0]},headers={'Authorization':'Bearer '+tokens[case]['A']})
                            report['observations'][case]['run_display_status']=response.status_code
                            if response.status_code!=200:report['observations'][case]['run_display_error']=response.json().get('error')
                            save();assert response.status_code==200
                            snapshot=response.json();status=snapshot['snapshot']['status'];text=snapshot['snapshot']['text'];reference=snapshot['reference']
                            assert reference['context_kind']=='none' and reference['trip_context'] is None and reference['content_sha256'] is None
                    if case=='testMemoryUpgradeRefused':
                        assert len(memory)==1 and memory[0][0]=='synthetic-retained-memory' and profile is None
                        with TestClient(original_app) as client:
                            item=client.get('/v1/memory-items',params={'item_id':'synthetic-retained-memory'},headers={'Authorization':'Bearer '+tokens[case]['A']});assert item.status_code==200
                            assert item.json()['item']['command']['text']==memory_command['text']
                    else:assert not memory and profile==('message-trip.1',)
                    events=[x for x in audit if x['case']==case];posts=[x for x in events if x['method']=='POST' and x['path']=='/v3/messages']
                    openings=[x for x in events if x['method']=='PUT' and x['path']=='/v1/conversations']
                    cancellations=[x for x in events if x['method']=='POST' and x['path']=='/v3/run-cancellations']
                    forbidden=[x for x in events if x['method'] not in ('GET','HEAD') and not (x['method']=='POST' and x['path']=='/v3/messages') and not (case.startswith('testNewChat') and x['method']=='PUT' and x['path']=='/v1/conversations') and not (case=='testDiscussionCancel' and x['method']=='POST' and x['path']=='/v3/run-cancellations')]
                    if case.startswith('testNewChat'):
                        assert len(chats)<=1 and all(chat[0]==cid for chat in chats)
                        assert len(openings)<=1 and all(event.get('status')==200 for event in openings)
                    hashes=[hashlib.sha256(bytes(row[1])).hexdigest() for row in rows]
                    if rows:assert [x['input_sha256'] for x in posts]==hashes
                    if cancellations:assert len(rows)==1 and all(event['message_id']==rows[0][0] and event.get('status')==200 for event in cancellations)
                    value=dict(runtime_role=role,pending=pending,status=status,text=text,reference=reference,messages=len(rows),posts=len(posts),model_calls=models[case].calls,
                        memory_items=len(memory),trip_profile=profile[0] if profile else None,upgrade_refused=case=='testMemoryUpgradeRefused',
                        forbidden_writes=len(forbidden),registered_operations=len(operations),input_hashes=hashes,post_statuses=[event['status'] for event in posts],worker_errors=worker_errors,
                        conversation_id=cid,chat_count=len(chats),opening_requests=len(openings),opening_ack_losses=sum(bool(event.get('ack_lost_after_200')) for event in openings),
                        message_id=rows[-1][0] if rows else None,message_ack_losses=sum(bool(event.get('ack_lost_after_200')) for event in posts),cancellations=len(cancellations))
                    report.setdefault('proofs',{})[case]=value;save();return value
                class Control(BaseHTTPRequestHandler):
                    def log_message(self,*_):pass
                    def do_GET(self):
                        try:
                            path=urlparse(self.path);case=parse_qs(path.query)['case'][0]
                            if path.path=='/prepare':
                                with lock:active[0]=case
                                value=dict(case_id=case,endpoint=endpoint,accounts=tokens[case],subjects=subjects[case],conversation=case)
                            elif path.path in ('/proof','/wait-completed','/wait-settled'):
                                deadline=time.monotonic()+30
                                expected='cancelled' if path.path=='/wait-settled' and case=='testDiscussionCancel' else 'completed'
                                while True:
                                    if path.path in ('/wait-completed','/wait-settled'):
                                        # A real receipt can precede RUN creation. Wait
                                        # for unchanged run_once to return its actual
                                        # terminal outcome before the strict 200 proof.
                                        with lock:finished=list(outcomes[case])
                                        if worker_errors:raise RuntimeError('formal worker failed')
                                        if not finished:
                                            if time.monotonic()>deadline:raise TimeoutError('formal worker outcome')
                                            time.sleep(.05);continue
                                        if any(value['status']!=expected for value in finished):raise RuntimeError('formal RUN unexpected terminal status')
                                    value=proof(case)
                                    if path.path=='/proof' or value['status']==expected and value['pending']==0:break
                                    if value['worker_errors'] or time.monotonic()>deadline:raise TimeoutError('original RUN completion')
                                    time.sleep(.05)
                            elif path.path=='/wait-provider':assert case=='testDiscussionCancel' and models[case].entered.wait(30);value={}
                            elif path.path=='/release-provider':assert case=='testDiscussionCancel';models[case].release.set();value={}
                            else:raise ValueError('unknown control')
                            raw=json.dumps(value).encode();self.send_response(200);self.end_headers();self.wfile.write(raw)
                        except Exception as error:
                            report.setdefault('control_errors',[]).append(dict(type=type(error).__name__,frames=[dict(file=Path(f.filename).name,line=f.lineno,function=f.name) for f in traceback.extract_tb(error.__traceback__)]));save();self.send_response(500);self.end_headers();self.wfile.write(type(error).__name__.encode())
                control=ThreadingHTTPServer(('127.0.0.1',0),Control);threading.Thread(target=control.serve_forever,daemon=True).start()
                try:
                    spec=importlib.util.spec_from_file_location('discussion_builder',ROOT/'scripts/check_ios_trip_confirm.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                    builder=object.__new__(module.XCTestDriver);builder.directory=output/'project';builder.directory.mkdir();builder.write_project(0)
                    (builder.directory/'G2CControl.swift').write_text((HERE/'DevelopmentTripDiscussionUITests.swift').read_text().replace('__FIXTURE_URL__',f'http://127.0.0.1:{control.server_port}'))
                    project=builder.directory/'G2CAcceptance.xcodeproj';pbx=project/'project.pbxproj'
                    text=pbx.read_text().replace('space.go2china.foundation.local',BUNDLE).replace('space.go2china.foundation.control',BUNDLE+'.control')
                    entitlements=builder.directory/'Discussion.entitlements';entitlements.write_bytes(plistlib.dumps({'application-identifier':BUNDLE,'keychain-access-groups':[BUNDLE]}))
                    pbx.write_text(text.replace(json.dumps(str(ROOT/'ios/App/Development.entitlements')),json.dumps(str(entitlements))))
                    for case in ([args.case] if args.case else CASES):
                        result=output/(case+'.xcresult')
                        command=['xcodebuild','-project',str(project),'-scheme','G2CControl','-configuration','Debug','-destination','platform=iOS Simulator,id='+args.simulator,
                            '-derivedDataPath',str(build),'-resultBundlePath',str(result),'-scmProvider','system','-skipPackageUpdates','-onlyUsePackageVersionsFromResolvedFile',
                            '-parallel-testing-enabled','NO','-collect-test-diagnostics','never','ARCHS=arm64','ONLY_ACTIVE_ARCH=YES','CODE_SIGNING_ALLOWED=YES','CODE_SIGN_IDENTITY=-',
                            '-only-testing:G2CControl/DevelopmentTripDiscussionUITests/'+case,'test']
                        print('DISCUSSION '+case,flush=True);run=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=1800)
                        log=run.stdout+run.stderr
                        for row in tokens.values():
                            for token in row.values():log=log.replace(token,'<redacted-local-token>')
                        (output/(case+'.log')).write_text(log)
                        report['cases'][case]='FAIL' if run.returncode else 'VERIFYING';save()
                        if run.returncode:
                            try:report.setdefault('failure_proofs',{})[case]=proof(case)
                            except Exception as error:report.setdefault('failure_proof_errors',{})[case]=dict(type=type(error).__name__,frames=[dict(file=Path(f.filename).name,line=f.lineno,function=f.name) for f in traceback.extract_tb(error.__traceback__)])
                            save()
                        run.check_returncode()
                        summary=json.loads(subprocess.check_output(['xcrun','xcresulttool','get','test-results','summary','--path',str(result)],env=env))
                        (output/(case+'-summary.json')).write_text(json.dumps(summary,indent=2));assert summary['passedTests']==1 and summary['failedTests']==0 and summary['skippedTests']==0
                        verified=proof(case);assert verified['forbidden_writes']==0 and not worker_errors
                        if case=='testMemoryUpgradeRefused':
                            assert verified['messages']==verified['model_calls']==verified['registered_operations']==0 and verified['memory_items']==1
                            assert verified['posts']==1 and verified['post_statuses']==[503]
                        else:assert verified['messages']==verified['posts']==verified['model_calls']==verified['registered_operations']==1
                        if case.startswith('testNewChat'):
                            assert verified['chat_count']==verified['opening_requests']==1
                            assert verified['opening_ack_losses']==(1 if case=='testNewChatUnknownReopen' else 0)
                        if case=='testDiscussionUnknownReopen':assert verified['message_ack_losses']==1 and verified['messages']==verified['posts']==1
                        if case=='testDiscussionCancel':assert verified['status']=='cancelled' and verified['cancellations']==1
                        report['cases'][case]='PASS';save()
                    container=Path(subprocess.check_output(['xcrun','simctl','get_app_container',args.simulator,BUNDLE,'data'],env=env,text=True).strip())
                    private_tokens=[token.encode() for row in tokens.values() for token in row.values()]
                    for path in container.rglob('*'):
                        if path.is_file() and not path.is_symlink():
                            data=path.read_bytes()
                            assert not any(token in data for token in private_tokens) and b'-----BEGIN PRIVATE KEY-----' not in data
                    report['token_key_scan']='PASS'
                    report['status']='PARTIAL_PASS';save()
                finally:
                    models['testDiscussionCancel'].release.set()
                    stop.set();worker_thread.join(10);server.should_exit=True;thread.join(10);control.shutdown();control.server_close()
            report['private_pg_stopped']=True;save()
    except BaseException as error:
        for case,state in report['cases'].items():
            if state=='VERIFYING':report['cases'][case]='FAIL'
        report['status']='FAIL';report['error']=type(error).__name__;raise
    finally:save()


if __name__=='__main__':main()
