"""#460 ordinary App: actual canonical producer/worker, signed C/B APIs and native UI.

Launch configuration contains accounts and explicit policies, never producer,
attempt, candidate or action IDs. Test selectors and proofs observe actual APIs.
"""
import argparse
import base64
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
BUNDLE='space.go2china.memory-candidate.acceptance'
CASES={'testConfirmCandidateEnglish':'confirm-en','testConfirmCandidateChinese':'confirm-zh-Hans',
       'testRejectCandidateEnglish':'reject-en','testUnknownCandidateReopensChinese':'lost-ack-zh-Hans',
       'testAccountClearsCandidateFamilyEnglish':'account-en','testFreshCurrentCandidateEnglish':'current-en'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('backend-source','run-context','output','build-dir'):parser.add_argument('--'+key,type=Path,required=True)
    parser.add_argument('--backend-head',required=True)
    target=parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--simulator');target.add_argument('--device')
    parser.add_argument('--local-tls',type=Path)
    parser.add_argument('--case',choices=CASES);parser.add_argument('--prepare-only',action='store_true')
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
        if path.is_relative_to(ROOT) or path.is_relative_to(backend):raise ValueError('external artifacts required')
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT):raise ValueError('commit App candidate first')
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
    from cj_api.local_run_context import load_run_context
    from cj_api.local_app import create_local_app,load_history_configuration,load_confirmation_signer,scope_for,ISSUER
    from cj_api.local_cleanup import load_configuration
    from cj_memory.typed_local import TypedConfiguration
    from cj_memory.typed_api import create_local_typed_app
    from cj_cleanup.registry import freeze_controls
    from cj_run.step_usage import ledger_scope_for
    from cj_usage.codec import decode as decode_ledger
    from fastapi.testclient import TestClient
    from pg_suites import cluster
    from prepare_memory_candidate_source import build_source_host,prepare_source
    from prepare_provided_cleanup_sources import project_registry,configuration_document
    from check_account_cleanup_component import FULL_INVENTORY
    packed=lambda value:json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
    context=load_run_context(args.run_context);assert context.current.meter.budget==2
    cases={args.case:CASES[args.case]} if args.case else CASES
    sources=[Path(__file__),HERE/'MemoryCandidateUITests.swift',HERE/'prepare_memory_candidate_source.py',HERE/'prepare_provided_cleanup_sources.py',HERE/'check_account_cleanup_component.py',*list((ROOT/'ios/App').glob('*.swift'))]
    if tls:sources += [HERE/name for name in ('m4_device.py','m4_native.py','m4_artifacts.py','M4DeviceControl.swift','M4DeviceTestSession.swift')]
    for module in ('CJShell','CJMemoryClient','CJCleanupClient','CJMessageClient','CJAuth','CJOfflineTrip','CJTripClient'):
        sources+=list((ROOT/'ios/Modules'/module/'Sources').rglob('*.swift'))
    report=dict(status='RUNNING',source_status='UNRUN',native='UNRUN',head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        backend_head=args.backend_head,cases={},source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        unrun=['physical device/VoiceOver','real accounts/cloud/providers/fees/backups'])
    def save():(output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    if tls:report.update(layer='signed approved iPhone/local pinned HTTPS/private PG/canonical candidate producer',
        raw_native_bundle_shareable=False,build_inputs_shareable=False,
        device_font_scope='actual system maximum throughout case; original simulator transition remains separate',
        unrun=['VoiceOver','actual system font setting record','in-place system-font transition','real accounts/cloud/providers/fees/backups'])
    save();secrets=[];server=None;control=None;thread=None;native=None;control_token=None;original_size=None;executing_case=None;active={'case':None};observed={};lock=threading.Lock()
    suite_complete=False
    try:
        with tempfile.TemporaryDirectory(prefix='cj460-app-',dir='/tmp') as temp:
            folder=Path(temp)
            with cluster('candidate460app',port=55860,role='cj460_app_initializer',root=folder/'pg') as config:
                with psycopg.connect(**config,autocommit=True) as conn:
                    chain=migrate.load();migrate.up(conn,chain,chain[-1]['version'])
                connection=folder/'connection.json';connection.write_bytes(packed(config));connection.chmod(0o600)
                subjects={case:{k:'cj460-'+uuid.uuid4().hex for k in ('A','B')} for case in cases.values()}
                auth=folder/'auth';dev_auth.init(auth,[s for pair in subjects.values() for s in pair.values()])
                tokens={case:{k:dev_auth.token(auth,s,120) for k,s in pair.items()} for case,pair in subjects.items()}
                secrets.extend(t.encode() for pair in tokens.values() for t in pair.values())
                for pair in subjects.values():
                    for subject in pair.values():local_run_context.provision_budget(connection,context,subject)
                inventory=tuple(t for t in FULL_INVENTORY if t!='external-processing')
                registry=backend/'backend/storage-registry.json';full=json.loads(registry.read_bytes())
                projected=folder/'provided-registry.json';projected.write_bytes(packed(project_registry(full,inventory,'actual-candidate-app-provided')))
                actual=freeze_controls(registry.read_bytes(),FULL_INVENTORY,versions=('CLEANUP@1.0','CLEANUP@1.1'))
                selected=freeze_controls(projected.read_bytes(),inventory,versions=('CLEANUP@1.0','CLEANUP@1.1'))
                assert not actual.gaps and not selected.gaps and selected.retained_controls==actual.retained_controls
                entries={e.registry_id:e for e in actual.entries};assert all(e==entries[e.registry_id] for e in selected.entries)
                key=os.urandom(32);secrets.append(key);key_file=folder/'cleanup.key';key_file.write_bytes(key);key_file.chmod(0o600)
                setup=folder/'cleanup.json';setup.write_bytes(packed(dict(version='CJ-LOCAL-CLEANUP@3',key_file=str(key_file),key_id='candidate-local',lifetime_seconds=7200,inventory=list(inventory))));setup.chmod(0o600)
                cleanup=replace(load_configuration(setup),registry_path=projected)
                hosts={};proofs={}
                for case in cases.values():
                    ordinary=create_local_app(conninfo_path=connection,auth_dir=auth,run_context=context,travel_context=True,
                        cleanup_configuration=cleanup,history_configuration=load_history_configuration(auth),confirmation_signer=load_confirmation_signer(auth))
                    travel=None
                    if case in ('confirm-zh-Hans','lost-ack-zh-Hans','current-en'):
                        for subject in subjects[case].values():
                            assert dev_auth.activate_travel(connection,subject,context,'MESSAGE-TRAVEL-CONSUMER@1')=='activated'
                        with TestClient(ordinary) as client:
                            created=client.post('/v1/travel-context-actions',content=packed(dict(version='TRAVEL-context-action.1',action_id=str(uuid.uuid4()),operation='create',travel_context=None)),
                                headers={'Authorization':'Bearer '+tokens[case]['A'],'Content-Type':'application/octet-stream'})
                            assert created.status_code==200;travel=created.json()['receipt']['travel_context']
                    source_tokens={subject:tokens[case][key] for key,subject in subjects[case].items()}
                    collection,host,jobs,background,model,originals=build_source_host(connection,auth,context,[subjects[case]['A']],
                        source_tokens.__getitem__,travel=travel)
                    proof=prepare_source(collection,host,jobs,background,model,originals,auth,tokens[case]['A'],tokens[case]['B'],travel=travel)
                    document=configuration_document(list(subjects[case].values()))
                    if travel:
                        document['collection']['profiles'][subjects[case]['A']]=dict(document['collection']['profiles'][subjects[case]['A']],extents=['long_term','current'])
                        document['travel_contexts'][subjects[case]['A']]=[travel['id']]
                        with TestClient(ordinary) as client:
                            advanced=client.post('/v1/travel-context-actions',content=packed(dict(version='TRAVEL-context-action.1',action_id=str(uuid.uuid4()),operation='advance',travel_context=dict(id=travel['id'],expected_version=travel['version']))),
                                headers={'Authorization':'Bearer '+tokens[case]['A'],'Content-Type':'application/octet-stream'})
                            assert advanced.status_code==200
                            actual_travel=advanced.json()['receipt']['travel_context']
                            assert actual_travel['id']==travel['id'] and actual_travel['version']==travel['version']+1
                            proof.update(travel_id=travel['id'],original_travel_version=travel['version'],current_travel_version=actual_travel['version'])
                    typed=create_local_typed_app(conninfo_path=connection,auth_dir=auth,configuration=TypedConfiguration.from_bytes(packed(document)))
                    other=str(uuid.uuid4());headers={'Authorization':'Bearer '+tokens[case]['B'],'Content-Type':'application/octet-stream'}
                    with TestClient(typed) as client:
                        response=client.post('/v2/memories',content=packed(dict(version='MEMORY-manual.2',operation_id=str(uuid.uuid4()),item_id=other,subject='self',slot='budget',kind='preference',text='另一用户明确保存的预算偏好',extent='long_term',context=None,occurred_at='时间不详')),headers=headers)
                        assert response.status_code==200
                        retained=client.get('/v2/memory-items',params={'item_id':other},headers=headers);assert retained.status_code==200
                        proof['other_item_id']=other;proof['other_item_sha256']=hashlib.sha256(packed(retained.json()['item'])).hexdigest()
                    with host.database.connect(scope_for(ISSUER,subjects[case]['A'])) as conn:
                        assert conn.execute('SELECT current_user').fetchone()==('cj_m1_runtime',)
                        assert conn.execute("SELECT count(*) FROM cj_memory_item WHERE status='candidate'").fetchone()==(1,)
                        assert conn.execute('SELECT count(*) FROM cj_memory_history_candidate_action').fetchone()==(0,)
                    with psycopg.connect(**config) as conn:
                        account=ledger_scope_for(scope_for(ISSUER,subjects[case]['A']),context.current.meter)
                        ledger=decode_ledger(conn.execute('SELECT ledger FROM cj_usage_ledger_candidate WHERE scope_id=%s',(account,)).fetchone()[0])
                        assert len(ledger.attempts)==2 and all(a.state=='settled' and a.receipt.actual==1 for a in ledger.attempts.values())
                    proof['meter']=dict(attempts=2,settled=2,actual_units=2,budget=2,runtime_role='cj_m1_runtime')
                    hosts[case]=dict(collection=collection,ordinary=ordinary,typed=typed,
                        profile=document['collection']['profiles'][subjects[case]['A']],travel_ids=document['travel_contexts'][subjects[case]['A']]);proofs[case]=proof
                    observed[case]=dict(actions=[],projections=[],api=[])
                report.update(source_status='PASS',sources=proofs);save()
                if args.prepare_only and not tls:report.update(status='UNRUN',native='UNRUN');return
                async def application(scope,receive,send):
                    if scope['type']!='http':return await hosts[next(iter(hosts))]['ordinary'](scope,receive,send)
                    case=active['case'];assert case in hosts
                    path=scope['path'];host=hosts[case]
                    selected=host['collection'] if path.startswith(('/v6/memory-candidates','/v3/memory-candidate','/v3/memory-history')) else host['typed'] if path.startswith('/v2/memor') else host['ordinary']
                    messages=[];body=bytearray()
                    async def read():
                        message=await receive()
                        if message['type']=='http.request':body.extend(message.get('body',b''))
                        return message
                    async def capture(message):messages.append(message)
                    await selected(scope,read,capture)
                    status=next(m['status'] for m in messages if m['type']=='http.response.start')
                    raw=b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body')
                    with lock:
                        observed[case]['api'].append(dict(method=scope['method'],path=path,status=status,input_sha256=hashlib.sha256(body).hexdigest()))
                        if status==200 and path=='/v6/memory-candidates':observed[case]['projections'].append(json.loads(raw)['result'])
                        if status==200 and scope['method']=='POST' and path=='/v3/memory-candidate-actions':
                            command=json.loads(body);result=json.loads(raw)['result'];original=proofs[case]
                            assert command['candidate_id']==original['candidate_id'] and {k:command[k] for k in ('job_id','attempt_id')}==original['producer']
                            assert result['action_id']==command['action_id'] and result['input_sha256']==hashlib.sha256(body).hexdigest()
                            if command['operation']=='confirm':
                                if 'travel_id' in original:
                                    assert command['extent']=='current' and command['context']==dict(kind='travel',id=original['travel_id'],expected_version=original['current_travel_version'])
                                else:assert command['extent']=='long_term' and command['context'] is None
                            observed[case]['actions'].append(dict(command=command,result=result,input_sha256=result['input_sha256']))
                    if case.startswith('lost-ack-') and status==200 and scope['method']=='POST' and path=='/v3/memory-candidate-actions':
                        # The real C transaction committed above; lose only its ACK.
                        for message in messages:
                            if message['type']=='http.response.start':message={**message,'status':503}
                            await send(message)
                    else:
                        for message in messages:await send(message)
                if tls:listener=tls.listener()
                else:listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen(128)
                endpoint=('https://'+tls.host if tls else 'http://127.0.0.1')+':'+str(listener.getsockname()[1])
                server=uvicorn.Server(uvicorn.Config(application,log_level='error',access_log=False,**(tls.uvicorn_options() if tls else {})));thread=threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True);thread.start()
                deadline=time.monotonic()+10
                while not server.started:
                    if not thread.is_alive() or time.monotonic()>deadline:raise RuntimeError('actual candidate host unavailable')
                    time.sleep(.02)
                namespace=lambda value:str(uuid.UUID(bytes=hashlib.sha256(value.encode()).digest()[:16])).upper()
                def with_container(action):
                    if tls:
                        with tempfile.TemporaryDirectory(prefix='g2c-candidate-private-scan-') as directory:
                            destination=Path(directory)/'app-data'
                            scan_app_container(args.device,BUNDLE,destination,tokens[active['case']].values())
                            return action(destination)
                    container=Path(subprocess.check_output(['xcrun','simctl','get_app_container',args.simulator,BUNDLE,'data'],env=env,text=True).strip())
                    return action(container)
                def proof_for(case):
                    source=proofs[case];headers={'Authorization':'Bearer '+tokens[case]['A']}
                    with TestClient(hosts[case]['typed']) as client:
                        current=client.get('/v2/memory-items',params={'item_id':source['candidate_id']},headers=headers)
                        other=client.get('/v2/memory-items',params={'item_id':source['other_item_id']},headers={'Authorization':'Bearer '+tokens[case]['B']})
                        assert other.status_code==200 and hashlib.sha256(packed(other.json()['item'])).hexdigest()==source['other_item_sha256']
                    account=namespace('G2C.DEBUG.TRIP.account|https://local.g2c.invalid|'+subjects[case]['A'])
                    def collect(container):
                        base=container/'Library/Application Support/G2CDevelopmentMemory'/namespace('G2C.DEBUG.TRIP.environment|'+endpoint)
                        return {str(p.relative_to(base)):hashlib.sha256(p.read_bytes()).hexdigest() for root in base.glob(account+'*') if root.is_dir() for p in root.rglob('*') if p.is_file()}
                    files=with_container(collect)
                    with lock:actions=list(observed[case]['actions'])
                    return dict(item_http_status=current.status_code,item=current.json().get('item') if current.status_code==200 else None,
                        candidate_files={k:v for k,v in files.items() if k.startswith(account+'.candidate-v1')},memory_files=files,
                        action_count=len(actions),action_id=actions[-1]['command']['action_id'] if actions else None,
                        input_sha256=actions[-1]['input_sha256'] if actions else None,other_item_unchanged=True)
                class Control(BaseHTTPRequestHandler):
                    def log_message(self,*_):pass
                    def do_GET(self):
                        path=urlsplit(self.path);query={k:v[0] for k,v in parse_qs(path.query).items()}
                        if path.path=='/fixture':
                            case=query['case'];assert case in hosts;active['case']=case
                            profile=hosts[case]['profile']
                            launch=dict(G2C_DEV_ACCOUNT_MODE='1',G2C_DEV_API_BASE_URL=endpoint,G2C_DEV_ACCOUNTS='{}' if tls else json.dumps(tokens[case]),
                                G2C_DEV_OFFLINE_TRIP='last-sync-v1',G2C_DEV_CLEANUP_PROFILE='device-v4',G2C_DEV_TRAVEL_PROFILE=json.dumps(dict(version='app-travel.1',travel_ids=hosts[case]['travel_ids'])),
                                G2C_DEV_TYPED_MEMORY_PROFILE=json.dumps(dict(version='app-memory.2',**{k:profile[k] for k in ('subjects','slots','extents')})),
                                G2C_DEV_TYPED_MEMORY_URL=endpoint,G2C_DEV_MEMORY_CANDIDATE_URL=endpoint)
                            value=dict(bundle=BUNDLE,case_id=case,launch=launch,subjects=subjects[case],conversation=proofs[case]['conversation'],
                                original_text='我可能更喜欢轻松的行程节奏',edited_text='我确认偏好轻松节奏 / cafe\u0301，保留原中文',occurred_at='时间不详',
                                travel_id=proofs[case].get('travel_id'),travel_version=proofs[case].get('current_travel_version'))
                        elif path.path=='/size':
                            size={'standard':'large','max':'accessibility-extra-extra-extra-large'}[query['value']]
                            if not tls:subprocess.run(['xcrun','simctl','ui',args.simulator,'content_size',size],env=env,check=True)
                            value=dict(device_font_scope='actual system maximum throughout case') if tls else {}
                        elif path.path=='/observed-projection':
                            with lock:
                                pages=observed[active['case']]['projections'];assert pages
                                value=pages[0]
                        elif path.path=='/proof':value=proof_for(active['case'])
                        else:self.send_response(404);self.end_headers();return
                        data=packed(value);self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
                control_token=random_secrets.token_urlsafe(32) if tls else None;native=None
                def stage_input(request):
                    query=parse_qs(urlsplit(request).query)
                    if set(query)!={'case'} or query['case']!=[executing_case]:raise ValueError('Staging requires the active candidate case')
                    native.stage(case=query['case'][0])
                control=ThreadingHTTPServer((tls.host if tls else '127.0.0.1',0),
                    authenticated_control(Control,control_token,stage_input,lambda: executing_case) if tls else Control)
                if tls:tls.secure_http_server(control)
                threading.Thread(target=control.serve_forever,daemon=True).start()
                if not tls:original_size=subprocess.check_output(['xcrun','simctl','ui',args.simulator,'content_size'],env=env,text=True).strip()
                spec=importlib.util.spec_from_file_location('candidate_builder',ROOT/'scripts/check_ios_trip_confirm.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                builder=object.__new__(module.XCTestDriver);builder.directory=(device_project_root if tls else output)/'project';builder.directory.mkdir();builder.write_project(0)
                control_url=('https://'+tls.host if tls else 'http://127.0.0.1')+':'+str(control.server_port)
                (builder.directory/'G2CControl.swift').write_text((HERE/'MemoryCandidateUITests.swift').read_text().replace('__CONTROL_URL__',control_url))
                project=builder.directory/'G2CAcceptance.xcodeproj';pbx=project/'project.pbxproj';text=pbx.read_text().replace('space.go2china.foundation.local',BUNDLE).replace('space.go2china.foundation.control',BUNDLE+'.control')
                entitlement=builder.directory/'Candidate.entitlements';entitlement.write_bytes(plistlib.dumps({'application-identifier':BUNDLE,'keychain-access-groups':[BUNDLE]}))
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
                        selected=['MemoryCandidateUITests/'+test]
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
                            '-collect-test-diagnostics','never','ARCHS=arm64','ONLY_ACTIVE_ARCH=YES','CODE_SIGNING_ALLOWED=YES','CODE_SIGN_IDENTITY=-','-only-testing:G2CControl/MemoryCandidateUITests/'+test,'test']
                        run=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=1200)
                        log=run.stdout+run.stderr
                        for secret in secrets:log=log.replace(secret.decode(errors='replace'),'<redacted-local-credential>')
                        (output/(test+'.log')).write_text(log)
                        if run.returncode:report['cases'][test]='FAIL';save();run.check_returncode()
                        summary=json.loads(subprocess.check_output(['xcrun','xcresulttool','get','test-results','summary','--path',str(result)],env=env,text=True))
                        value={k:summary[k] for k in ('passedTests','failedTests','skippedTests')};assert value==dict(passedTests=1,failedTests=0,skippedTests=0)
                    proof=proof_for(case);assert proof['action_count']==1 and proof['other_item_unchanged']
                    if case=='account-en':assert not proof['candidate_files'] and not proof['memory_files'] and proof['item_http_status'] in (401,403)
                    else:assert proof['candidate_files'] and proof['item_http_status']==200
                    report.setdefault('proofs',{})[test]=proof;report.setdefault('results',{})[test]=value;report['cases'][test]='PASS';save()
                if args.prepare_only:report.update(status='PREPARED_EXECUTION_UNRUN',native='UNRUN')
                else:
                    def scan(container):
                        for path in [*container.rglob('*'),*output.rglob('*')]:
                            if path.is_file() and any(secret in path.read_bytes() for secret in secrets):raise AssertionError('credential leaked into candidate artifacts')
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
            report['api']={case:value['api'] for case,value in observed.items()}
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
                        if path.is_file() and not path.is_symlink():
                            if control_token.encode() in path.read_bytes():
                                report['status']='FAIL';save();raise AssertionError('control credential in evidence export')
                if thread and thread.is_alive():
                    report['status']='FAIL';save();raise RuntimeError('candidate host did not stop')
            if original_size:subprocess.run(['xcrun','simctl','ui',args.simulator,'content_size',original_size],env=env,check=True)
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
