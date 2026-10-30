"""#266 actual App/signed local API/private PG/formal registered PLACE consumer.

Only the frozen synthetic-v1 source and FakeProvider are used. Operator budget is
explicit and initialized once through the official local CLI; no quota/429 or
business response is injected. The stale case waits for real UTC time to elapse.
"""
import argparse,asyncio,hashlib,importlib.util,json,os,plistlib,subprocess,sys,tempfile,threading,time,uuid
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs,urlparse
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
BUNDLE='space.go2china.place.acceptance'
CASES=['testEnglish','testChineseLarge','testOutcomes','testUnknownReopen','testOverLimit','testCancel','testSwitchLate','testExpired','testReleaseClosed']
sys.path.insert(0,str(ROOT/'scripts'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--simulator',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--build-dir',type=Path,required=True);p.add_argument('--run-context',type=Path,required=True)
    p.add_argument('--case',choices=CASES);args=p.parse_args()
    output=args.output.resolve();build=args.build_dir.resolve()
    if output.is_relative_to(ROOT) or build.is_relative_to(ROOT):raise ValueError('external evidence required')
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT):raise ValueError('commit candidate first')
    os.umask(0o077)
    output.mkdir(parents=True,mode=0o700)
    output.chmod(0o700)
    if (output/'report.json').exists():raise ValueError('preserve prior report')
    env={k:v for k,v in os.environ.items() if not k.startswith(('PG','LIBPQ','SIMCTL_CHILD_','G2C_DEV_','CJ_LOCAL_'))}
    for key in tuple(os.environ):
        if key.startswith(('PG','LIBPQ','CJ_LOCAL_')):os.environ.pop(key)
    env.update(CJ_ENV='local',DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer');os.environ['CJ_ENV']='local'
    import psycopg,uvicorn,dev_auth,migrate
    from fastapi.testclient import TestClient
    from pg_suites import cluster
    from cj_api.local_app import app_from_environment,LocalDatabase,ISSUER,scope_for
    from cj_api.local_run_context import load_run_context
    from cj_api.local_tools import LocalTools,SyntheticToolModel
    from cj_run.core import Binding,Service as RunService
    from cj_message.domain import Service as MessageService
    from cj_run.step_usage import ledger_scope_for
    from cj_usage.codec import decode,encode
    from cj_usage.core import Meter
    from run_worker import run_once
    context=load_run_context(args.run_context)
    if context.version!='CJ-LOCAL-RUN@2' or context.current.meter.max_tools!=1:raise ValueError('explicit @2/max_tools=1 profile required')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    sources=[*list((ROOT/'ios/App').glob('*.swift')),*list((ROOT/'ios/Modules/CJTripClient/Sources').rglob('*.swift')),
        *list((ROOT/'ios/Modules/CJShell/Sources').rglob('*.swift')),*list((ROOT/'ios/Modules/CJRunClient/Sources').rglob('*.swift')),
        HERE/'DevelopmentPlaceUITests.swift',Path(__file__)]
    report=dict(status='RUNNING',head=head,cases={},required_cases=CASES,
        unrun=['real services/providers/models/cloud/fees','physical device/VoiceOver','map SDK/location alignment'],
        source_hashes={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
        git_trees={name:subprocess.check_output(['git','rev-parse',head+':'+name],cwd=ROOT,text=True).strip() for name in ('ios','backend','contracts','scripts')},
        run_context=json.loads(args.run_context.read_text()))
    if args.case:report['unrun'] += [case for case in CASES if case!=args.case]
    lock=threading.RLock()
    def save():
        with lock:(output/'report.json').write_text(json.dumps(report,indent=2))
    save()
    try:
        with tempfile.TemporaryDirectory(prefix='cj266-',dir='/tmp') as temporary:
            root=Path(temporary)
            with cluster('placeui',port=55786,role='cj266_initializer',root=root/'pg') as config:
                with psycopg.connect(**config,autocommit=True) as conn:
                    chain=migrate.load();migrate.up(conn,chain,chain[-1]['version'])
                connection=root/'connection.json';connection.write_text(json.dumps(config));connection.chmod(0o600)
                subjects={case:{key:'cj266-'+uuid.uuid4().hex for key in ('A','B')} for case in CASES}
                auth=root/'auth';dev_auth.init(auth,[s for row in subjects.values() for s in row.values()])
                tokens={case:{key:dev_auth.token(auth,subject,120) for key,subject in row.items()} for case,row in subjects.items()}
                for target in (env,os.environ):target.update(CJ_LOCAL_CONNINFO=str(connection),CJ_LOCAL_AUTH_DIR=str(auth),CJ_LOCAL_RUN_CONTEXT=str(args.run_context.resolve()))
                for row in subjects.values():
                    for subject in row.values():
                        subprocess.run([sys.executable,'-B',str(ROOT/'scripts/local_run_context.py'),'--conninfo-json',str(connection),
                            '--auth-dir',str(auth),'--run-context',str(args.run_context.resolve()),'--subject',subject,'init-budget'],
                            cwd=ROOT,env=env,check=True,capture_output=True)
                app=app_from_environment();database=LocalDatabase(connection,run_context=context)
                specs={};audit=[];worker_errors=[];active=[None];stop=threading.Event()
                class Model(SyntheticToolModel):
                    def stream(self,messages,system=None):
                        for chunk in super().stream(messages,system=system):
                            value=json.loads(chunk)
                            if active[0] and specs[active[0]]['mode']=='limit' and value['kind']=='tool':value['calls']*=2
                            encoded=json.dumps(value,ensure_ascii=False)
                            if active[0] and specs[active[0]]['mode']=='cancel' and messages[-1]['role']!='tool':
                                row=specs[active[0]]
                                yield encoded[:1]
                                row['entered'].set()
                                if not row['release'].wait(90):raise TimeoutError('test model stream gate')
                                yield encoded[1:]
                            else:yield encoded
                def worker():
                    try:
                        while not stop.is_set():
                            with lock:key=active[0]
                            if key:
                                row=specs[key]
                                outcomes=run_once(database,row['model'],auth,tools_configuration=row['tools'])
                                with lock:row['outcomes'] += [dict(message_id=x.message_id,run_id=x.run_id,status=x.status) for x in outcomes]
                            stop.wait(.05)
                    except BaseException as error:
                        worker_errors.append(type(error).__name__);stop.set()
                worker_thread=threading.Thread(target=worker,daemon=True);worker_thread.start()
                async def observed(scope,receive,send):
                    if scope['type']!='http':return await app(scope,receive,send)
                    with lock:key=active[0];row=specs.get(key)
                    event=dict(case=key,method=scope['method'],path=scope['path'])
                    with lock:audit.append(event)
                    async def capture(message):
                        if message['type']=='http.response.start':event['status']=message['status']
                        if (row and row['hold_read'] and scope['path']=='/v1/run-display' and message['type']=='http.response.body' and event.get('status')==200):
                            row['hold_read']=False;row['read_entered'].set()
                            await asyncio.to_thread(row['read_release'].wait,90)
                        await send(message)
                    await app(scope,receive,capture)
                server=uvicorn.Server(uvicorn.Config(observed,host='127.0.0.1',port=0,log_level='error'))
                thread=threading.Thread(target=server.run,daemon=True);thread.start()
                deadline=time.monotonic()+20
                while not server.started:
                    if time.monotonic()>deadline:raise TimeoutError('local API start')
                    time.sleep(.05)
                endpoint='http://127.0.0.1:'+str(server.servers[0].sockets[0].getsockname()[1])
                def prepare(case):
                    if case in specs:raise ValueError('case already prepared')
                    mode={'testOverLimit':'limit','testCancel':'cancel','testExpired':'stale'}.get(case,'normal')
                    row=dict(mode=mode,model=Model(),tools=LocalTools(),outcomes=[],audit_start=len(audit),
                        entered=threading.Event(),release=threading.Event(),read_entered=threading.Event(),read_release=threading.Event(),hold_read=False)
                    row['read_release'].set()
                    if mode=='stale':
                        count=[0]
                        def physical_clock():
                            count[0]+=1
                            if count[0]==3:
                                row['entered'].set();start=time.monotonic();stop.wait(62)
                                row['real_wait_seconds']=time.monotonic()-start
                            return datetime.now(timezone.utc)
                        row['tools'].place.clock=physical_clock
                    with TestClient(app) as client:
                        result=client.put('/v1/conversations',params={'conversation_id':case},headers={'Authorization':'Bearer '+tokens[case]['A']})
                        assert result.status_code==200
                    with lock:specs[case]=row;active[0]=case
                    return dict(case_id=case,endpoint=endpoint,accounts=tokens[case],subjects=subjects[case],conversation=case)
                def proof(case,settled=False):
                    row=specs[case];scope=scope_for(ISSUER,subjects[case]['A'])
                    deadline=time.monotonic()+20
                    while True:
                        with database.connect(scope) as conn:
                            pending=conn.execute('SELECT count(*) FROM cj_message_delivery WHERE NOT acknowledged').fetchone()[0]
                        if not settled or not pending or time.monotonic()>deadline:break
                        time.sleep(.05)
                    with database.connect(scope) as conn:
                        role=conn.execute('SELECT current_user').fetchone()[0]
                        originals=conn.execute('SELECT message_id,raw_input,run_id FROM cj_message_receipt WHERE conversation_id=%s ORDER BY sequence',(case,)).fetchall()
                        account=ledger_scope_for(scope,context.current.meter)
                        ledger=decode(conn.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()[0])
                        operations=conn.execute('SELECT o.operation_key,o.registration_id,o.kind,o.command_bytes,o.input_bytes FROM cj_run_metered_operation o JOIN cj_message_receipt m ON (m.scope,m.run_id)=(o.scope,o.run_id) WHERE m.conversation_id=%s ORDER BY m.sequence,o.operation_key',(case,)).fetchall()
                    fingerprints=[dict(message_id=mid,run_id=run,sha256=hashlib.sha256(bytes(raw)).hexdigest()) for mid,raw,run in originals]
                    status=None;text='';effects=[];stage='none'
                    if originals:
                        message=MessageService(database.message_repository(scope),new_run_id=lambda:None).query(originals[-1][0])
                        r=message.receipt
                        messages=MessageService(database.message_repository(scope),new_run_id=lambda:None)
                        state=RunService(database.run_repository(scope),valid=lambda binding:messages.query(binding.message_id) is not None).snapshot(Binding(scope,r.conversation_id,r.generation,r.message_id,r.run_id,r.sequence))
                        status=state.status;text=state.text;effects=list(state.effects);stage=state.budget_exhausted_stage
                    events=[e for e in audit[row['audit_start']:] if e['case']==case]
                    result=dict(runtime_role=role,pending=pending,status=status,text=text,message_id=originals[-1][0] if originals else None,
                        messages=len(originals),posts=sum(e['method']=='POST' and e['path']=='/v1/messages' for e in events),
                        cancellations=sum(e['method']=='POST' and e['path']=='/v1/run-cancellations' for e in events),
                        model_calls=row['model'].calls,place_calls=row['tools'].place.invocations,transport_calls=row['tools'].place.transport_calls,
                        budget_stage=stage,exposure=Meter.exposure(ledger),effects=effects,
                        originals_sha256=hashlib.sha256(json.dumps(fingerprints,sort_keys=True).encode()).hexdigest(),
                        registered_sha256=hashlib.sha256(b''.join(str(x[:3]).encode()+bytes(x[3])+bytes(x[4]) for x in operations)).hexdigest(),
                        ledger_sha256=hashlib.sha256(encode(ledger).encode()).hexdigest(),
                        forbidden_writes=sum(e['method'] not in ('GET','HEAD') and e['path'].startswith('/v1/trip') for e in events),
                        worker_errors=worker_errors,real_wait_seconds=row.get('real_wait_seconds',0))
                    assert role=='cj_m1_runtime' and not worker_errors and not result['forbidden_writes'] and not effects
                    if settled:assert not pending
                    report.setdefault('proofs',{})[case]=result;save();return result
                class Control(BaseHTTPRequestHandler):
                    def log_message(self,*_):pass
                    def do_GET(self):
                        try:
                            parsed=urlparse(self.path);query=parse_qs(parsed.query);case=query['case'][0]
                            if parsed.path=='/prepare':value=prepare(case)
                            elif parsed.path=='/proof':value=proof(case,query.get('settled')==['1'])
                            elif parsed.path=='/phase':value=dict(stale_finished='real_wait_seconds' in specs[case])
                            elif parsed.path=='/wait-source':
                                assert specs[case]['entered'].wait(20);value={}
                            elif parsed.path=='/release-source':specs[case]['release'].set();value={}
                            elif parsed.path=='/hold-read':
                                specs[case]['read_release'].clear();specs[case]['read_entered'].clear();specs[case]['hold_read']=True;value={}
                            elif parsed.path=='/wait-read':assert specs[case]['read_entered'].wait(20);value={}
                            elif parsed.path=='/release-read':specs[case]['read_release'].set();value={}
                            else:raise ValueError('unknown test control')
                            raw=json.dumps(value).encode();self.send_response(200);self.end_headers();self.wfile.write(raw)
                        except Exception as error:
                            report.setdefault('control_errors',[]).append(type(error).__name__);save()
                            self.send_response(500);self.end_headers();self.wfile.write(type(error).__name__.encode())
                control=ThreadingHTTPServer(('127.0.0.1',0),Control);threading.Thread(target=control.serve_forever,daemon=True).start()
                try:
                    spec=importlib.util.spec_from_file_location('place_builder',ROOT/'scripts/check_ios_trip_confirm.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                    builder=object.__new__(module.XCTestDriver);builder.directory=output/'project';builder.directory.mkdir();builder.write_project(0)
                    (builder.directory/'G2CControl.swift').write_text((HERE/'DevelopmentPlaceUITests.swift').read_text().replace('__FIXTURE_URL__',f'http://127.0.0.1:{control.server_port}'))
                    project=builder.directory/'G2CAcceptance.xcodeproj';pbx=project/'project.pbxproj'
                    text=pbx.read_text().replace('space.go2china.foundation.local',BUNDLE).replace('space.go2china.foundation.control',BUNDLE+'.control')
                    entitlements=builder.directory/'Place.entitlements';entitlements.write_bytes(plistlib.dumps({'application-identifier':BUNDLE,'keychain-access-groups':[BUNDLE]}))
                    text=text.replace(json.dumps(str(ROOT/'ios/App/Development.entitlements')),json.dumps(str(entitlements)))
                    line=next(x for x in text.splitlines() if x.startswith('A00000000000000000000004 = {isa = XCBuildConfiguration; name = Debug;'))
                    text=text.replace(line,line+'\n'+line.replace('A00000000000000000000004','A0000000000000000000000C',1).replace('name = Debug;','name = Release;',1)).replace('buildConfigurations = (A00000000000000000000004);','buildConfigurations = (A00000000000000000000004, A0000000000000000000000C);');pbx.write_text(text)
                    for case in ([args.case] if args.case else CASES):
                        result=output/(case+'.xcresult')
                        command=['xcodebuild','-project',str(project),'-scheme','G2CControl','-configuration','Release' if case=='testReleaseClosed' else 'Debug',
                            '-destination','platform=iOS Simulator,id='+args.simulator,'-derivedDataPath',str(build),'-resultBundlePath',str(result),
                            '-scmProvider','system','-skipPackageUpdates','-onlyUsePackageVersionsFromResolvedFile','-parallel-testing-enabled','NO','-collect-test-diagnostics','never',
                            'ARCHS=arm64','ONLY_ACTIVE_ARCH=YES','CODE_SIGNING_ALLOWED=YES','CODE_SIGN_IDENTITY=-','-only-testing:G2CControl/DevelopmentPlaceUITests/'+case,'test']
                        print('PLACE '+case,flush=True);run=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=1800)
                        log=run.stdout+run.stderr
                        for pair in tokens.values():
                            for token in pair.values():log=log.replace(token,'<redacted-local-token>')
                        (output/(case+'.log')).write_text(log)
                        if run.returncode:
                            report['cases'][case]='FAIL'
                            try:report.setdefault('failure_proofs',{})[case]=proof(case,settled=False)
                            except Exception as error:report.setdefault('failure_proof_errors',{})[case]=type(error).__name__
                            save()
                        run.check_returncode()
                        summary=json.loads(subprocess.check_output(['xcrun','xcresulttool','get','test-results','summary','--path',str(result)],env=env))
                        (output/(case+'-summary.json')).write_text(json.dumps(summary,indent=2))
                        assert summary['passedTests']==1 and summary['failedTests']==0 and summary['skippedTests']==0
                        report['cases'][case]='PASS';save()
                    with TestClient(app) as client:
                        for case,row in specs.items():
                            current=proof(case,settled=True)
                            if not current['message_id']:continue
                            foreign=client.get('/v1/run-display',params={'message_id':current['message_id']},headers={'Authorization':'Bearer '+tokens[case]['B']})
                            assert foreign.status_code==503 and 'snapshot' not in foreign.json()
                    container=Path(subprocess.check_output(['xcrun','simctl','get_app_container',args.simulator,BUNDLE,'data'],env=env,text=True).strip())
                    private_tokens=[token.encode() for pair in tokens.values() for token in pair.values()]
                    plaintext=[value.encode() for value in ('Find synthetic hotel / \u67e5\u8be2\u5408\u6210\u9152\u5e97 e\u0301','SYNTH_MISSING','SYNTH_BAD_JSON','SYNTH_TIMEOUT','SYNTH_DOUBLE_TOOL')]
                    for path in container.rglob('*'):
                        if path.is_file() and not path.is_symlink():
                            data=path.read_bytes();assert not any(token in data for token in private_tokens) and b'-----BEGIN PRIVATE KEY-----' not in data
                            assert not any(value in data for value in plaintext),'plaintext original input in App files'
                    report['token_key_scan']='PASS';report['plaintext_scan']='PASS';report['status']='PASS' if not args.case else 'PARTIAL_PASS';save()
                finally:
                    for row in specs.values():row['release'].set();row['read_release'].set()
                    stop.set();worker_thread.join(10);server.should_exit=True;thread.join(10);control.shutdown();control.server_close()
            report['private_pg_stopped']=True;save()
    except BaseException as error:report['status']='FAIL';report['error']=type(error).__name__;raise
    finally:save()

if __name__=='__main__':main()
