"""#320 actual App + signed local API/private PG/formal NEEDS worker.

Synthetic data and FakeProvider only. Manual requests use the canonical API;
quota and business failures are never injected. ACK-loss/cancel gates hold or
close a real successful response only after the backend committed it.
"""
import argparse,asyncio,hashlib,importlib.util,json,os,plistlib,subprocess,sys,tempfile,threading,time,uuid
from datetime import datetime,timezone
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs,urlparse
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
BUNDLE='space.go2china.needs.acceptance'
CASES=['testEnglish','testChineseLarge','testClarifications','testConflictReplay','testUnknownReopen','testCancelWaiting','testOwnerLate','testDeviceTimezones','testReleaseClosed']
sys.path.insert(0,str(ROOT/'scripts'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--simulator',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--build-dir',type=Path,required=True);p.add_argument('--run-context',type=Path,required=True)
    p.add_argument('--case',choices=CASES);args=p.parse_args()
    output=args.output.resolve();build=args.build_dir.resolve()
    if output.is_relative_to(ROOT) or build.is_relative_to(ROOT):raise ValueError('external evidence required')
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT):raise ValueError('commit candidate first')
    os.umask(0o077);output.mkdir(parents=True,mode=0o700);output.chmod(0o700)
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
    from cj_api.local_needs_preview import LocalNeedsPreview,SyntheticNeedsModel
    from cj_needs.preview import preview as encode_preview,synthetic_extract
    from cj_run.core import Binding,Service as RunService
    from cj_message.domain import Service as MessageService
    from cj_run.step_usage import ledger_scope_for
    from cj_usage.codec import decode,encode
    from cj_usage.core import Meter
    from run_worker import run_once
    context=load_run_context(args.run_context)
    if context.version!='CJ-LOCAL-RUN@2':raise ValueError('explicit registered @2 profile required')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    sources=[*list((ROOT/'ios/App').glob('*.swift')),*list((ROOT/'ios/Modules/CJNeedsClient/Sources').rglob('*.swift')),
        *list((ROOT/'ios/Modules/CJShell/Sources').rglob('*.swift')),*list((ROOT/'ios/Modules/CJMessageClient/Sources').rglob('*.swift')),
        HERE/'DevelopmentNeedsUITests.swift',Path(__file__)]
    report=dict(status='RUNNING',head=head,cases={},required_cases=CASES,
        unrun=['real accounts/models/services/cloud/fees','physical device/VoiceOver','real-model extraction quality'],
        source_hashes={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
        git_trees={name:subprocess.check_output(['git','rev-parse',head+':'+name],cwd=ROOT,text=True).strip() for name in ('ios','backend','contracts','scripts')},
        run_context=json.loads(args.run_context.read_text()))
    if args.case:report['unrun'] += [case for case in CASES if case!=args.case]
    lock=threading.RLock()
    def save():
        with lock:(output/'report.json').write_text(json.dumps(report,indent=2))
    save()
    try:
        with tempfile.TemporaryDirectory(prefix='cj320-',dir='/tmp') as temporary:
            root=Path(temporary)
            with cluster('needsui',port=55820,role='cj320_initializer',root=root/'pg') as config:
                with psycopg.connect(**config,autocommit=True) as conn:
                    chain=migrate.load();migrate.up(conn,chain,chain[-1]['version'])
                connection=root/'connection.json';connection.write_text(json.dumps(config));connection.chmod(0o600)
                subjects={case:{key:'cj320-'+uuid.uuid4().hex for key in ('A','B')} for case in CASES}
                auth=root/'auth';dev_auth.init(auth,[s for row in subjects.values() for s in row.values()])
                tokens={case:{key:dev_auth.token(auth,subject,120) for key,subject in row.items()} for case,row in subjects.items()}
                for target in (env,os.environ):target.update(CJ_LOCAL_CONNINFO=str(connection),CJ_LOCAL_AUTH_DIR=str(auth),
                    CJ_LOCAL_RUN_CONTEXT=str(args.run_context.resolve()),CJ_LOCAL_NEEDS_PROFILE='manual-v1')
                for row in subjects.values():
                    for subject in row.values():
                        subprocess.run([sys.executable,'-B',str(ROOT/'scripts/local_run_context.py'),'--conninfo-json',str(connection),
                            '--auth-dir',str(auth),'--run-context',str(args.run_context.resolve()),'--subject',subject,'init-budget'],cwd=ROOT,env=env,check=True,capture_output=True)
                app=app_from_environment();database=LocalDatabase(connection,run_context=context,needs_context=True)
                specs={};audit=[];worker_errors=[];active=[None];stop=threading.Event()
                def worker():
                    try:
                        while not stop.is_set():
                            with lock:key=active[0]
                            if key:
                                row=specs[key]
                                outcomes=run_once(database,row['model'],auth,tools_configuration=row['tools'])
                                with lock:row['outcomes'] += [dict(message_id=x.message_id,run_id=x.run_id,status=x.status) for x in outcomes]
                            stop.wait(.05)
                    except BaseException as error:worker_errors.append(type(error).__name__);stop.set()
                worker_thread=threading.Thread(target=worker,daemon=True);worker_thread.start()
                async def observed(scope,receive,send):
                    if scope['type']!='http':return await app(scope,receive,send)
                    with lock:key=active[0];row=specs.get(key)
                    authorization=dict(scope.get('headers',[])).get(b'authorization')
                    account=next((name for name,token in tokens.get(key,{}).items() if authorization==('Bearer '+token).encode()),None)
                    event=dict(case=key,account=account,method=scope['method'],path=scope['path'],started=time.monotonic())
                    with lock:audit.append(event)
                    body=bytearray()
                    async def inspect_receive():
                        message=await receive()
                        if message['type']=='http.request':
                            body.extend(message.get('body',b''))
                            if not message.get('more_body',False) and scope['path']=='/v1/needs-actions':
                                raw=bytes(body);command=json.loads(raw)
                                event.update(action_id=command['action_id'],needs_id=command['needs_id'],expected_version=command['expected_version'],body_sha256=hashlib.sha256(raw).hexdigest())
                                if row:row['originals'].append(raw)
                        return message
                    async def capture(message):
                        if message['type']=='http.response.start':event['status']=message['status']
                        if message['type']=='http.response.body' and not message.get('more_body',False):
                            event['finished_at']=time.monotonic()
                            if event.get('status',200)!=200:
                                try:
                                    error=json.loads(message.get('body',b''))['error']
                                    event['error']={name:error[name] for name in ('code','outcome','recovery')}
                                except (ValueError,KeyError):pass
                        if row and row['hold_ack'] and scope['path']=='/v1/needs-actions' and message['type']=='http.response.body' and event.get('status')==200:
                            row['hold_ack']=False;row['manual_entered'].set()
                            if row['mode']=='lost-ack':
                                event['ack_loss']='transport closed after actual successful commit'
                                raise ConnectionResetError('synthetic transport ACK loss after actual commit')
                            await asyncio.to_thread(row['manual_release'].wait,90)
                        if row and row['hold_read'] and scope['path']=='/v1/needs' and message['type']=='http.response.body' and event.get('status')==200:
                            row['hold_read']=False;row['read_entered'].set();await asyncio.to_thread(row['read_release'].wait,90)
                        await send(message)
                    await app(scope,inspect_receive,capture)
                server=uvicorn.Server(uvicorn.Config(observed,host='127.0.0.1',port=0,log_level='critical'))
                thread=threading.Thread(target=server.run,daemon=True);thread.start();deadline=time.monotonic()+20
                while not server.started:
                    if time.monotonic()>deadline:raise TimeoutError('local API start')
                    time.sleep(.05)
                endpoint='http://127.0.0.1:'+str(server.servers[0].sockets[0].getsockname()[1])
                def prepare(case):
                    if case in specs:raise ValueError('case already prepared')
                    mode={'testUnknownReopen':'lost-ack','testCancelWaiting':'cancel-wait'}.get(case,'normal')
                    row=dict(mode=mode,model=SyntheticNeedsModel(),tools=LocalNeedsPreview(),outcomes=[],originals=[],audit_start=len(audit),
                        manual_entered=threading.Event(),manual_release=threading.Event(),hold_ack=mode in ('lost-ack','cancel-wait'),external_posts=0,
                        read_entered=threading.Event(),read_release=threading.Event(),hold_read=False)
                    row['read_release'].set()
                    with TestClient(app) as client:
                        result=client.put('/v1/conversations',params={'conversation_id':case},headers={'Authorization':'Bearer '+tokens[case]['A']});assert result.status_code==200
                    with lock:specs[case]=row;active[0]=case
                    return dict(case_id=case,endpoint=endpoint,accounts=tokens[case],subjects=subjects[case],conversation=case,needs_id='needs-'+case)
                def proof(case,settled=False):
                    row=specs[case];scope=scope_for(ISSUER,subjects[case]['A']);deadline=time.monotonic()+20
                    while True:
                        with database.connect(scope) as conn:pending=conn.execute('SELECT count(*) FROM cj_message_delivery WHERE NOT acknowledged').fetchone()[0]
                        if not settled or not pending or time.monotonic()>deadline:break
                        time.sleep(.05)
                    with database.connect(scope) as conn:
                        role=conn.execute('SELECT current_user').fetchone()[0]
                        originals=conn.execute('SELECT message_id,raw_input,run_id FROM cj_message_receipt WHERE conversation_id=%s ORDER BY sequence',(case,)).fetchall()
                        account=ledger_scope_for(scope,context.current.meter)
                        ledger=decode(conn.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()[0])
                        operations=conn.execute('SELECT o.operation_key,o.registration_id,o.kind,o.command_bytes,o.input_bytes FROM cj_run_metered_operation o JOIN cj_message_receipt m ON (m.scope,m.run_id)=(o.scope,o.run_id) WHERE m.conversation_id=%s ORDER BY m.sequence,o.operation_key',(case,)).fetchall()
                        counts={name:conn.execute('SELECT count(*) FROM '+table).fetchone()[0] for name,table in [('needs_records','cj_needs_record'),('needs_revisions','cj_needs_revision'),('memory_records','cj_memory_item'),('trip_records','cj_trip_record')]}
                    status=None;text='';effects=[]
                    if originals:
                        messages=MessageService(database.message_repository(scope),new_run_id=lambda:None);r=messages.query(originals[-1][0]).receipt
                        state=RunService(database.run_repository(scope),valid=lambda binding:messages.query(binding.message_id) is not None).snapshot(Binding(scope,r.conversation_id,r.generation,r.message_id,r.run_id,r.sequence))
                        status=state.status;text=state.text;effects=list(state.effects)
                        if status=='completed':
                            source=json.loads(bytes(originals[-1][1]))['text']
                            expected=encode_preview(synthetic_extract(source),message_id=r.message_id,run_id=r.run_id,source_text=source).decode('utf8')+'\n'
                            assert text==expected
                    with TestClient(app) as client:
                        result=client.get('/v1/needs',params={'needs_id':'needs-'+case},headers={'Authorization':'Bearer '+tokens[case]['A']})
                        snapshot=result.json().get('needs') if result.status_code==200 else None
                    events=[e for e in audit[row['audit_start']:] if e['case']==case]
                    manual=[e for e in events if e['method']=='POST' and e['path']=='/v1/needs-actions']
                    result=dict(runtime_role=role,pending=pending,status=status,text=text,message_id=originals[-1][0] if originals else None,
                        snapshot_status=result.status_code,snapshot_version=snapshot['version'] if snapshot else None,
                        snapshot_fields_json=json.dumps(snapshot['fields'],ensure_ascii=False,sort_keys=True) if snapshot else None,
                        messages=len(originals),posts=sum(e['method']=='POST' and e['path']=='/v1/messages' for e in events),
                        manual_posts=len(manual),external_posts=row['external_posts'],model_calls=row['model'].calls,
                        manual_originals=[{k:e.get(k) for k in ('action_id','body_sha256','status','expected_version')} for e in manual],
                        manual_bytes_sha256=hashlib.sha256(b''.join(row['originals'])).hexdigest(),exposure=Meter.exposure(ledger),effects=effects,
                        originals_sha256=hashlib.sha256(b''.join(bytes(x[1]) for x in originals)).hexdigest(),
                        registered_sha256=hashlib.sha256(b''.join(str(x[:3]).encode()+bytes(x[3])+bytes(x[4]) for x in operations)).hexdigest(),
                        ledger_sha256=hashlib.sha256(encode(ledger).encode()).hexdigest(),
                        forbidden_writes=sum(e['method'] not in ('GET','HEAD') and e['path'].startswith(('/v1/trip','/v2/trip','/v3/trip','/v4/trip','/v1/memor','/v2/memor')) for e in events),
                        worker_errors=worker_errors,responses=events,**counts)
                    assert role=='cj_m1_runtime' and not worker_errors and not result['forbidden_writes'] and not effects and counts['memory_records']==0 and counts['trip_records']==0
                    if settled:assert not pending
                    report.setdefault('proofs',{})[case]=result;save();return result
                def external_correction(case):
                    with TestClient(app) as client:
                        headers={'Authorization':'Bearer '+tokens[case]['A']}
                        current=client.get('/v1/needs',params={'needs_id':'needs-'+case},headers=headers);assert current.status_code==200
                        command=dict(action_id='external-'+uuid.uuid4().hex,needs_id='needs-'+case,expected_version=current.json()['needs']['version'],
                            source=dict(kind='manual',text='SYNTHETIC second client explicitly changes party size'),changes=dict(party_size=dict(state='known',value=5)))
                        raw=json.dumps(command,ensure_ascii=False,separators=(',',':')).encode()
                        saved=client.post('/v1/needs-actions',content=raw,headers=dict(headers,**{'Content-Type':'application/octet-stream'}));assert saved.status_code==200
                        specs[case]['external_posts']+=1
                    return dict(action_id=command['action_id'],sha256=hashlib.sha256(raw).hexdigest())
                class Control(BaseHTTPRequestHandler):
                    def log_message(self,*_):pass
                    def do_GET(self):
                        try:
                            q=parse_qs(urlparse(self.path).query);path=urlparse(self.path).path;case=q['case'][0]
                            if path=='/prepare':value=prepare(case)
                            elif path=='/proof':value=proof(case,settled=q.get('settled')==['1'])
                            elif path=='/wait-completed':
                                deadline=time.monotonic()+30
                                while True:
                                    value=proof(case,settled=True)
                                    if value['status']=='completed':break
                                    if value['status'] in ('failed','cancelled','unknown') or time.monotonic()>deadline:raise RuntimeError('completed original RUN required')
                                    time.sleep(.05)
                            elif path=='/external-correction':value=external_correction(case)
                            elif path=='/wait-manual':assert specs[case]['manual_entered'].wait(30);value={}
                            elif path=='/release-manual':specs[case]['manual_release'].set();value={}
                            elif path=='/hold-read':specs[case]['read_release'].clear();specs[case]['read_entered'].clear();specs[case]['hold_read']=True;value={}
                            elif path=='/wait-read':assert specs[case]['read_entered'].wait(20);value={}
                            elif path=='/release-read':specs[case]['read_release'].set();value={}
                            else:raise ValueError('unknown test control')
                            raw=json.dumps(value).encode();self.send_response(200);self.end_headers();self.wfile.write(raw)
                        except Exception as error:
                            report.setdefault('control_errors',[]).append(type(error).__name__);save();self.send_response(500);self.end_headers();self.wfile.write(type(error).__name__.encode())
                control=ThreadingHTTPServer(('127.0.0.1',0),Control);threading.Thread(target=control.serve_forever,daemon=True).start()
                try:
                    spec=importlib.util.spec_from_file_location('needs_builder',ROOT/'scripts/check_ios_trip_confirm.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                    builder=object.__new__(module.XCTestDriver);builder.directory=output/'project';builder.directory.mkdir();builder.write_project(0)
                    (builder.directory/'G2CControl.swift').write_text((HERE/'DevelopmentNeedsUITests.swift').read_text().replace('__FIXTURE_URL__',f'http://127.0.0.1:{control.server_port}'))
                    project=builder.directory/'G2CAcceptance.xcodeproj';pbx=project/'project.pbxproj'
                    text=pbx.read_text().replace('space.go2china.foundation.local',BUNDLE).replace('space.go2china.foundation.control',BUNDLE+'.control')
                    entitlements=builder.directory/'Needs.entitlements';entitlements.write_bytes(plistlib.dumps({'application-identifier':BUNDLE,'keychain-access-groups':[BUNDLE]}))
                    text=text.replace(json.dumps(str(ROOT/'ios/App/Development.entitlements')),json.dumps(str(entitlements)))
                    line=next(x for x in text.splitlines() if x.startswith('A00000000000000000000004 = {isa = XCBuildConfiguration; name = Debug;'))
                    text=text.replace(line,line+'\n'+line.replace('A00000000000000000000004','A0000000000000000000000C',1).replace('name = Debug;','name = Release;',1)).replace('buildConfigurations = (A00000000000000000000004);','buildConfigurations = (A00000000000000000000004, A0000000000000000000000C);');pbx.write_text(text)
                    for case in ([args.case] if args.case else CASES):
                        result=output/(case+'.xcresult')
                        command=['xcodebuild','-project',str(project),'-scheme','G2CControl','-configuration','Release' if case=='testReleaseClosed' else 'Debug',
                            '-destination','platform=iOS Simulator,id='+args.simulator,'-derivedDataPath',str(build),'-resultBundlePath',str(result),
                            '-scmProvider','system','-skipPackageUpdates','-onlyUsePackageVersionsFromResolvedFile','-parallel-testing-enabled','NO','-collect-test-diagnostics','never',
                            'ARCHS=arm64','ONLY_ACTIVE_ARCH=YES','CODE_SIGNING_ALLOWED=YES','CODE_SIGN_IDENTITY=-','-only-testing:G2CControl/DevelopmentNeedsUITests/'+case,'test']
                        print('NEEDS '+case,flush=True);run=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=1800)
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
                            if current['needs_records']:
                                other=client.get('/v1/needs',params={'needs_id':'needs-'+case},headers={'Authorization':'Bearer '+tokens[case]['B']})
                                if case=='testOwnerLate':
                                    assert other.status_code==200 and other.json()['needs']['fields']['party_size']['value']==9
                                    assert json.loads(current['snapshot_fields_json'])['party_size']['value']==3
                                else:assert other.status_code==503 and 'needs' not in other.json()
                                first=next(x for x in current['manual_originals'] if x['status']==200)
                                receipt=client.get('/v1/needs-action-receipts',params={'action_id':first['action_id']},headers={'Authorization':'Bearer '+tokens[case]['B']})
                                assert (receipt.status_code==503 and 'receipt' not in receipt.json()) or (receipt.status_code==200 and receipt.json()['receipt'] is None)
                    container=Path(subprocess.check_output(['xcrun','simctl','get_app_container',args.simulator,BUNDLE,'data'],env=env,text=True).strip())
                    private_tokens=[token.encode() for pair in tokens.values() for token in pair.values()]
                    plaintext=[value.encode() for value in ('we are 3; budget','本次3人；预算','SYNTHETIC_PRIVATE_NEEDS_SENTINEL')]
                    for path in container.rglob('*'):
                        if path.is_file() and not path.is_symlink():
                            data=path.read_bytes();assert not any(token in data for token in private_tokens) and b'-----BEGIN PRIVATE KEY-----' not in data
                            assert not any(value in data for value in plaintext),'plaintext original input in App files'
                    report['token_key_scan']='PASS';report['plaintext_scan']='PASS';report['status']='PASS' if not args.case else 'PARTIAL_PASS';save()
                finally:
                    for row in specs.values():row['manual_release'].set();row['read_release'].set()
                    stop.set();worker_thread.join(10);server.should_exit=True;thread.join(10);control.shutdown();control.server_close()
            report['private_pg_stopped']=True;save()
    except BaseException as error:report['status']='FAIL';report['error']=type(error).__name__;raise
    finally:save()

if __name__=='__main__':main()
