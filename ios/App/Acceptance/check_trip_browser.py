"""#21 independent formal-Trip browser, not PLACE/map/time/assistant integration.

Every formal record is made through signed MESSAGE -> formal run_once/FakeProvider
-> signed Trip confirmation/action. No DB-injected Trip or manufactured refusal.
"""
import argparse
import asyncio
import base64
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

ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
BUNDLE='space.go2china.trip-browser.acceptance'
CASES=['testEnglish','testChineseLarge','testAccountLateRead']
sys.path.insert(0,str(ROOT/'scripts'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--simulator',required=True);p.add_argument('--run-context',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path);p.add_argument('--build-dir',required=True,type=Path)
    p.add_argument('--case',choices=CASES);args=p.parse_args()
    output=args.output.resolve();build=args.build_dir.resolve()
    if output.is_relative_to(ROOT) or build.is_relative_to(ROOT):raise ValueError('external evidence only')
    output.mkdir(parents=True)
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT):raise ValueError('commit candidate first')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    env={k:v for k,v in os.environ.items() if not k.startswith(('PG','LIBPQ','SIMCTL_CHILD_','G2C_DEV_','CJ_LOCAL_'))}
    env.update(CJ_ENV='local',DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer')
    for key in tuple(os.environ):
        if key.startswith(('PG','LIBPQ','CJ_LOCAL_')): os.environ.pop(key)
    os.environ['CJ_ENV']='local'
    import psycopg,uvicorn,dev_auth,migrate
    from pg_suites import cluster
    from fastapi.testclient import TestClient
    from cj_api.local_app import app_from_environment,LocalDatabase,ISSUER,scope_for
    from cj_api.local_run_context import load_run_context
    from cj_agent.provider import FakeProvider
    from cj_agent.draft import proposal_id_for
    from run_worker import run_once
    context=load_run_context(args.run_context)
    sources=[*list((ROOT/'ios/App').glob('*.swift')),*list((ROOT/'ios/Modules/CJTripClient/Sources').rglob('*.swift')),
             *list((ROOT/'ios/Modules/CJShell/Sources').rglob('*.swift')),Path(__file__),HERE/'DevelopmentTripBrowserUITests.swift']
    report=dict(status='RUNNING',head=head,cases={},checks={},run_context=json.loads(args.run_context.read_text()),
        source_hashes={str(s.relative_to(ROOT)):hashlib.sha256(s.read_bytes()).hexdigest() for s in sources},
        git_trees={s:subprocess.check_output(['git','rev-parse',head+':'+s],cwd=ROOT,text=True).strip() for s in ('ios','backend','contracts','scripts')},
        unrun=['destination-local timeline fields','assistant Trip/day/item binding','PLACE/map service chain','real accounts/models/fees/cloud','physical device/VoiceOver','deployment'])
    if args.case:report['unrun'] += [c for c in CASES if c!=args.case]
    def save():(output/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
    save();tokens={};audit=[];records={};models={}
    try:
        with tempfile.TemporaryDirectory(prefix='cj21-',dir='/tmp') as temporary:
            root=Path(temporary)
            with cluster('tripbrowser',port=55721,role='cj21_initializer',root=root/'pg') as config:
                with psycopg.connect(**config,autocommit=True) as conn:
                    chain=migrate.load();migrate.up(conn,chain,chain[-1]['version'])
                connection=root/'connection.json';connection.write_text(json.dumps(config))
                subjects={case:{x:'cj21-'+uuid.uuid4().hex for x in ('A','B')} for case in CASES}
                auth=root/'auth';dev_auth.init(auth,[s for pair in subjects.values() for s in pair.values()])
                for target in (os.environ,env):target.update(CJ_LOCAL_CONNINFO=str(connection),CJ_LOCAL_AUTH_DIR=str(auth),CJ_LOCAL_RUN_CONTEXT=str(args.run_context.resolve()))
                database=LocalDatabase(connection,run_context=context);app=app_from_environment()
                async def observed(scope,receive,send):
                    if scope['type']!='http':return await app(scope,receive,send)
                    path=scope['path'];query=parse_qs(scope.get('query_string',b'').decode());captured=[]
                    async def capture(message):captured.append(message)
                    await app(scope,receive,capture);status=captured[0]['status']
                    audit.append(dict(method=scope['method'],path=path,query=query,status=status))
                    target=next((row for row in records.values() if row.get('hold_id')==query.get('trip_id',[''])[0]),None)
                    delayed=target is not None and path=='/v1/trip-details' and status==200
                    if delayed:
                        target['hold_id']=None;target['captured'].set()
                        if not await asyncio.to_thread(target['release'].wait,30):raise TimeoutError('late read release missing')
                    for message in captured:await send(message)
                    if delayed:target['released'].set()
                with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
                endpoint=f'http://127.0.0.1:{port}'
                server=uvicorn.Server(uvicorn.Config(observed,host='127.0.0.1',port=port,log_level='critical',access_log=False))
                api_thread=threading.Thread(target=server.run,daemon=True);api_thread.start()
                deadline=time.monotonic()+10
                while not server.started:
                    if not api_thread.is_alive() or time.monotonic()>deadline:raise RuntimeError('signed API startup unavailable')
                    time.sleep(.02)
                def operator(subject,*arguments):
                    subprocess.run([sys.executable,'-B',str(ROOT/'scripts/local_run_context.py'),'--conninfo-json',str(connection),
                        '--auth-dir',str(auth),'--run-context',str(args.run_context.resolve()),'--subject',subject,*arguments],env=env,stdout=subprocess.DEVNULL,check=True)
                def create(case):
                    row=records[case];model=models[case];headers={'Authorization':'Bearer '+tokens[case]['A'],'X-CJ-Trip-Content':'provenance.1'}
                    count=2 if case=='testAccountLateRead' else 21
                    with TestClient(app) as client:
                        for index in range(count):
                            cid=uuid.uuid4().hex;subject=subjects[case]['A']
                            client.put('/v1/conversations',params={'conversation_id':cid},headers=headers).raise_for_status()
                            needs=root/('needs-'+cid+'.json');needs.write_text(json.dumps(dict(action_id='needs-'+cid,needs_id='needs-'+cid,expected_version=0,
                                source={'kind':'manual','text':'Synthetic operator-supplied party size for browser acceptance'},changes={'party_size':{'state':'known','value':1}})))
                            operator(subject,'put-needs','--input-json',str(needs));operator(subject,'bind-needs','--conversation-id',cid,'--needs-id','needs-'+cid)
                            state=client.get('/v1/message-send-status',params={'conversation_id':cid},headers=headers);state.raise_for_status();message_head=state.json()['head']
                            command=dict(version='MESSAGE-send.1',conversation_id=cid,message_id=uuid.uuid4().hex,text='Synthetic formal trip browser record '+str(index),
                                trip_id=None,creation_intent='consider_trip',expected_generation=message_head['generation'],expected_sequence=message_head['last_sequence'])
                            response=client.post('/v1/messages',content=json.dumps(command).encode(),headers={**headers,'Content-Type':'application/octet-stream'});response.raise_for_status()
                            run_once(database,model,auth)
                            pid=proposal_id_for(response.json()['receipt']['run_id'])
                            proposal=client.get('/v1/trip-proposals',params={'proposal_id':pid},headers=headers);proposal.raise_for_status();proposal=proposal.json()['proposal']
                            action_id=uuid.uuid4().hex
                            prepared=client.post('/v1/trip-confirmations',json=dict(action_id=action_id,kind='accept',proposal_id=pid,candidate_hash=proposal['candidate_hash']),headers=headers);prepared.raise_for_status()
                            original=base64.b64decode(prepared.json()['action_utf8_base64'])
                            accepted=client.post('/v1/trip-actions',content=original,headers={**headers,'Content-Type':'application/octet-stream'});accepted.raise_for_status()
                            assert accepted.json()['receipt']['committed_version']==1
                        page=client.get('/v1/trips',params={'limit':50},headers=headers);page.raise_for_status();trips=page.json()['trips']
                        assert len(trips)==count and model.calls==count*2
                    row['formal']=[dict(trip_id=t['trip_id'],version=t['version'],title=t['document']['title'],sha256=hashlib.sha256(base64.b64decode(t['content_utf8_base64'])).hexdigest()) for t in trips]
                    row['calls']=model.calls;return row['formal']
                def verify(case,stage):
                    row=records[case];headers={'Authorization':'Bearer '+tokens[case]['A'],'X-CJ-Trip-Content':'provenance.1'}
                    scope=scope_for(ISSUER,subjects[case]['A'])
                    with database.connect(scope) as conn:assert conn.execute('SELECT current_user').fetchone()[0]=='cj_m1_runtime'
                    with TestClient(app) as client:
                        for expected in row['formal']:
                            response=client.get('/v1/trip-details',params={'trip_id':expected['trip_id']},headers=headers);response.raise_for_status();trip=response.json()['trip']
                            assert trip['version']==expected['version'] and hashlib.sha256(base64.b64decode(trip['content_utf8_base64'])).hexdigest()==expected['sha256']
                        foreign=client.get('/v1/trip-details',params={'trip_id':row['formal'][0]['trip_id']},headers={'Authorization':'Bearer '+tokens[case]['B'],'X-CJ-Trip-Content':'provenance.1'})
                        assert foreign.status_code==200 and foreign.json()['trip'] is None
                    requests=audit[row['audit_start']:]
                    report.setdefault('verification_requests',{})[case]=requests;save()
                    assert all(x['method'] in ('GET','HEAD') for x in requests) and models[case].calls==row['calls']
                    if stage=='browse':
                        pages=[x for x in requests if x['path']=='/v1/trips']
                        assert any(x['query'].get('after') for x in pages)
                    if stage=='late':assert row['captured'].is_set() and row['released'].is_set()
                    result=dict(formal_records=row['formal'],provider_calls=models[case].calls,app_requests=requests,
                                foreign_status=foreign.status_code,runtime_role='cj_m1_runtime',unchanged=True)
                    report['checks'][case]=result;save();return result
                class Control(BaseHTTPRequestHandler):
                    def log_message(self,*args):pass
                    def do_GET(self):
                        try:
                            query=parse_qs(self.path.split('?',1)[1]) if '?' in self.path else {};path=self.path.split('?',1)[0];case=query['case'][0]
                            if path=='/prepare':
                                tokens[case]={x:dev_auth.token(auth,s,120) for x,s in subjects[case].items()}
                                for s in subjects[case].values():operator(s,'init-budget')
                                models[case]=FakeProvider(chunks_per_reply=2)
                                records[case]=dict(audit_start=len(audit),captured=threading.Event(),release=threading.Event(),released=threading.Event())
                                value=dict(endpoint=endpoint,accounts=tokens[case],subjects=subjects[case],case_id=case)
                            elif path=='/create':value=create(case)
                            elif path=='/verify':value=verify(case,query['stage'][0])
                            elif path=='/hold':records[case]['hold_id']=query['trip_id'][0];value={}
                            elif path=='/wait-held':
                                if not records[case]['captured'].wait(10):raise TimeoutError('actual detail not held')
                                value={}
                            elif path=='/release':
                                records[case]['release'].set()
                                if not records[case]['released'].wait(10):raise TimeoutError('actual late detail not released')
                                value={}
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
                    (builder.directory/'G2CControl.swift').write_text((HERE/'DevelopmentTripBrowserUITests.swift').read_text().replace('__FIXTURE_URL__',f'http://127.0.0.1:{control.server_port}'))
                    project=builder.directory/'G2CAcceptance.xcodeproj';pbx=project/'project.pbxproj'
                    text=pbx.read_text().replace('space.go2china.foundation.local',BUNDLE).replace('space.go2china.foundation.control',BUNDLE+'.control')
                    entitlement=builder.directory/'Browser.entitlements';entitlement.write_bytes(plistlib.dumps({'application-identifier':BUNDLE,'keychain-access-groups':[BUNDLE]}))
                    text=text.replace(json.dumps(str(ROOT/'ios/App/Development.entitlements')),json.dumps(str(entitlement)));pbx.write_text(text)
                    for case in ([args.case] if args.case else CASES):
                        if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT):raise RuntimeError('candidate changed')
                        result=output/(case+'.xcresult')
                        command=['xcodebuild','-project',str(project),'-scheme','G2CControl','-configuration','Debug','-destination','platform=iOS Simulator,id='+args.simulator,
                            '-derivedDataPath',str(build),'-resultBundlePath',str(result),'-scmProvider','system','-skipPackageUpdates','-onlyUsePackageVersionsFromResolvedFile',
                            '-parallel-testing-enabled','NO','-collect-test-diagnostics','never','ARCHS=arm64','ONLY_ACTIVE_ARCH=YES','CODE_SIGNING_ALLOWED=YES','CODE_SIGN_IDENTITY=-',
                            '-only-testing:G2CControl/DevelopmentTripBrowserUITests/'+case,'test']
                        print('Trip browser: '+case,flush=True)
                        run=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=1800)
                        log=run.stdout+run.stderr
                        for pair in tokens.values():
                            for token in pair.values():log=log.replace(token,'<redacted-local-token>')
                        (output/(case+'.log')).write_text(log)
                        summary=json.loads(subprocess.check_output(['xcrun','xcresulttool','get','test-results','summary','--path',str(result)],text=True))
                        report.setdefault('results',{})[case]={x:summary[x] for x in ('passedTests','failedTests','skippedTests')};save();run.check_returncode()
                        assert summary['passedTests']==1 and summary['failedTests']==summary['skippedTests']==0
                        report['cases'][case]='PASS';save()
                    container=Path(subprocess.check_output(['xcrun','simctl','get_app_container',args.simulator,BUNDLE,'data'],text=True).strip())
                    for file in [*container.rglob('*'),*output.rglob('*')]:
                        if file.is_file():
                            raw=file.read_bytes();assert not any(token.encode() in raw for pair in tokens.values() for token in pair.values())
                            assert b'-----BEGIN PRIVATE KEY-----' not in raw
                    report['token_key_scan']='PASS';report['status']='PARTIAL_PASS' if args.case else 'PASS'
                finally:
                    for row in records.values():row['release'].set()
                    server.should_exit=True;api_thread.join(10);control.shutdown();control.server_close()
    except BaseException as error:report['status']='FAIL';report['error']=type(error).__name__;raise
    finally:save()
    print(json.dumps(dict(status=report['status'],head=head,cases=report['cases']),indent=2))

if __name__=='__main__':main()
