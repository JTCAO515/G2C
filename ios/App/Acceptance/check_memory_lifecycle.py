"""#271 native lifecycle acceptance. Actual App, signed official local hosts,
private runtime PG and explicit operator run configuration; no backend overrides.
"""
import argparse
import asyncio
from datetime import datetime,timedelta,timezone
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
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import parse_qs

ROOT=Path(__file__).resolve().parents[3]; HERE=Path(__file__).resolve().parent
BUNDLE='space.go2china.memory-lifecycle.acceptance'
CASES=['testEnglish','testChineseLarge']
sys.path.insert(0,str(ROOT/'scripts'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--simulator',required=True);p.add_argument('--run-context',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--build-dir',type=Path,required=True)
    p.add_argument('--case',choices=CASES);args=p.parse_args()
    output=args.output.resolve();build=args.build_dir.resolve()
    if output.is_relative_to(ROOT) or build.is_relative_to(ROOT):raise ValueError('external evidence only')
    output.mkdir(parents=True)
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT):raise ValueError('commit candidate first')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    env={k:v for k,v in os.environ.items() if not k.startswith(('PG','LIBPQ','SIMCTL_CHILD_','G2C_DEV_','CJ_LOCAL_'))}
    for key in tuple(os.environ):
        if key.startswith(('PG','LIBPQ','CJ_LOCAL_')):os.environ.pop(key)
    env.update(CJ_ENV='local',DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer');os.environ['CJ_ENV']='local'
    import psycopg,uvicorn,dev_auth,migrate
    from pg_suites import cluster
    from fastapi.testclient import TestClient
    from cj_api.local_app import app_from_environment,LocalDatabase,ISSUER,scope_for,create_local_memory_management_app
    from cj_api.local_run_context import load_run_context
    from cj_memory.local import LocalMemoryConfiguration
    context=load_run_context(args.run_context)
    sources=[*list((ROOT/'ios/App').glob('*.swift')),*list((ROOT/'ios/Modules/CJMemoryClient/Sources').rglob('*.swift')),
        *list((ROOT/'ios/Modules/CJShell/Sources').rglob('*.swift')),*list((ROOT/'ios/Modules/CJMessageClient/Sources').rglob('*.swift')),
        Path(__file__),HERE/'DevelopmentMemoryLifecycleUITests.swift']
    report=dict(status='RUNNING',head=head,cases={},checks={},run_context=json.loads(args.run_context.read_text()),
        source_hashes={str(s.relative_to(ROOT)):hashlib.sha256(s.read_bytes()).hexdigest() for s in sources},
        git_trees={s:subprocess.check_output(['git','rev-parse',head+':'+s],cwd=ROOT,text=True).strip() for s in ('ios','backend','contracts','scripts')},
        unrun=['remaining lifecycle native cases','real accounts/models/fees/cloud','physical device/VoiceOver','deployment'])
    def save():(output/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
    save();tokens={};records={};audit=[]
    try:
        with tempfile.TemporaryDirectory(prefix='cj271-',dir='/tmp') as temporary:
            root=Path(temporary)
            with cluster('memorylifecycle',port=55771,role='cj271_initializer',root=root/'pg') as config:
                with psycopg.connect(**config,autocommit=True) as conn:
                    chain=migrate.load();migrate.up(conn,chain,chain[-1]['version'])
                connection=root/'connection.json';connection.write_text(json.dumps(config))
                subjects={case:{x:'cj271-'+uuid.uuid4().hex for x in ('A','B')} for case in CASES}
                auth=root/'auth';dev_auth.init(auth,[s for row in subjects.values() for s in row.values()])
                profile=dict(subjects=['self'],slots={slot:dict(kind=kind,collection_allowed=True,semantic_resolved=True) for slot,kind in (('fact','fact'),('experience','experience'),('food.spice','preference'))},extents=['long_term'],context_ids=[])
                policy=dict(version='local-memory-policy.1',expires_at=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),profiles={s:profile for row in subjects.values() for s in row.values()})
                policy_path=root/'memory-policy.json';policy_path.write_text(json.dumps(policy));policy_path.chmod(0o600)
                for target in (env,os.environ):target.update(CJ_LOCAL_CONNINFO=str(connection),CJ_LOCAL_AUTH_DIR=str(auth),CJ_LOCAL_RUN_CONTEXT=str(args.run_context.resolve()),CJ_LOCAL_MEMORY_POLICY=str(policy_path))
                database=LocalDatabase(connection,run_context=context)
                apps=dict(read=app_from_environment(),management=create_local_memory_management_app(conninfo_path=connection,auth_dir=auth,memory_configuration=LocalMemoryConfiguration.from_bytes(policy_path.read_bytes())))
                servers=[];threads=[];endpoints={}
                def observer(name,app):
                    async def observed(scope,receive,send):
                        if scope['type']!='http':return await app(scope,receive,send)
                        incoming=[];captured=[]
                        async def read():
                            message=await receive()
                            if message['type']=='http.request':incoming.append(message.get('body',b''))
                            return message
                        async def capture(message):captured.append(message)
                        await app(scope,read,capture)
                        bearer=dict(scope['headers']).get(b'authorization',b'').decode()
                        case=next((c for c,pair in tokens.items() if bearer=='Bearer '+pair['A']),None)
                        raw=b''.join(incoming);status=captured[0]['status']
                        entry=dict(host=name,method=scope['method'],path=scope['path'],query=parse_qs(scope.get('query_string',b'').decode()),status=status,case=case)
                        if raw:
                            entry['sha256']=hashlib.sha256(raw).hexdigest()
                            if case and scope['method']=='POST':records[case]['posts'].append(dict(entry,original=json.loads(raw)))
                        audit.append(entry)
                        for message in captured:await send(message)
                    return observed
                for name,app in apps.items():
                    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
                    endpoints[name]=f'http://127.0.0.1:{port}'
                    server=uvicorn.Server(uvicorn.Config(observer(name,app),host='127.0.0.1',port=port,log_level='critical',access_log=False))
                    thread=threading.Thread(target=server.run,daemon=True);thread.start();servers.append(server);threads.append(thread)
                    deadline=time.monotonic()+10
                    while not server.started:
                        if not thread.is_alive() or time.monotonic()>deadline:raise RuntimeError('official host startup failed')
                        time.sleep(.02)
                def operator(subject,*arguments):
                    subprocess.run([sys.executable,'-B',str(ROOT/'scripts/local_run_context.py'),'--conninfo-json',str(connection),'--auth-dir',str(auth),'--run-context',str(args.run_context.resolve()),'--subject',subject,*arguments],env=env,stdout=subprocess.DEVNULL,check=True)
                def prepare(case):
                    tokens[case]={x:dev_auth.token(auth,s,120) for x,s in subjects[case].items()}
                    for s in subjects[case].values():operator(s,'init-budget')
                    row=records[case]=dict(posts=[],initial=[],audit_start=len(audit))
                    headers={'Authorization':'Bearer '+tokens[case]['A']}
                    with TestClient(apps['read']) as api:
                        for kind in ('fact','experience','preference'):
                            command=dict(operation_id=uuid.uuid4().hex,item_id=uuid.uuid4().hex,subject='self',slot='food.spice' if kind=='preference' else kind,kind=kind,
                                text='Synthetic '+kind+' / 合成原始'+kind,occurred_at='Synthetic date unknown / 合成时间不详',extent='long_term',context_id=None)
                            response=api.post('/v1/memories',content=json.dumps(command,ensure_ascii=False).encode(),headers={**headers,'Content-Type':'application/octet-stream'});response.raise_for_status()
                            response=api.get('/v1/memory-items',params={'item_id':command['item_id']},headers=headers);response.raise_for_status();item=response.json()['item']
                            row['initial'].append(item)
                    scope=scope_for(ISSUER,subjects[case]['A'])
                    with database.connect(scope) as conn:
                        row['original_sources']={s:hashlib.sha256(bytes(raw)).hexdigest() for s,raw in conn.execute('SELECT source_id,approved_input FROM cj_memory_source WHERE scope=%s',(scope,))}
                    return dict(endpoint=endpoints['read'],management_endpoint=endpoints['management'],accounts=tokens[case],subjects=subjects[case],profile=json.dumps(profile),case_id=case,initial=row['initial'])
                def snapshot(case,item_id):
                    with TestClient(apps['read']) as api:
                        response=api.get('/v1/memory-items',params={'item_id':item_id},headers={'Authorization':'Bearer '+tokens[case]['A']});response.raise_for_status();return response.json()['item']
                def verify(case):
                    row=records[case];scope=scope_for(ISSUER,subjects[case]['A']);posts=row['posts'];expected=7 if case=='testEnglish' else 1
                    assert len(posts)==expected and all(p['host']=='management' and p['status']==200 for p in posts)
                    assert not any(a['method']=='POST' and a['case'] is None for a in audit[row['audit_start']:])
                    with database.connect(scope) as conn:
                        assert conn.execute('SELECT current_user').fetchone()[0]=='cj_m1_runtime'
                        ledger=conn.execute('SELECT action_id,operation,original_input,item_id,version,status FROM cj_memory_management_action WHERE scope=%s',(scope,)).fetchall()
                        assert len(ledger)==expected
                        for aid,op,raw,iid,version,status in ledger:
                            post=next(p for p in posts if p['original']['action_id']==aid)
                            assert hashlib.sha256(bytes(raw)).hexdigest()==post['sha256'] and iid==post['original']['item_id'] and version==post['original']['expected_version']+1
                            assert post['original']['expected_source_version']>0
                        sources=conn.execute('SELECT source_id,approved_input,active FROM cj_memory_source WHERE scope=%s',(scope,)).fetchall()
                        for sid,sha in row['original_sources'].items():assert next(hashlib.sha256(bytes(raw)).hexdigest() for s,raw,_ in sources if s==sid)==sha
                        assert conn.execute('SELECT count(*) FROM cj_memory_operation WHERE scope=%s',(scope,)).fetchone()[0]==3
                        if case=='testEnglish':
                            withdrawn=next(i for i in row['initial'] if i['command']['kind']=='preference')['command']['item_id']
                            history=conn.execute("SELECT withdrawal_history FROM cj_memory_management_action WHERE scope=%s AND item_id=%s AND operation='withdraw'",(scope,withdrawn)).fetchone()[0]
                            assert len(history)==2
                            for source in history:assert not next(active for sid,_,active in sources if sid==source['source_id'])
                    with TestClient(apps['read']) as api:
                        for item in row['initial']:
                            denied=api.get('/v1/memory-items',params={'item_id':item['command']['item_id']},headers={'Authorization':'Bearer '+tokens[case]['B']});denied.raise_for_status();assert denied.json()['item'] is None
                    value=dict(runtime_role='cj_m1_runtime',posts=posts,ledger=[dict(action_id=a,operation=op,item_id=i,version=v,status=s) for a,op,_,i,v,s in ledger],original_sources_unchanged=True,cross_owner_empty=True,
                        items=[snapshot(case,i['command']['item_id']) for i in row['initial']])
                    report['checks'][case]=value;save();return value
                class Control(BaseHTTPRequestHandler):
                    def log_message(self,*args):pass
                    def do_GET(self):
                        try:
                            query=parse_qs(self.path.split('?',1)[1]);path=self.path.split('?',1)[0];case=query['case'][0]
                            if path=='/prepare':value=prepare(case)
                            elif path=='/snapshot':value=snapshot(case,query['item_id'][0])
                            elif path=='/verify':value=verify(case)
                            else:raise ValueError('unknown control route')
                            raw=json.dumps(value).encode();self.send_response(200);self.end_headers();self.wfile.write(raw)
                        except Exception as error:
                            import traceback
                            report.setdefault('control_errors',[]).append(dict(type=type(error).__name__,frames=[dict(function=f.name,line=f.lineno) for f in traceback.extract_tb(error.__traceback__)]));save()
                            self.send_response(500);self.end_headers();self.wfile.write(type(error).__name__.encode())
                control=ThreadingHTTPServer(('127.0.0.1',0),Control);threading.Thread(target=control.serve_forever,daemon=True).start()
                try:
                    spec=importlib.util.spec_from_file_location('trip_builder',ROOT/'scripts/check_ios_trip_confirm.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                    builder=object.__new__(module.XCTestDriver);builder.directory=output/'project';builder.directory.mkdir();builder.write_project(0)
                    (builder.directory/'G2CControl.swift').write_text((HERE/'DevelopmentMemoryLifecycleUITests.swift').read_text().replace('__FIXTURE_URL__',f'http://127.0.0.1:{control.server_port}'))
                    project=builder.directory/'G2CAcceptance.xcodeproj';pbx=project/'project.pbxproj';text=pbx.read_text().replace('space.go2china.foundation.local',BUNDLE).replace('space.go2china.foundation.control',BUNDLE+'.control')
                    entitlements=builder.directory/'Lifecycle.entitlements';entitlements.write_bytes(plistlib.dumps({'application-identifier':BUNDLE,'keychain-access-groups':[BUNDLE]}));text=text.replace(json.dumps(str(ROOT/'ios/App/Development.entitlements')),json.dumps(str(entitlements)));pbx.write_text(text)
                    for case in ([args.case] if args.case else CASES):
                        if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT):raise RuntimeError('candidate changed')
                        result=output/(case+'.xcresult')
                        command=['xcodebuild','-project',str(project),'-scheme','G2CControl','-configuration','Debug','-destination','platform=iOS Simulator,id='+args.simulator,'-derivedDataPath',str(build),'-resultBundlePath',str(result),'-scmProvider','system','-skipPackageUpdates','-onlyUsePackageVersionsFromResolvedFile','-parallel-testing-enabled','NO','-collect-test-diagnostics','never','ARCHS=arm64','ONLY_ACTIVE_ARCH=YES','CODE_SIGNING_ALLOWED=YES','CODE_SIGN_IDENTITY=-','-only-testing:G2CControl/DevelopmentMemoryLifecycleUITests/'+case,'test']
                        print('Memory lifecycle: '+case,flush=True);run=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=1800)
                        log=run.stdout+run.stderr
                        for pair in tokens.values():
                            for token in pair.values():log=log.replace(token,'<redacted-local-token>')
                        (output/(case+'.log')).write_text(log)
                        summary=json.loads(subprocess.check_output(['xcrun','xcresulttool','get','test-results','summary','--path',str(result)],text=True));report.setdefault('results',{})[case]={k:summary[k] for k in ('passedTests','failedTests','skippedTests')};save();run.check_returncode()
                        assert summary['passedTests']==1 and summary['failedTests']==summary['skippedTests']==0;report['cases'][case]='PASS';save()
                    container=Path(subprocess.check_output(['xcrun','simctl','get_app_container',args.simulator,BUNDLE,'data'],text=True).strip())
                    for file in [*container.rglob('*'),*output.rglob('*')]:
                        if file.is_file():
                            raw=file.read_bytes();assert not any(token.encode() in raw for pair in tokens.values() for token in pair.values());assert b'-----BEGIN PRIVATE KEY-----' not in raw
                    report['token_key_scan']='PASS';report['status']='PARTIAL_PASS'
                finally:
                    for server in servers:server.should_exit=True
                    for thread in threads:thread.join(10)
                    control.shutdown();control.server_close()
    except BaseException as error:report['status']='FAIL';report['error']=type(error).__name__;raise
    finally:save()
    print(json.dumps(dict(status=report['status'],head=head,cases=report['cases']),indent=2))

if __name__=='__main__':main()
