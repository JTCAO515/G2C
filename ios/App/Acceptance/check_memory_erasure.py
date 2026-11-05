"""#468 normal App: actual signed C/B host, private PG, worker/Fake and native UI.

Only local launch configuration and observations reach the test runner. Protected
items/actions/operations and physical outcomes are never supplied to App code.
"""
import argparse
from dataclasses import replace
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import secrets as random_secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
BUNDLE='space.go2china.memory-erasure.acceptance'
CASES={'testMemoryErasureEnglish':'complete-en','testMemoryErasureChinese':'complete-zh-Hans',
       'testUnknownErasureReopensEnglish':'lost-ack-en','testUnknownErasureReopensChinese':'lost-ack-zh-Hans',
       'testErasureJournalAccountCleanupEnglish':'account-en'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('backend-source','run-context','output','build-dir'):parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--backend-head',required=True)
    target=parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--simulator');target.add_argument('--device')
    parser.add_argument('--local-tls',type=Path)
    parser.add_argument('--case',choices=CASES)
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args();backend=args.backend_source.resolve();output=args.output.resolve();build=args.build_dir.resolve()
    tls=None
    if args.device:
        if not args.local_tls:parser.error('--device requires the approved --local-tls profile')
        from m4_device import LocalTLS,configure_project,private_workspace,scan_app_container
        from m4_native import DeviceNative,authenticated_control
        tls=LocalTLS.load(args.local_tls)
    elif args.local_tls:parser.error('--local-tls requires --device')
    if tls: device_project_root, build = private_workspace(output, build)
    os.umask(0o077)
    for path in (output,build):
        if path.is_relative_to(ROOT) or path.is_relative_to(backend):raise ValueError('external artifact roots required')
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT):raise ValueError('commit candidate first')
    if subprocess.check_output(['git','status','--porcelain'],cwd=backend):raise ValueError('clean backend pin required')
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=backend,text=True).strip()!=args.backend_head:raise ValueError('backend pin mismatch')
    output.mkdir(parents=True)
    env={k:v for k,v in os.environ.items() if not k.startswith(('PG','LIBPQ','SIMCTL_CHILD_','G2C_DEV_','CJ_LOCAL_'))}
    env.update(CJ_ENV='local',OS_ACTIVITY_MODE='disable',DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer')
    for key in tuple(os.environ):
        if key.startswith(('PG','LIBPQ','CJ_LOCAL_')):os.environ.pop(key)
    os.environ['CJ_ENV']='local'
    sys.path[:0]=[str(backend/'scripts'),str(backend/'backend'),*sorted(str(p) for p in (backend/'backend').iterdir() if p.is_dir())]
    import psycopg,uvicorn,dev_auth,migrate,local_run_context
    from pg_suites import cluster
    from cj_api.local_run_context import load_run_context
    from cj_api.local_app import create_local_app,load_history_configuration,load_confirmation_signer
    from cj_cleanup.registry import freeze_controls
    from prepare_preserved_history_source import prepare_preserved_history
    from prepare_provided_cleanup_sources import project_registry
    from check_account_cleanup_component import FULL_INVENTORY
    context=load_run_context(args.run_context);assert context.current.meter.budget==4
    cases={args.case:CASES[args.case]} if args.case else CASES
    sources=[Path(__file__),HERE/'MemoryErasureUITests.swift',HERE/'prepare_preserved_history_source.py',HERE/'prepare_provided_cleanup_sources.py',
             HERE/'check_account_cleanup_component.py',*list((ROOT/'ios/App').glob('*.swift'))]
    if tls:sources += [HERE/name for name in ('m4_device.py','m4_native.py','m4_artifacts.py','M4DeviceControl.swift','M4DeviceTestSession.swift')]
    for module in ('CJShell','CJMemoryClient','CJCleanupClient','CJMessageClient','CJAuth','CJOfflineTrip','CJTripClient'):
        sources+=list((ROOT/'ios/Modules'/module/'Sources').rglob('*.swift'))
    report=dict(status='RUNNING',source_status='UNRUN',native='UNRUN',head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        backend_head=args.backend_head,cases={},source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        unrun=['physical device','real accounts/cloud/providers/fees/backups'])
    def save():(output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    if tls:report.update(layer='signed approved iPhone/local pinned HTTPS/private PG/canonical erasure host',
        raw_native_bundle_shareable=False,build_inputs_shareable=False,
        device_font_scope='system default font; no size override',
        unrun=['real accounts/cloud/providers/fees/backups'])
    save();secrets=[];server=None;control=None;thread=None;native=None;control_token=None;original_size=None;executing_case=None;active={'case':None};lock=threading.Lock();observations={}
    suite_complete=False
    try:
        with tempfile.TemporaryDirectory(prefix='cj468-app-',dir='/tmp') as temp:
            folder=Path(temp)
            with cluster('erasure468',port=55862,role='cj468_initializer',root=folder/'pg') as config:
                with psycopg.connect(**config,autocommit=True) as conn:
                    chain=migrate.load();migrate.up(conn,chain,chain[-1]['version'])
                connection=folder/'connection.json';connection.write_text(json.dumps(config));connection.chmod(0o600)
                subjects={case:{k:'cj468-'+uuid.uuid4().hex for k in ('A','B')} for case in cases.values()}
                auth=folder/'auth';dev_auth.init(auth,[s for pair in subjects.values() for s in pair.values()])
                tokens={case:{k:dev_auth.token(auth,s,120) for k,s in pair.items()} for case,pair in subjects.items()}
                secrets.extend(t for pair in tokens.values() for t in pair.values())
                for pair in subjects.values():
                    for subject in pair.values():local_run_context.provision_budget(connection,context,subject)
                hosts={};proofs={};registry=backend/'backend/storage-registry.json'
                inventory=tuple(t for t in FULL_INVENTORY if t!='external-processing')
                for case in cases.values():
                    source_folder=folder/case;source_folder.mkdir()
                    human,proof,parts=prepare_preserved_history(connection,auth,context,subjects[case],tokens[case],source_folder,registry,include_apps=True)
                    projected=source_folder/'provided-registry.json'
                    projected.write_text(json.dumps(project_registry(json.loads(registry.read_bytes()),inventory,'actual-provided-erasure-app'),sort_keys=True))
                    selected=freeze_controls(projected.read_bytes(),inventory,versions=('CLEANUP@1.0','CLEANUP@1.1'))
                    actual=freeze_controls(registry.read_bytes(),FULL_INVENTORY,versions=('CLEANUP@1.0','CLEANUP@1.1'))
                    entries={e.registry_id:e for e in actual.entries}
                    assert not selected.gaps and not actual.gaps and all(e==entries[e.registry_id] for e in selected.entries)
                    assert selected.retained_controls==actual.retained_controls
                    cleanup_options=replace(parts['cleanup_options'],inventory=inventory,registry_path=projected)
                    account=create_local_app(conninfo_path=connection,auth_dir=auth,run_context=context,cleanup_configuration=cleanup_options,
                        history_configuration=load_history_configuration(auth),confirmation_signer=load_confirmation_signer(auth))
                    hosts[case]=dict(human=human,account=account,**parts);proofs[case]=proof
                    observations[case]=dict(saved=[],erased=[],api=[])
                report.update(source_status='PASS',sources=proofs);save()
                if args.prepare_only and not tls:
                    report.update(status='UNRUN',native='UNRUN');return

                async def observed(scope,receive,send):
                    if scope['type']!='http':return await hosts[next(iter(hosts))]['human'](scope,receive,send)
                    case=active['case'];assert case in hosts
                    path=scope['path'];host=hosts[case]
                    selected=host['typed'] if path.startswith('/v2/memor') else host['erasure'] if path.startswith('/v1/memory-era') else host['account'] if '/cleanup-' in path or '/account-cleanup-' in path else host['human']
                    messages=[];body=bytearray()
                    async def read():
                        message=await receive()
                        if message['type']=='http.request':body.extend(message.get('body',b''))
                        return message
                    async def capture(message):messages.append(message)
                    await selected(scope,read,capture)
                    status=next(m['status'] for m in messages if m['type']=='http.response.start')
                    raw=b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body')
                    response=json.loads(raw) if raw else {}
                    for value in (response,response.get('registration'),response.get('invocation')):
                        if isinstance(value,dict):
                            for name in ('device_token','receipt_token','progress_token'):
                                if isinstance(value.get(name),str):secrets.append(value[name])
                    entry=dict(method=scope['method'],path=path,status=status,input_sha256=hashlib.sha256(body).hexdigest())
                    if isinstance(response.get('error'),dict):entry['error_code']=response['error'].get('code')
                    drop=False
                    with lock:
                        data=observations[case];data['api'].append(entry)
                        if status==200 and scope['method']=='POST' and path=='/v2/memories':
                            command=json.loads(body);receipt=response['receipt']
                            assert receipt['input_sha256']==entry['input_sha256'] and receipt['item_id']==command['item_id']
                            data['saved'].append(dict(command=command,receipt=receipt))
                        if status==200 and scope['method']=='POST' and path=='/v1/memory-erasures':
                            command=json.loads(body);result=response['result']
                            assert result['action_id']==command['action_id'] and result['stop_use']=='stopped'
                            data['erased'].append(dict(command=command,result=result))
                            drop=case.startswith('lost-ack-') and len(data['erased'])==1
                    if drop:
                        trace=response['request_id']
                        error=json.dumps(dict(request_id=trace,error=dict(code='ERASURE_OUTCOME_UNKNOWN',category='dependency',message_en='Unknown',message_zh='未知',outcome='unknown',recovery='reconcile_original'))).encode()
                        await send({'type':'http.response.start','status':503,'headers':[(b'content-type',b'application/json'),(b'cache-control',b'no-store'),(b'x-request-id',trace.encode())]})
                        await send({'type':'http.response.body','body':error});return
                    for message in messages:await send(message)

                if tls:listener=tls.listener()
                else:listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(128)
                port=listener.getsockname()[1];endpoint=('https://'+tls.host if tls else 'http://127.0.0.1')+':'+str(port)
                server=uvicorn.Server(uvicorn.Config(observed,log_level='error',access_log=False,**(tls.uvicorn_options() if tls else {})));thread=threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True);thread.start()
                deadline=time.monotonic()+10
                while not server.started:
                    if not thread.is_alive() or time.monotonic()>deadline:raise RuntimeError('actual erasure host unavailable')
                    time.sleep(.02)
                namespace=lambda value:str(uuid.UUID(bytes=hashlib.sha256(value.encode()).digest()[:16])).upper()
                def with_container(action):
                    if tls:
                        with tempfile.TemporaryDirectory(prefix='g2c-erasure-private-scan-') as directory:
                            destination=Path(directory)/'app-data'
                            scan_app_container(args.device,BUNDLE,destination,tokens[active['case']].values())
                            return action(destination)
                    container=Path(subprocess.check_output(['xcrun','simctl','get_app_container',args.simulator,BUNDLE,'data'],env=env,text=True).strip())
                    return action(container)
                def local_proof(case):
                    def inspect(container):
                        account=namespace('G2C.DEBUG.TRIP.account|https://local.g2c.invalid|'+subjects[case]['A'])
                        base=container/'Library/Application Support/G2CDevelopmentMemory'/namespace('G2C.DEBUG.TRIP.environment|'+endpoint)
                        with lock:data=observations[case];saved=list(data['saved']);erased=list(data['erased'])
                        assert len(saved)==2 and len(erased)==1
                        target=saved[-1]['command'];operation=erased[0]
                        expected=base/(account+'.typed-v2')/(hashlib.sha256(target['operation_id'].encode()).hexdigest()+'.memory')
                        files=[p for root in base.glob(account+'*') if root.is_dir() for p in root.rglob('*') if p.is_file()]
                        originals={str(p.relative_to(base)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.parent.name.startswith(account+'.erasure-v1')}
                        target_files={str(expected.relative_to(base)):hashlib.sha256(expected.read_bytes()).hexdigest()} if expected.exists() else {}
                        other={str(p.relative_to(base)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p!=expected and str(p.relative_to(base)) not in originals}
                        assert all(target['text'].encode() not in p.read_bytes() for p in files),'App leaked plain target text'
                        return dict(item_journals=target_files,other_journals=other,erasure_originals=originals,
                            erasure_post_count=len(erased),original_action_id=operation['command']['action_id'],operation_id=operation['result']['operation_id'])
                    return with_container(inspect)
                class Control(BaseHTTPRequestHandler):
                    def log_message(self,*_):pass
                    def do_GET(self):
                        path=urlsplit(self.path);query={k:v[0] for k,v in parse_qs(path.query).items()}
                        if path.path=='/fixture':
                            case=query['case'];assert case in hosts;active['case']=case
                            profile=dict(version='app-memory.2',**{k:hosts[case]['policy'][k] for k in ('subjects','slots','extents')})
                            launch=dict(G2C_DEV_ACCOUNT_MODE='1',G2C_DEV_API_BASE_URL=endpoint,G2C_DEV_ACCOUNTS='{}' if tls else json.dumps(tokens[case]),G2C_DEV_OFFLINE_TRIP='last-sync-v1',
                                G2C_DEV_CLEANUP_PROFILE='device-v4',G2C_DEV_TRAVEL_PROFILE=json.dumps(dict(version='app-travel.1',travel_ids=[])),
                                G2C_DEV_TYPED_MEMORY_PROFILE=json.dumps(profile),G2C_DEV_TYPED_MEMORY_URL=endpoint,G2C_DEV_MEMORY_ERASURE_URL=endpoint)
                            value=dict(bundle=BUNDLE,case_id=case,launch=launch,subjects=subjects[case],option_label='self · pace · Long term / 长期',other_option_label='self · budget · Long term / 长期',
                                text='我明确保存少辣的旅行偏好',other_text='这是另一条应当保留的记忆',occurred_at='时间不详')
                        elif path.path=='/size':
                            size='large' if query['value']=='standard' else 'accessibility-extra-extra-extra-large'
                            assert query['value'] in ('standard','max')
                            value={'status':'system default font; no size mutation'}
                        elif path.path=='/observed-save':
                            with lock:value={'item_id':observations[active['case']]['saved'][-1]['receipt']['item_id']}
                        elif path.path=='/local-proof':value=local_proof(active['case'])
                        else:self.send_response(404);self.end_headers();return
                        data=json.dumps(value,ensure_ascii=False).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(data)
                control_token=random_secrets.token_urlsafe(32) if tls else None
                def stage_input(request):
                    query=parse_qs(urlsplit(request).query)
                    if set(query)!={'case'} or query['case']!=[executing_case]:raise ValueError('Staging requires the active erasure case')
                    native.stage(case=query['case'][0])
                control=ThreadingHTTPServer((tls.host if tls else '127.0.0.1',0),
                    authenticated_control(Control,control_token,stage_input,lambda: executing_case) if tls else Control)
                if tls:tls.secure_http_server(control)
                threading.Thread(target=control.serve_forever,daemon=True).start()
                spec=importlib.util.spec_from_file_location('erasure_builder',ROOT/'scripts/check_ios_trip_confirm.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                builder=object.__new__(module.XCTestDriver);builder.directory=(device_project_root if tls else output)/'project';builder.directory.mkdir();builder.write_project(0)
                control_url=('https://'+tls.host if tls else 'http://127.0.0.1')+':'+str(control.server_port)
                (builder.directory/'G2CControl.swift').write_text((HERE/'MemoryErasureUITests.swift').read_text().replace('__CONTROL_URL__',control_url))
                project=builder.directory/'G2CAcceptance.xcodeproj';pbx=project/'project.pbxproj';text=pbx.read_text().replace('space.go2china.foundation.local',BUNDLE).replace('space.go2china.foundation.control',BUNDLE+'.control')
                entitlement=builder.directory/'Erasure.entitlements';entitlement.write_bytes(plistlib.dumps({'application-identifier':BUNDLE,'keychain-access-groups':[BUNDLE]}))
                pbx.write_text(text.replace(json.dumps(str(ROOT/'ios/App/Development.entitlements')),json.dumps(str(entitlement))))
                if tls:_,configuration_file,_=configure_project(project,tls,control_url,control_token,bundle=BUNDLE)
                for test,case in cases.items():
                    executing_case=case
                    report['cases'][test]='RUNNING';save()
                    if tls:
                        active['case']=case
                        detail=dict(status='RUNNING');report.setdefault('device_native',{})[test]=detail
                        case_output=output/'device-native'/test;case_output.mkdir(parents=True,mode=0o700)
                        native=DeviceNative(args.device,BUNDLE,project,configuration_file,build,ROOT,case_output,tokens[case],control_token,detail,evidence_root=output,case_id=case)
                        selected=['MemoryErasureUITests/'+test]
                        native.build_for_testing('Debug',selected,env)
                        if args.prepare_only:
                            detail['status']='PREPARED_EXECUTION_UNRUN';report['cases'][test]='UNRUN';save();continue
                        summary=native.run('Debug',selected,env)
                        native.scan('Debug');detail['status']='PASS'
                        value={k:summary[k] for k in ('passedTests','failedTests','skippedTests')}
                    else:
                        result=output/(test+'.xcresult')
                        command=['xcodebuild','-project',str(project),'-scheme','G2CControl','-configuration','Debug','-destination','platform=iOS Simulator,id='+args.simulator,
                            '-derivedDataPath',str(build),'-resultBundlePath',str(result),'-skipPackageUpdates','-onlyUsePackageVersionsFromResolvedFile','-parallel-testing-enabled','NO',
                            '-collect-test-diagnostics','never','ARCHS=arm64','ONLY_ACTIVE_ARCH=YES','CODE_SIGNING_ALLOWED=YES','CODE_SIGN_IDENTITY=-','-only-testing:G2CControl/MemoryErasureUITests/'+test,'test']
                        run=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=1200)
                        log=run.stdout+run.stderr
                        for secret in secrets:log=log.replace(secret,'<redacted-local-credential>')
                        (output/(test+'.log')).write_text(log)
                        if run.returncode:report['cases'][test]='FAIL';save();run.check_returncode()
                        summary=json.loads(subprocess.check_output(['xcrun','xcresulttool','get','test-results','summary','--path',str(result)],env=env,text=True))
                        value={k:summary[k] for k in ('passedTests','failedTests','skippedTests')};assert value==dict(passedTests=1,failedTests=0,skippedTests=0)
                    proof=local_proof(case);assert not proof['item_journals'] and proof['erasure_post_count']==1
                    if case=='account-en':assert not proof['other_journals'] and not proof['erasure_originals']
                    else:assert proof['other_journals'] and proof['erasure_originals']
                    report.setdefault('results',{})[test]=value;report.setdefault('proofs',{})[test]=proof;report['cases'][test]='PASS';save()
                if args.prepare_only:report.update(status='PREPARED_EXECUTION_UNRUN',native='UNRUN')
                else:
                    def scan(container):
                        for path in [*container.rglob('*'),*output.rglob('*')]:
                            if path.is_file() and any(secret.encode() in path.read_bytes() for secret in secrets):raise AssertionError('credential leaked into App artifacts')
                    with_container(scan)
                    report.update(status='VERIFYING_CLEANUP',native='PASS',credential_scan='PASS')
            report['pg_stopped']=True
        report['task_credentials_destroyed']=True
        assert report['head']==subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'App head changed during acceptance'
        assert args.backend_head==subprocess.check_output(['git','rev-parse','HEAD'],cwd=backend,text=True).strip(),'backend head changed during acceptance'
        assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest for name,digest in report['source_hashes'].items()),'source changed during acceptance'
        suite_complete=True
        report['status']='VERIFYING_CLEANUP'
    except BaseException as error:
        report.update(status='FAIL',error_type=type(error).__name__);raise
    finally:
        try:
            report['api']={case:value['api'] for case,value in observations.items()}
            if control:control.shutdown();control.server_close()
            if server:server.should_exit=True
            if thread:thread.join(timeout=10)
            if tls:
                try:
                    if native is not None:native.cleanup_input()
                except Exception:
                    report['status']='FAIL';raise
                finally:
                    (device_project_root/'project/M4ControlBootstrap.plist').unlink(missing_ok=True)
                    save()
                if control_token is not None:
                    for path in output.rglob('*'):
                        if path.is_file() and not path.is_symlink() and control_token.encode() in path.read_bytes():
                            report['status']='FAIL';save();raise AssertionError('control credential in evidence export')
                if thread and thread.is_alive():
                    report['status']='FAIL';save();raise RuntimeError('erasure host did not stop')
            if args.prepare_only and report['source_status']=='PASS':report.update(pg_stopped=True,task_credentials_destroyed=True)
            save()
            if suite_complete:
                expected='UNRUN' if args.prepare_only else 'PASS'
                assert report['cases'] and all(value==expected for value in report['cases'].values())
                report['status']='PREPARED_EXECUTION_UNRUN' if args.prepare_only else 'PASS'
                save()
        except BaseException as error:
            report.update(status='FAIL',error_type=type(error).__name__);save();raise



if __name__=='__main__':main()
