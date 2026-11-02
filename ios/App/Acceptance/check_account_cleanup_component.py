"""#443 native CJCleanupClient component, actual signed API/private PG/FakeProvider.

The positive host selects actual B-owned domains from the unmodified main registry;
it is explicitly NOT whole-App/device completion. The second host uses the full
actual registry and must preserve real missing-owner-hook blocked/prepared state.
No account operation, binding, receipt or progress token is injected into the App.
"""
import argparse, asyncio, hashlib, importlib.util, json, os, plistlib, socket, subprocess, sys, tempfile, threading, time, uuid
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BUNDLE = 'space.go2china.cleanup.component'
CASES = ['testActualCommittedUnknownReopen', 'testActualPreparationUnknown', 'testActualFullInventoryBlocked']
B_DOMAINS = ('business/message', 'checkpoints/run', 'business/usage', 'business/feedback-private-actions')
# Explicit operator inventory, independent of the registry under test. Its full
# snapshot must include actual C/unimplemented and all DEVICE@3 domains.
FULL_INVENTORY = ('business/message','business/usage','business/memory-authoritative','business/trip-authoritative',
    'business/needs-current-planning','business/feedback-private-actions','business/cleanup-metadata',
    'business/memory-management-actions','checkpoints/run','memory-derived',
    'device-cache/encrypted-message-file','device-cache/sdk-session-keychain','device-cache/message-key-keychain',
    'device-cache/trip-pending-file','device-cache/offline-trip','device-cache/feedback-pending','device-cache/feedback-key-keychain',
    'device-cache/memory-manual-pending','device-cache/memory-lifecycle-pending','device-cache/memory-typed-pending',
    'device-cache/memory-key-keychain','device-cache/needs-pending','device-cache/needs-key-keychain',
    'device-cache/memory-history-pending','device-cache/trip-scoped-pending','device-cache/needs-planning-pending',
    'device-cache/trip-key-keychain','device-cache/offline-key-keychain','device-cache/offline-write-residue','external-processing')


def main():
    global BUNDLE
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('simulator', 'backend-head'): parser.add_argument('--' + name, required=True)
    for name in ('backend-source', 'run-context', 'output', 'build-dir'): parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--case', choices=CASES)
    parser.add_argument('--native-device', action='store_true', help='Use actual CJProbeApp DEVICE@3 workflow; legacy component cases remain default')
    args = parser.parse_args()
    if args.native_device: BUNDLE='space.go2china.device-v3.acceptance'
    backend = args.backend_source.resolve(); output = args.output.resolve(); build = args.build_dir.resolve()
    for path in (output, build):
        if path.is_relative_to(ROOT) or path.is_relative_to(backend): raise ValueError('external artifact/build root required')
    output.mkdir(parents=True)
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT): raise ValueError('commit native candidate first')
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=backend): raise ValueError('clean explicit backend pin required')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=backend, text=True).strip()
    if head != args.backend_head: raise ValueError('backend pin mismatch')
    env = {k:v for k,v in os.environ.items() if not k.startswith(('PG','LIBPQ','SIMCTL_CHILD_','G2C_DEV_','CJ_LOCAL_'))}
    env.update(CJ_ENV='local', OS_ACTIVITY_MODE='disable', DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer')
    for key in tuple(os.environ):
        if key.startswith(('PG','LIBPQ','CJ_LOCAL_')): os.environ.pop(key)
    os.environ['CJ_ENV']='local'
    sys.path[:0] = [str(backend/'scripts'), str(backend/'backend'), *sorted(str(p) for p in (backend/'backend').iterdir() if p.is_dir())]
    import psycopg, uvicorn
    import cj_api.local_app as local_app
    import cj_api.local_cleanup as cleanup
    import cj_agent.provider as provider
    from cj_api.local_run_context import load_run_context
    from cj_api.local_worker_context import checker_for
    from cj_cleanup.registry import freeze
    from cj_cleanup.core import encode
    from fastapi.testclient import TestClient
    from pg_suites import cluster
    import migrate, dev_auth, local_run_context, run_worker
    for module in (local_app,cleanup,provider,run_worker):
        if not Path(module.__file__).resolve().is_relative_to(backend): raise ValueError('foreign backend import')
    context=load_run_context(args.run_context)
    report=dict(status='RUNNING',head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(), backend_head=head,
        app_mode='CJProbeApp_device_v3' if args.native_device else 'native_component_harness_not_CJProbeApp',positive_inventory=list(B_DOMAINS),full_registry=str(Path('backend/storage-registry.json')),
        cases={},proofs={},faults=[],run_context=json.loads(args.run_context.read_text()),
        unrun=['CJProbeApp account UI/full AX/localizations', 'complete device hook/key erasure/current-device receipt', 'C/all-domain full-account completion', 'physical device/VoiceOver', 'real accounts/cloud/providers/fees/deployment'])
    sources=[Path(__file__),HERE/'AccountCleanupComponentApp.swift',HERE/'AccountCleanupComponentUITests.swift',ROOT/'ios/App/DevelopmentSessionConfiguration.swift']
    for module in ('CJCleanupClient','CJMessageClient'):
        sources+=list((ROOT/'ios/Modules'/module/'Sources').rglob('*.swift'))
    if args.native_device:
        sources += [ROOT/'ios/App/CJProbeApp.swift', ROOT/'ios/App/DevelopmentTripHost.swift', HERE/'DevelopmentDeviceCleanupUITests.swift']
        for module in ('CJShell','CJOfflineTrip','CJAuth','CJTripClient','CJManualPreviewClient','CJMemoryClient','CJNeedsClient','CJFeedbackClient'):
            sources += list((ROOT/'ios/Modules'/module/'Sources').rglob('*.swift'))
        report['unrun']=['all C online cleanup domains', 'physical device/VoiceOver', 'real accounts/cloud/providers/fees/deployment']
    report['source_hashes']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    report['backend_trees']={name:subprocess.check_output(['git','rev-parse','HEAD:'+name],cwd=backend,text=True).strip() for name in ('backend','contracts','scripts')}
    def save(): (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    save(); servers=[]; threads=[]; control=None; secrets=[]; audits=[]; lock=threading.Lock(); fault={'path':None}; current={'case':None}
    try:
        with tempfile.TemporaryDirectory(prefix='cj443-',dir='/tmp') as temp:
            root=Path(temp)
            with cluster('cleanupclient443',port=55843,role='cj443_initializer',root=root/'pg') as config:
                with psycopg.connect(**config,autocommit=True) as conn:
                    migrations=migrate.load(); migrate.up(conn,migrations,migrations[-1]['version'])
                connection=root/'connection.json';connection.write_text(json.dumps(config))
                subjects={case:{k:'cj443-'+uuid.uuid4().hex for k in ('A','B')} for case in CASES}
                auth=root/'auth';dev_auth.init(auth,[s for pair in subjects.values() for s in pair.values()])
                tokens={case:{k:dev_auth.token(auth,s,120) for k,s in pair.items()} for case,pair in subjects.items()}
                secrets.extend(t for pair in tokens.values() for t in pair.values())
                for pair in subjects.values():
                    for subject in pair.values(): local_run_context.provision_budget(connection,context,subject)
                database=local_app.LocalDatabase(connection,run_context=context)
                registry=backend/'backend/storage-registry.json';manifest=json.loads(registry.read_bytes())
                full=freeze(registry.read_bytes(),FULL_INVENTORY,versions=('CLEANUP@1.0','CLEANUP@1.1'))
                assert not full.gaps,'explicit full inventory differs from actual main'
                def project(node,parent=''):
                    target=parent+node['id'];children=node.get('objects',[])
                    nested=[child for child in children if isinstance(child,dict)]
                    if nested:
                        assert len(nested)==len(children),'mixed registry children'
                        selected=[value for child in nested if (value:=project(child,target+'/')) is not None]
                        return dict(node,objects=selected) if selected else None
                    return node if target in B_DOMAINS else None
                selected=[value for node in manifest['stores'] if (value:=project(node)) is not None]
                component_registry=root/'component-registry.json'
                component_registry.write_bytes(encode(dict(version='CJ443-B-COMPONENT-1',stores=selected)))
                component=freeze(component_registry.read_bytes(),B_DOMAINS,versions=('CLEANUP@1.0','CLEANUP@1.1'))
                actual={entry.registry_id:entry for entry in full.entries}
                assert not component.gaps and all(entry==actual[entry.registry_id] for entry in component.entries)
                report['component_registry']=dict(scope='B-owned component only; not full account/device',
                    sha256=component.digest,full_main_sha256=full.digest,entry_digests={entry.registry_id:entry.version for entry in component.entries})
                report['full_inventory']=list(FULL_INVENTORY);save()
                key=os.urandom(32); secrets.append(key)
                options=cleanup.Configuration({'native-local':key},'native-local',7200,B_DOMAINS,component_registry)
                full_options=cleanup.Configuration({'native-local':key},'native-local',7200,FULL_INVENTORY,registry)
                apps={mode:local_app.create_local_app(conninfo_path=connection,auth_dir=auth,run_context=context,cleanup_configuration=selected,
                    history_configuration=local_app.load_history_configuration(auth) if args.native_device else None)
                    for mode,selected in [('component',options),('full',full_options)]}
                runtime=cleanup.Runtime(database,options,local_app.scope_for)
                bindings={case:{k:runtime.bind(checker_for(auth).check(tokens[case][k]).principal) for k in ('A','B')} for case in CASES}
                model=provider.FakeProvider();provider_counts={};feedback_hashes={}
                for case in CASES:
                    before=model.calls;feedback_hashes[case]={}
                    with TestClient(apps['component']) as api:
                        for k,subject in subjects[case].items():
                            headers={'Authorization':'Bearer '+tokens[case][k],'Content-Type':'application/octet-stream'}
                            opened=api.put('/v1/conversations',params={'conversation_id':'native-cleanup'},headers=headers);opened.raise_for_status()
                            raw=json.dumps(dict(version='MESSAGE-send.1',conversation_id='native-cleanup',message_id='native-message',
                                text='原生注销组件 中文输入与原操作 '+subject,trip_id=None,creation_intent='none',expected_generation=opened.json()['generation'],expected_sequence=0)).encode()
                            api.post('/v1/messages',content=raw,headers=headers).raise_for_status()
                            feedback_raw=json.dumps(dict(action_id='native-feedback',problem='中文组件反馈 '+subject,expectation='',references=[])).encode()
                            api.post('/v1/feedback',content=feedback_raw,headers=headers).raise_for_status()
                            feedback_hashes[case][k]=hashlib.sha256(feedback_raw).hexdigest()
                    run_worker.run_once(database,model,auth)
                    provider_counts[case]=model.calls-before
                    assert provider_counts[case]==2,'actual A/B original FakeProvider run did not complete'
                original_size = subprocess.check_output(['xcrun','simctl','ui',args.simulator,'content_size'],env=env,text=True).strip()
                if args.native_device: subprocess.run(['xcrun','simctl','ui',args.simulator,'content_size','large'],env=env,check=True)
                endpoints={}
                for mode,app in apps.items():
                    async def observed(scope,receive,send,app=app,mode=mode):
                        if scope['type']!='http': return await app(scope,receive,send)
                        headers=dict(scope['headers']);authorization=headers.get(b'authorization',b'').decode('ascii')
                        who=next(((case,k) for case,pair in tokens.items() for k,t in pair.items() if authorization=='Bearer '+t),None)
                        messages=[]; body=bytearray()
                        async def read():
                            message=await receive()
                            if message['type']=='http.request': body.extend(message.get('body',b''))
                            return message
                        async def capture(message): messages.append(message)
                        await app(scope,read,capture)
                        status=next(m['status'] for m in messages if m['type']=='http.response.start')
                        raw=b''.join(m.get('body',b'') for m in messages if m['type']=='http.response.body')
                        response=json.loads(raw) if raw else {}
                        for field in ('device_token','progress_token'):
                            if field in response: secrets.append(response[field])
                        if isinstance(response.get('preparation'),dict):secrets.append(response['preparation']['progress_token'])
                        for payload in (response,response.get('registration',{}),response.get('invocation',{})):
                            if isinstance(payload,dict):
                                for name in ('device_token','receipt_token'):
                                    if name in payload:secrets.append(payload[name])
                        entry=dict(mode=mode,case=current['case'],actor=None if who is None else who[1],method=scope['method'],path=scope['path'],http_status=status,
                            authorization_scheme=authorization.partition(' ')[0],request_sha256=hashlib.sha256(body).hexdigest())
                        if body: entry['action']=json.loads(body)
                        if isinstance(response.get('error'),dict):entry['error_code']=response['error'].get('code')
                        for name in ('operation_id','binding_id','registry_digest','phase','status','business_access'):
                            if name in response:entry[name]=response[name]
                        if isinstance(response.get('preparation'),dict): entry['operation_id']=response['preparation']['operation_id']
                        if isinstance(response.get('invocation'),dict):
                            call=response['invocation']['call']
                            entry['device_call']=call
                            entry['device_state']=response['invocation']['state']
                        if isinstance(response.get('call'),dict):
                            entry['device_call']=response['call'];entry['device_state']=response['state']
                        with lock:audits.append(entry);drop=scope['method']=='POST' and fault['path']==scope['path'];fault['path']=None if drop else fault['path']
                        if drop:
                            report['faults'].append(dict(path=scope['path'],actual_status=status,actual_operation_id=response.get('operation_id')));save()
                            trace=response['request_id']
                            error=json.dumps(dict(request_id=trace,error=dict(code='CLEANUP_OUTCOME_UNKNOWN',category='dependency',message_en='Unknown',message_zh='未知',outcome='unknown',recovery='reconcile_original'))).encode()
                            await send({'type':'http.response.start','status':503,'headers':[(b'content-type',b'application/json'),(b'cache-control',b'no-store'),(b'x-request-id',trace.encode())]})
                            await send({'type':'http.response.body','body':error});return
                        for message in messages:await send(message)
                    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
                    server=uvicorn.Server(uvicorn.Config(observed,host='127.0.0.1',port=port,log_level='error',access_log=False))
                    thread=threading.Thread(target=server.run,daemon=True);thread.start();servers.append(server);threads.append(thread)
                    deadline=time.monotonic()+10
                    while not server.started:
                        if not thread.is_alive() or time.monotonic()>deadline:raise RuntimeError('local API did not start')
                        time.sleep(.02)
                    endpoints[mode]='http://127.0.0.1:'+str(port)
                def proof(case):
                    with lock: entries=[dict(e) for e in audits if e['case']==case]
                    result=dict(provider_calls=provider_counts[case],api=entries,accounts={})
                    prepares=[e for e in entries if e['method']=='POST' and e['path']=='/v1/account-cleanup-operations']
                    assert len(prepares)==1 and 'operation_id' in prepares[0]
                    original_id=prepares[0]['operation_id'] # Actual API-produced ID, never a fabricated SQL context.
                    for k in ('A','B'):
                        binding=bindings[case][k]
                        with binding.store.transaction(original_id,writing=False) as cur:
                            cur.execute('SELECT current_user');role=cur.fetchone()[0];assert role=='cj_local_cleanup'
                            cur.execute('SELECT operation_id,action_id,input_digest,phase FROM cj_cleanup_request WHERE subject_digest=%s ORDER BY action_id',(binding.store.subject_digest,));operations=cur.fetchall()
                            cur.execute('SELECT count(*) FROM cj_account_fence WHERE subject_digest=%s',(binding.store.subject_digest,));fences=cur.fetchone()[0]
                            counts={};cleanup_eligible=False
                            if fences:
                                assert len(operations)==1 and operations[0][0]==original_id
                                cur.execute('SELECT purpose,blocked FROM cj_cleanup_operation WHERE subject_digest=%s AND operation_id=%s',(binding.store.subject_digest,original_id))
                                assert cur.fetchone()==('account',False),'physical read requires actual unblocked original account operation'
                                cleanup_eligible=True
                                cur.execute("SELECT set_config('cj.cleanup_scope',%s,true),set_config('cj.cleanup_purpose','account',true)",(binding.owner_scope,))
                                for table in ('cj_feedback_action','cj_message_receipt','cj_run_record'):
                                    cur.execute('SELECT count(*) FROM '+table+' WHERE scope=%s',(binding.owner_scope,));counts[table]=cur.fetchone()[0]
                                cur.execute("SELECT set_config('cj.cleanup_owner_scope',%s,true)",(binding.owner_scope,))
                                usage=0
                                for ledger in binding.namespaces[3:]:
                                    cur.execute("SELECT set_config('cj.cleanup_scope',%s,true)",(ledger,))
                                    cur.execute('SELECT count(*) FROM cj_usage_ledger_candidate WHERE scope_id=%s',(ledger,));usage+=cur.fetchone()[0]
                                counts['cj_usage_ledger_candidate']=usage
                        with database.connect(binding.owner_scope) as conn:
                            runtime_role=conn.execute('SELECT current_user').fetchone()[0];assert runtime_role=='cj_m1_runtime'
                            if not fences:
                                # A blocked/prepared or B live account is NOT eligible
                                # for cleanup-role private reads. Use its actual ordinary
                                # role, with this original authenticated owner scope.
                                conn.execute("SELECT set_config('cj.message_scope',%s,true)",(binding.owner_scope,))
                                for table in ('cj_feedback_action','cj_message_receipt','cj_run_record'):
                                    counts[table]=conn.execute('SELECT count(*) FROM '+table+' WHERE scope=%s',(binding.owner_scope,)).fetchone()[0]
                                counts['cj_usage_ledger_candidate']=conn.execute('SELECT count(*) FROM cj_usage_ledger_candidate').fetchone()[0]
                                observed=conn.execute('SELECT input_sha256 FROM cj_feedback_action WHERE scope=%s AND action_id=%s',(binding.owner_scope,'native-feedback')).fetchone()
                                assert observed==(feedback_hashes[case][k],),'live other-owner original feedback bytes changed'
                        if not fences:
                            with TestClient(apps['full' if case=='testActualFullInventoryBlocked' else 'component']) as verifier:
                                checked=verifier.get('/v1/feedback-action-receipts',params={'action_id':'native-feedback'},headers={'Authorization':'Bearer '+tokens[case][k]})
                                assert checked.status_code==200 and checked.json()['receipt']['input_sha256']==feedback_hashes[case][k]
                        result['accounts'][k]=dict(cleanup_role=role,runtime_role=runtime_role,cleanup_private_read_eligible=cleanup_eligible,
                            physical_read_authority='original-confirmed-cleanup' if fences else 'current-ALLOWED-runtime-and-signed-receipt',
                            operations=[dict(operation_id=o,action_id=a,input_digest=d,phase=p) for o,a,d,p in operations],
                            fences=fences,feedback=counts['cj_feedback_action'],domain_rows=counts)
                    report['proofs'][case]=result;save();return result
                class Control(BaseHTTPRequestHandler):
                    def log_message(self,*args):pass
                    def do_GET(self):
                        try:
                            parsed=urlsplit(self.path);query={k:v[0] for k,v in parse_qs(parsed.query).items()}
                            case=query.get('case',current['case'])
                            if case not in CASES:raise ValueError('unknown case')
                            if parsed.path=='/fixture':
                                current['case']=case
                                value=dict(endpoint=endpoints['full' if case=='testActualFullInventoryBlocked' else 'component'],accounts=tokens[case],subjects=subjects[case],case_id=case)
                            elif parsed.path=='/fault':
                                if query['kind']=='preparation':fault['path']='/v1/account-cleanup-operations'
                                elif query['kind']=='confirmation':
                                    candidates=proof(case)['accounts']['A']['operations'];assert len(candidates)==1
                                    fault['path']='/v1/account-cleanup-operations/'+candidates[0]['operation_id']+'/confirmation'
                                elif query['kind']=='device-receipt' and args.native_device:fault['path']='/v3/cleanup-device-receipts'
                                else:raise ValueError('unknown fault')
                                value={}
                            elif parsed.path=='/size' and args.native_device:
                                size={'max':'accessibility-extra-extra-extra-large','standard':'large'}[query['value']]
                                subprocess.run(['xcrun','simctl','ui',args.simulator,'content_size',size],env=env,check=True)
                                value={}
                            elif parsed.path=='/native-files' and args.native_device:
                                container=Path(subprocess.check_output(['xcrun','simctl','get_app_container',args.simulator,BUNDLE,'data'],env=env,text=True).strip())
                                namespace=lambda value:str(uuid.UUID(bytes=hashlib.sha256(value.encode()).digest()[:16])).upper()
                                environment=namespace('G2C.DEBUG.TRIP.environment|'+endpoints['component'])
                                account=namespace('G2C.DEBUG.TRIP.account|https://local.g2c.invalid|'+subjects[case]['A'])
                                support=container/'Library/Application Support'
                                known=('G2CDevelopmentMessages','G2CDevelopmentTrip','G2CDevelopmentMemory','G2CDevelopmentNeeds','G2CDevelopmentFeedback','G2COfflineTrip')
                                counts={}
                                for folder in known:
                                    base=support/folder/environment
                                    candidates=[p for p in base.glob(account+'*')] if base.exists() else []
                                    counts[folder]=sum(1 for parent in candidates for p in parent.rglob('*') if p.is_file())
                                if query['stage']=='before':assert counts['G2CDevelopmentMessages']>0,'real App draft did not persist encrypted snapshot'
                                elif query['stage']=='after':assert all(n==0 for n in counts.values()),'original App private files remain'
                                else:raise ValueError('unknown native file stage')
                                other_account=namespace('G2C.DEBUG.TRIP.account|https://local.g2c.invalid|'+subjects[case]['B'])
                                other={str(p.relative_to(support)):hashlib.sha256(p.read_bytes()).hexdigest()
                                    for folder in known for parent in (support/folder/environment).glob(other_account+'*')
                                    for p in parent.rglob('*') if p.is_file()}
                                if query['stage']=='before':assert other,'other account has no actual encrypted file'
                                else:assert other==report['native_files'][case]['before']['other_hashes'],'other account native file changed'
                                value=dict(stage=query['stage'],counts=counts,other_hashes=other)
                                report.setdefault('native_files',{}).setdefault(case,{})[query['stage']]=value;save()
                            elif parsed.path=='/proof':value=proof(case)
                            elif parsed.path=='/validate':
                                value=proof(case);a=value['accounts']['A'];b=value['accounts']['B'];assert len(a['operations'])==1 and not b['operations']
                                writes=[e for e in value['api'] if e['method']=='POST']
                                prepares=[e for e in writes if e['path']=='/v1/account-cleanup-operations'];assert len(prepares)==1
                                assert prepares[0]['request_sha256']==a['operations'][0]['input_digest']
                                confirms=[e for e in writes if e['path'].endswith('/confirmation')];assert len(confirms)==(0 if case=='testActualPreparationUnknown' else 1)
                                assert b['fences']==0 and b['feedback']==1 and all(count==1 for count in b['domain_rows'].values())
                                if case=='testActualCommittedUnknownReopen':assert a['fences']==1 and a['cleanup_private_read_eligible'] and all(count==0 for count in a['domain_rows'].values()) and a['operations'][0]['phase']=='confirmed'
                                else:assert a['fences']==0 and all(count==1 for count in a['domain_rows'].values()) and a['operations'][0]['phase']=='prepared'
                                assert not any(e['path'].startswith('/v1/cleanup-device-calls') or e['path'].startswith('/v1/cleanup-device-receipts') for e in value['api'])
                                if args.native_device:
                                    registrations=[e for e in writes if e['path']=='/v3/cleanup-devices' and e['actor']=='A'];assert len(registrations)==1
                                    calls=[e for e in writes if e['path']=='/v3/cleanup-device-calls']
                                    receipts=[e for e in writes if e['path']=='/v3/cleanup-device-receipts']
                                    if case=='testActualCommittedUnknownReopen':
                                        assert len(calls)==len(receipts)==1
                                        call=calls[0]['device_call'];assert call['operation_id']==a['operations'][0]['operation_id']
                                        assert call['reason']=='account_cleanup' and len(call['targets'])==19
                                        assert receipts[0]['device_state']=='confirmed' and receipts[0]['action']['outcome']=='confirmed'
                                        original_reads=[e for e in value['api'] if e['method']=='GET' and e['path']=='/v3/cleanup-device-calls/'+call['invocation_id']]
                                        assert original_reads and original_reads[-1]['device_state']=='confirmed'
                                    else:assert not calls and not receipts
                                report.setdefault('checks',{})[case]=dict(real_server_original=True,exact_original_bytes=True,no_repeated_prepare_or_confirmation=True,other_actor_unchanged=True,device_hook_not_claimed=not args.native_device);save()
                            else:raise ValueError('unknown control path')
                            raw=json.dumps(value).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
                        except Exception as error:
                            report.setdefault('control_errors',[]).append(type(error).__name__);save();self.send_response(500);self.end_headers()
                control=ThreadingHTTPServer(('127.0.0.1',0),Control);threading.Thread(target=control.serve_forever,daemon=True).start()
                spec=importlib.util.spec_from_file_location('cleanup_component_builder',ROOT/'scripts/check_ios_trip_confirm.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
                builder=object.__new__(module.XCTestDriver);builder.directory=output/'project';builder.directory.mkdir();builder.write_project(0)
                test_file='DevelopmentDeviceCleanupUITests.swift' if args.native_device else 'AccountCleanupComponentUITests.swift'
                (builder.directory/'G2CControl.swift').write_text((HERE/test_file).read_text().replace('__CONTROL_URL__','http://127.0.0.1:'+str(control.server_port)))
                project=builder.directory/'G2CAcceptance.xcodeproj';pbx=project/'project.pbxproj';text=pbx.read_text()
                original_entry=json.dumps(str(ROOT/'ios/App/CJProbeApp.swift'))
                assert text.count(original_entry)==1,'component entry replacement missing or ambiguous'
                if not args.native_device:text=text.replace(original_entry,json.dumps(str(HERE/'AccountCleanupComponentApp.swift')))
                text=text.replace('space.go2china.foundation.local',BUNDLE).replace('space.go2china.foundation.control',BUNDLE+'.control')
                entitlement=builder.directory/'Component.entitlements';entitlement.write_bytes(plistlib.dumps({'application-identifier':BUNDLE,'keychain-access-groups':[BUNDLE]}))
                pbx.write_text(text.replace(json.dumps(str(ROOT/'ios/App/Development.entitlements')),json.dumps(str(entitlement))))
                for case in ([args.case] if args.case else CASES):
                    current['case']=case;report['cases'][case]='RUNNING';save();result=output/(case+'.xcresult')
                    command=['xcodebuild','-project',str(project),'-scheme','G2CControl','-configuration','Debug','-destination','platform=iOS Simulator,id='+args.simulator,
                        '-derivedDataPath',str(build),'-resultBundlePath',str(result),'-scmProvider','system','-skipPackageUpdates','-onlyUsePackageVersionsFromResolvedFile','-parallel-testing-enabled','NO',
                        '-collect-test-diagnostics','never','ARCHS=arm64','ONLY_ACTIVE_ARCH=YES','CODE_SIGNING_ALLOWED=YES','CODE_SIGN_IDENTITY=-',
                        '-only-testing:G2CControl/'+('DevelopmentDeviceCleanupUITests' if args.native_device else 'AccountCleanupComponentUITests')+'/'+case,'test']
                    run=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,text=True,timeout=1200)
                    log=run.stdout+run.stderr
                    for secret in secrets:
                        if isinstance(secret,str):log=log.replace(secret,'<redacted-local-credential>')
                    (output/(case+'.log')).write_text(log)
                    if run.returncode:report['cases'][case]='FAIL';save();run.check_returncode()
                    summary=json.loads(subprocess.check_output(['xcrun','xcresulttool','get','test-results','summary','--path',str(result)],env=env,text=True))
                    report.setdefault('results',{})[case]={k:summary[k] for k in ('passedTests','failedTests','skippedTests')}
                    assert summary['passedTests']==1 and summary['failedTests']==summary['skippedTests']==0
                    report['cases'][case]='PASS';save()
                container=Path(subprocess.check_output(['xcrun','simctl','get_app_container',args.simulator,BUNDLE,'data'],env=env,text=True).strip())
                for path in [*container.rglob('*'),*output.rglob('*')]:
                    if path.is_file():
                        data=path.read_bytes()
                        for secret in secrets:
                            if (secret.encode() if isinstance(secret,str) else secret) in data:raise AssertionError('credential leaked into component artifacts')
                report['credential_scan']='PASS';report['status']='PASS' if len(report['cases'])==len(CASES) else 'PARTIAL_PASS';save()
            report['pg_stopped']=True;save()
    except Exception as error:
        report['status']='FAIL';report['error_type']=type(error).__name__;report['last_api']=audits;save();raise
    finally:
        if args.native_device and 'original_size' in locals():
            subprocess.run(['xcrun','simctl','ui',args.simulator,'content_size',original_size],env=env,check=True)
        if control:control.shutdown();control.server_close()
        for server in servers:server.should_exit=True
        for thread in threads:thread.join(timeout=10)
    print(json.dumps(dict(status=report['status'],head=report['head'],cases=report['cases'],unrun=report['unrun']),ensure_ascii=False))

if __name__=='__main__':main()
