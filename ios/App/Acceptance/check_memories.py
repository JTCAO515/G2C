"""#228 native manual-memory acceptance on signed local API + private PG.

No contract overrides, quota injection, fake HTTP refusal, real provider or cloud.
The only lost-response case truncates an actual committed server response.
"""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BUNDLE = 'space.go2china.memory.acceptance'
CASES = ['testEnglish', 'testChineseLargeText', 'testUnknownReopen', 'testRejected', 'testSkipAndChat', 'testReleaseClosed']
sys.path.insert(0, str(ROOT / 'scripts'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulator', required=True)
    parser.add_argument('--run-context', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--build-dir', type=Path, required=True)
    parser.add_argument('--case', choices=CASES)
    args = parser.parse_args()
    output, build = args.output.resolve(), args.build_dir.resolve()
    if output.is_relative_to(ROOT) or build.is_relative_to(ROOT): raise ValueError('External evidence only')
    output.mkdir(parents=True)  # Preserve every earlier result, including FAIL.
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT): raise ValueError('Commit candidate before native acceptance')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    env = {k: v for k, v in os.environ.items() if not k.startswith(('SIMCTL_CHILD_', 'G2C_DEV_', 'PG', 'LIBPQ'))}
    env.update(CJ_ENV='local', DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer')
    os.environ['CJ_ENV'] = 'local'
    import psycopg
    import uvicorn
    import dev_auth
    import migrate
    from pg_suites import cluster
    from fastapi.testclient import TestClient
    from cj_api.local_app import app_from_environment, LocalDatabase, ISSUER, scope_for
    from cj_api.local_run_context import load_run_context
    from cj_agent.provider import FakeProvider
    from run_worker import run_once
    context = load_run_context(args.run_context)
    report = dict(status='RUNNING', head=head, cases={}, checks={}, unrun=['#227 effective context', 'cloud/real model/fees', 'device/VoiceOver', 'deployment'],
        run_context=json.loads(args.run_context.read_text()), source_hashes={})
    sources = [*list((ROOT/'ios/App').glob('*.swift')), *list((ROOT/'ios/Modules/CJMemoryClient/Sources').rglob('*.swift')),
               *list((ROOT/'ios/Modules/CJShell/Sources').rglob('*.swift')), Path(__file__), HERE/'DevelopmentMemoryUITests.swift']
    report['source_hashes'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    def save(): (output/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    save()
    tokens = {}
    audit = []
    try:
        with tempfile.TemporaryDirectory(prefix='cj228-', dir='/tmp') as temporary:
            root = Path(temporary)
            with cluster('memoryui', port=55628, role='cj228_initializer', root=root/'pg') as config:
                with psycopg.connect(**config, autocommit=True) as conn:
                    chain = migrate.load(); migrate.up(conn, chain, chain[-1]['version'])
                connection = root/'connection.json'; connection.write_text(json.dumps(config))
                subjects = {case: {a: 'cj228-'+uuid.uuid4().hex for a in ('A','B')} for case in CASES}
                auth = root/'auth'; dev_auth.init(auth, [s for row in subjects.values() for s in row.values()])
                profile = dict(subjects=['self'], slots={
                    'fact':dict(kind='fact',collection_allowed=True,semantic_resolved=True),
                    'experience':dict(kind='experience',collection_allowed=True,semantic_resolved=True),
                    'food.spice':dict(kind='preference',collection_allowed=True,semantic_resolved=True),
                    'ambiguous':dict(kind='fact',collection_allowed=True,semantic_resolved=False),
                    'blocked':dict(kind='fact',collection_allowed=False,semantic_resolved=True)},
                    extents=['long_term'],context_ids=[])
                policy = dict(version='local-memory-policy.1',expires_at=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),
                              profiles={s:profile for row in subjects.values() for s in row.values()})
                policy_path=root/'memory-policy.json'; policy_path.write_text(json.dumps(policy)); policy_path.chmod(0o600)
                for target in (env, os.environ): target.update(CJ_LOCAL_CONNINFO=str(connection),CJ_LOCAL_AUTH_DIR=str(auth),
                    CJ_LOCAL_RUN_CONTEXT=str(args.run_context.resolve()),CJ_LOCAL_MEMORY_POLICY=str(policy_path))
                database = LocalDatabase(connection, run_context=context)
                app = app_from_environment()
                records, errors, requests = {}, [], []
                stop=threading.Event(); lock=threading.Lock()
                model=FakeProvider(chunks_per_reply=2)
                def worker():
                    try:
                        while not stop.is_set(): run_once(database, model, auth); stop.wait(.05)
                    except Exception as error: errors.append(type(error).__name__); stop.set()
                worker_thread=threading.Thread(target=worker,daemon=True); worker_thread.start()
                async def observed(scope, receive, send):
                    if scope['type']!='http': return await app(scope,receive,send)
                    method,path=scope['method'],scope['path']; requests.append((method,path))
                    original=bytearray()
                    async def observed_receive():
                        message=await receive()
                        if message['type']=='http.request': original.extend(message.get('body',b''))
                        return message
                    captured=[]
                    async def capture(message): captured.append(message)
                    await app(scope,observed_receive,capture)
                    status=captured[0]['status']
                    body=b''.join(m.get('body',b'') for m in captured[1:])
                    audit.append(dict(method=method,path=path,status=status,query=parse_qs(scope.get('query_string',b'').decode()),input_sha256=hashlib.sha256(original).hexdigest(),response_sha256=hashlib.sha256(body).hexdigest()))
                    case=None
                    if method=='POST' and path=='/v1/memories':
                        auth_header=dict(scope['headers']).get(b'authorization',b'').decode()
                        case=next((c for c,row in tokens.items() if auth_header=='Bearer '+row['A']),None)
                        records[case]['posts'].append(bytes(original))
                    if case=='testUnknownReopen' and status==200:
                        await send(captured[0])
                        raise RuntimeError('controlled loss after real committed MEMORY response')
                    for message in captured: await send(message)
                with socket.socket() as sock: sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
                endpoint=f'http://127.0.0.1:{port}'
                server=uvicorn.Server(uvicorn.Config(observed,host='127.0.0.1',port=port,log_level='critical',access_log=False))
                api_thread=threading.Thread(target=server.run,daemon=True); api_thread.start()
                deadline=time.monotonic()+10
                while not server.started:
                    if not api_thread.is_alive() or time.monotonic()>deadline: raise RuntimeError('signed API unavailable')
                    time.sleep(.02)
                def proof(case,stage):
                    row=records[case]; scope=scope_for(ISSUER,subjects[case]['A'])
                    with database.connect(scope) as conn:
                        role=conn.execute('SELECT current_user').fetchone()[0]
                        operations=conn.execute('SELECT operation_id,item_id,original_input,version,status FROM cj_memory_operation WHERE scope=%s ORDER BY operation_id',(scope,)).fetchall()
                    assert role=='cj_m1_runtime'
                    expected={'three-saves':3,'reopen':3,'unknown-reopen':1,'rejected':0,'skip':0,'release':0}[stage]
                    assert len(operations)==expected
                    posts=row['posts']
                    assert len(posts)==(1 if stage=='rejected' else expected)
                    originals={p:hashlib.sha256(p).hexdigest() for p in posts}
                    items=[]
                    for oid,iid,raw,version,status in operations:
                        raw=bytes(raw); assert raw in originals and version==1 and status=='active'
                        command=json.loads(raw); assert command['operation_id']==oid and command['item_id']==iid
                        with database.connect(scope) as conn:
                            item_raw,item_version,item_status=conn.execute('SELECT original_input,version,status FROM cj_memory_item WHERE scope=%s AND item_id=%s',(scope,iid)).fetchone()
                        item=json.loads(bytes(item_raw))
                        assert all(item[k]==v for k,v in command.items())
                        assert item['source_id']=='manual-v1:'+hashlib.sha256(raw).hexdigest() and item['source_version']==1
                        assert item_version==version and item_status==status
                        items.append(dict(slot=item['slot'],source_id=item['source_id']))
                    current=[dict(operation_id=o,item_id=i,sha256=hashlib.sha256(bytes(raw)).hexdigest(),version=v,status=s) for o,i,raw,v,s in operations]
                    if 'baseline' in row: assert row['baseline']==current
                    else: row['baseline']=current
                    foreign=[]
                    with TestClient(app) as client:
                        for oid,iid,*_ in operations:
                            for path,query in [('/v1/memory-receipts',{'operation_id':oid}),('/v1/memory-items',{'item_id':iid})]:
                                response=client.get(path,params=query,headers={'Authorization':'Bearer '+tokens[case]['B']})
                                assert response.status_code!=200 or all(v is None for k,v in response.json().items() if k in ('item','receipt'))
                                assert not any(json.loads(bytes(raw))['text'] in response.text for _,_,raw,*_ in operations)
                                foreign.append(dict(path=path,status=response.status_code))
                    if stage=='reopen':
                        native=[a['query']['operation_id'][0] for a in audit if a['path']=='/v1/memory-receipts'][-3:]
                        assert len(native)==3 and set(native)=={o for o,*_ in operations}
                    if stage=='skip':
                        deadline=time.monotonic()+15
                        while model.calls<1 and time.monotonic()<deadline: time.sleep(.05)
                        assert model.calls>=1
                    if stage=='release': assert len(requests)==row['request_start']
                    value=dict(runtime_role=role,operations=current,items=items,posts=len(posts),foreign_reads=foreign,provider_calls=model.calls)
                    report['checks'][case+'-'+stage]=value; save(); return value
                class Control(BaseHTTPRequestHandler):
                    def log_message(self,*args): pass
                    def do_GET(self):
                        try:
                            query=parse_qs(urlsplit(self.path).query)
                            if urlsplit(self.path).path=='/prepare':
                                mode=query['mode'][0]
                                case={'success': query.get('case',['testEnglish'])[0],
                                      'unknown':'testUnknownReopen','rejected':'testRejected','skip':'testSkipAndChat','release':'testReleaseClosed'}[mode]
                                tokens[case]={a:dev_auth.token(auth,s,120) for a,s in subjects[case].items()}
                                for subject in subjects[case].values():
                                    command=[sys.executable,'-B',str(ROOT/'scripts/local_run_context.py'),'--conninfo-json',str(connection),
                                        '--auth-dir',str(auth),'--run-context',str(args.run_context.resolve()),'--subject',subject,'init-budget']
                                    result=subprocess.run(command,env=env,capture_output=True,text=True); result.check_returncode()
                                conversation='memory-'+uuid.uuid4().hex
                                with TestClient(app) as client:
                                    client.put('/v1/conversations',params={'conversation_id':conversation},headers={'Authorization':'Bearer '+tokens[case]['A']}).raise_for_status()
                                records[case]=dict(posts=[],request_start=len(requests))
                                display=json.loads(json.dumps(profile))
                                if mode=='rejected': display['slots']['blocked']['collection_allowed']=True
                                value=dict(endpoint=endpoint,accounts=tokens[case],subjects=subjects[case],case_id=case,conversation=conversation,profile=json.dumps(display))
                            elif urlsplit(self.path).path=='/verify': value=proof(query['case'][0],query['stage'][0])
                            else: raise ValueError('unknown control route')
                            body=json.dumps(value).encode(); self.send_response(200); self.end_headers(); self.wfile.write(body)
                        except Exception as error:
                            report['control_error']=type(error).__name__; save()
                            self.send_response(500); self.end_headers(); self.wfile.write(type(error).__name__.encode())
                control=ThreadingHTTPServer(('127.0.0.1',0),Control)
                threading.Thread(target=control.serve_forever,daemon=True).start()
                try:
                    spec=importlib.util.spec_from_file_location('trip_acceptance',ROOT/'scripts/check_ios_trip_confirm.py')
                    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                    builder=object.__new__(module.XCTestDriver); builder.directory=output/'project'; builder.directory.mkdir(); builder.write_project(0)
                    (builder.directory/'G2CControl.swift').write_text((HERE/'DevelopmentMemoryUITests.swift').read_text().replace('__FIXTURE_URL__',f'http://127.0.0.1:{control.server_port}'))
                    project=builder.directory/'G2CAcceptance.xcodeproj'; pbx=project/'project.pbxproj'
                    text=pbx.read_text().replace('space.go2china.foundation.local',BUNDLE).replace('space.go2china.foundation.control',BUNDLE+'.control')
                    entitlements=builder.directory/'Development.entitlements'; entitlements.write_bytes(plistlib.dumps({'application-identifier':BUNDLE,'keychain-access-groups':[BUNDLE]}))
                    text=text.replace(json.dumps(str(ROOT/'ios/App/Development.entitlements')),json.dumps(str(entitlements)))
                    line=next(l for l in text.splitlines() if l.startswith('A00000000000000000000004 = {isa = XCBuildConfiguration; name = Debug;'))
                    text=text.replace(line,line+'\n'+line.replace('A00000000000000000000004','A0000000000000000000000C',1).replace('name = Debug;','name = Release;',1)).replace('buildConfigurations = (A00000000000000000000004);','buildConfigurations = (A00000000000000000000004, A0000000000000000000000C);')
                    pbx.write_text(text)
                    cases=[args.case] if args.case else CASES
                    for case in cases:
                        if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT): raise RuntimeError('candidate changed')
                        result=output/(case+'.xcresult'); configuration='Release' if case=='testReleaseClosed' else 'Debug'
                        command=['xcodebuild','-project',str(project),'-scheme','G2CControl','-configuration',configuration,
                            '-destination','platform=iOS Simulator,id='+args.simulator,'-derivedDataPath',str(build),'-resultBundlePath',str(result),
                            '-scmProvider','system','-skipPackageUpdates','-onlyUsePackageVersionsFromResolvedFile','-parallel-testing-enabled','NO',
                            '-collect-test-diagnostics','never','ARCHS=arm64','ONLY_ACTIVE_ARCH=YES','CODE_SIGNING_ALLOWED=YES','CODE_SIGN_IDENTITY=-',
                            '-only-testing:G2CControl/DevelopmentMemoryUITests/'+case,'test']
                        print('Native memory: '+case,flush=True)
                        run=subprocess.run(command,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=1200)
                        log=run.stdout
                        for row in tokens.values():
                            for token in row.values(): log=log.replace(token,'<redacted-local-token>')
                        (output/(case+'.log')).write_text(log); run.check_returncode()
                        summary=json.loads(subprocess.check_output(['xcrun','xcresulttool','get','test-results','summary','--path',str(result)],env=env))
                        (output/(case+'-summary.json')).write_text(json.dumps(summary,indent=2))
                        assert summary['passedTests']==1 and summary['failedTests']==0 and summary['skippedTests']==0
                        report['cases'][case]='PASS'; save()
                    assert not errors
                    report['worker_errors']=errors
                    container=Path(subprocess.check_output(['xcrun','simctl','get_app_container',args.simulator,BUNDLE,'data'],env=env,text=True).strip())
                    for path in container.rglob('*'):
                        if path.is_file():
                            raw=path.read_bytes()
                            assert not any(token.encode() in raw for row in tokens.values() for token in row.values())
                    report['app_file_token_scan']='PASS'
                    report['status']='PARTIAL_PASS' if args.case else 'PASS'
                finally:
                    stop.set(); worker_thread.join(10); server.should_exit=True; api_thread.join(10); control.shutdown()
    except BaseException as error:
        report['status']='FAIL'; report['error']=type(error).__name__; raise
    finally:
        report['api_audit']=audit
        save()
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
