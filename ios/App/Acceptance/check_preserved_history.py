"""#468 actual retained formal history: signed API/private PG/worker/Fake/App.

Preparation-only reports source PASS and native UNRUN. Native PASS requires
the real App, actual system maximum type and unfiltered accessibility audits.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
BUNDLE='space.go2china.preserved-history.acceptance'
CASES=['testErasedHistoryEnglish','testErasedHistoryChinese']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend-source',type=Path,required=True)
    parser.add_argument('--backend-head',required=True)
    parser.add_argument('--run-context',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--build-dir',type=Path,required=True)
    parser.add_argument('--simulator',required=True)
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args();backend=args.backend_source.resolve();output=args.output.resolve();build=args.build_dir.resolve()
    for path in (output,build):
        if path.is_relative_to(ROOT) or path.is_relative_to(backend):raise ValueError('external artifact roots required')
    output.mkdir(parents=True)
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT):raise ValueError('commit candidate first')
    if subprocess.check_output(['git','status','--porcelain'],cwd=backend):raise ValueError('clean backend pin required')
    if subprocess.check_output(['git','rev-parse','HEAD'],cwd=backend,text=True).strip()!=args.backend_head:raise ValueError('backend pin mismatch')
    env={k:v for k,v in os.environ.items() if not k.startswith(('PG','LIBPQ','SIMCTL_CHILD_','G2C_DEV_','CJ_LOCAL_'))}
    env.update(CJ_ENV='local',OS_ACTIVITY_MODE='disable',DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer')
    for key in tuple(os.environ):
        if key.startswith(('PG','LIBPQ','CJ_LOCAL_')):os.environ.pop(key)
    os.environ['CJ_ENV']='local'
    sys.path[:0]=[str(backend/'scripts'),str(backend/'backend'),*sorted(str(p) for p in (backend/'backend').iterdir() if p.is_dir())]
    import psycopg,uvicorn,dev_auth,migrate,local_run_context
    from pg_suites import cluster
    from cj_api.local_run_context import load_run_context
    from prepare_preserved_history_source import prepare_preserved_history
    context=load_run_context(args.run_context)
    assert context.current.meter.budget==4,'explicit bounded four-call source profile required'
    sources=[Path(__file__),HERE/'prepare_preserved_history_source.py',HERE/'PreservedHistoryUITests.swift',*list((ROOT/'ios/App').glob('*.swift'))]
    for module in ('CJShell','CJMessageClient','CJRunClient','CJAuth','CJTripClient','CJMemoryClient'):
        sources+=list((ROOT/'ios/Modules'/module/'Sources').rglob('*.swift'))
    report=dict(status='RUNNING',source_status='UNRUN',native='UNRUN',head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        backend_head=args.backend_head,cases={},source_hashes={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
        unrun=['full App erasure action/local per-item cleanup','physical device/VoiceOver/real provider/cloud/fees/backups'])
    def save():(output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    save();server=None;control=None;thread=None;secrets=[];audits=[];lock=threading.Lock()
    try:
        with tempfile.TemporaryDirectory(prefix='cj468-human-',dir='/tmp') as temp:
            folder=Path(temp)
            with cluster('preserved468',port=55851,role='cj468_initializer',root=folder/'pg') as config:
                with psycopg.connect(**config,autocommit=True) as conn:
                    chain=migrate.load();migrate.up(conn,chain,chain[-1]['version'])
                connection=folder/'connection.json';connection.write_text(json.dumps(config));connection.chmod(0o600)
                subjects={k:'cj468-'+uuid.uuid4().hex for k in ('A','B')}
                auth=folder/'auth';dev_auth.init(auth,list(subjects.values()))
                tokens={k:dev_auth.token(auth,subject,120) for k,subject in subjects.items()};secrets.extend(tokens.values())
                for subject in subjects.values():local_run_context.provision_budget(connection,context,subject)
                app,source=prepare_preserved_history(connection,auth,context,subjects,tokens,folder,backend/'backend/storage-registry.json')
                report.update(source_status='PASS',source=source);save()
                if args.prepare_only:
                    report.update(status='UNRUN',native='UNRUN');return
                async def observed(scope,receive,send):
                    if scope['type']=='http':
                        with lock:audits.append(dict(method=scope['method'],path=scope['path']))
                    await app(scope,receive,send)
                server=uvicorn.Server(uvicorn.Config(observed,host='127.0.0.1',port=0,log_level='error',access_log=False))
                import socket,time
                listener=socket.socket();listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
                thread=threading.Thread(target=lambda:server.run(sockets=[listener]),daemon=True);thread.start()
                deadline=time.monotonic()+10
                while not server.started:
                    if not thread.is_alive() or time.monotonic()>deadline:raise RuntimeError('formal history host unavailable')
                    time.sleep(.02)
                original_size=subprocess.check_output(['xcrun','simctl','ui',args.simulator,'content_size'],env=env,text=True).strip()
                class Control(BaseHTTPRequestHandler):
                    def log_message(self,*_):pass
                    def do_GET(self):
                        path=urlsplit(self.path);query={k:v[0] for k,v in parse_qs(path.query).items()}
                        if path.path=='/fixture':value=dict(endpoint='http://127.0.0.1:'+str(port),accounts=tokens,subjects=subjects,**source)
                        elif path.path=='/size':
                            assert query['value']=='max'
                            subprocess.run(['xcrun','simctl','ui',args.simulator,'content_size','accessibility-extra-extra-extra-large'],env=env,check=True)
                            value={'status':'configured'}
                        else:self.send_response(404);self.end_headers();return
                        raw=json.dumps(value).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(raw)
                control=ThreadingHTTPServer(('127.0.0.1',0),Control);threading.Thread(target=control.serve_forever,daemon=True).start()
                spec=importlib.util.spec_from_file_location('preserved_builder',ROOT/'scripts/check_ios_trip_confirm.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                builder=object.__new__(module.XCTestDriver);builder.directory=output/'project';builder.directory.mkdir();builder.write_project(0)
                (builder.directory/'G2CControl.swift').write_text((HERE/'PreservedHistoryUITests.swift').read_text().replace('__CONTROL_URL__','http://127.0.0.1:'+str(control.server_port)))
                project=builder.directory/'G2CAcceptance.xcodeproj';pbx=project/'project.pbxproj';text=pbx.read_text().replace('space.go2china.foundation.local',BUNDLE).replace('space.go2china.foundation.control',BUNDLE+'.control')
                entitlement=builder.directory/'Human.entitlements';entitlement.write_bytes(plistlib.dumps({'application-identifier':BUNDLE,'keychain-access-groups':[BUNDLE]}))
                pbx.write_text(text.replace(json.dumps(str(ROOT/'ios/App/Development.entitlements')),json.dumps(str(entitlement))))
                for case in CASES:
                    report['cases'][case]='RUNNING';save();result=output/(case+'.xcresult')
                    command=['xcodebuild','-project',str(project),'-scheme','G2CControl','-configuration','Debug','-destination','platform=iOS Simulator,id='+args.simulator,
                        '-derivedDataPath',str(build),'-resultBundlePath',str(result),'-skipPackageUpdates','-onlyUsePackageVersionsFromResolvedFile',
                        '-parallel-testing-enabled','NO','-collect-test-diagnostics','never','ARCHS=arm64','ONLY_ACTIVE_ARCH=YES','CODE_SIGNING_ALLOWED=YES','CODE_SIGN_IDENTITY=-',
                        '-only-testing:G2CControl/PreservedHistoryUITests/'+case,'test']
                    run=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=1200)
                    log=run.stdout+run.stderr
                    for secret in secrets:log=log.replace(secret,'<redacted-local-credential>')
                    (output/(case+'.log')).write_text(log)
                    if run.returncode:report['cases'][case]='FAIL';save();run.check_returncode()
                    summary=json.loads(subprocess.check_output(['xcrun','xcresulttool','get','test-results','summary','--path',str(result)],env=env,text=True))
                    value={k:summary[k] for k in ('passedTests','failedTests','skippedTests')};assert value==dict(passedTests=1,failedTests=0,skippedTests=0)
                    report.setdefault('results',{})[case]=value;report['cases'][case]='PASS';save()
                assert not any(a['method'] not in ('GET','HEAD') for a in audits),'read-only App created a write'
                assert sum(a['path']=='/v5/message-history' for a in audits)>=2 and sum(a['path']=='/v6/run-display' for a in audits)>=2
                container=Path(subprocess.check_output(['xcrun','simctl','get_app_container',args.simulator,BUNDLE,'data'],env=env,text=True).strip())
                for path in [*container.rglob('*'),*output.rglob('*')]:
                    if path.is_file() and any(secret.encode() in path.read_bytes() for secret in secrets):raise AssertionError('credential leaked into human history artifacts')
                report.update(status='PASS',native='PASS',api=audits,credential_scan='PASS')
        report.update(pg_stopped=True,task_credentials_destroyed=True)
    except BaseException as error:
        report.update(status='FAIL',error_type=type(error).__name__);raise
    finally:
        if control:control.shutdown();control.server_close()
        if server:server.should_exit=True
        if thread:thread.join(timeout=10)
        if 'original_size' in locals():subprocess.run(['xcrun','simctl','ui',args.simulator,'content_size',original_size],env=env,check=True)
        if args.prepare_only and report.get('source_status')=='PASS':report.update(pg_stopped=True,task_credentials_destroyed=True)
        save()


if __name__=='__main__':main()
