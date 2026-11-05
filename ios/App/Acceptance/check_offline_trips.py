"""#24 actual App + signed API + restricted PG + unmodified worker/FakeProvider.

Formal records are created through MESSAGE, worker, signed confirmation and act.
The App gets no Trip fixture, cache bytes, operation ID or manufactured acceptance.
503/UNKNOWN are explicit post-auth fault injections; denial uses the real invite gate.
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
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BUNDLE = 'space.go2china.offline-trip.acceptance'
CASES = ['testReopenLanguageAndReadOnly', 'testExpiryRollbackAndUntrustedTime',
         'testAccountSwitchAndLogout', 'testTemporaryFailuresAndIdentityDenial']
sys.path.insert(0, str(ROOT / 'scripts'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--simulator'); target.add_argument('--device')
    parser.add_argument('--local-tls', type=Path); parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--run-context', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--build-dir', required=True, type=Path)
    parser.add_argument('--case', choices=CASES)
    parser.add_argument('--seed-only', action='store_true', help='Diagnose real formal-source preparation; every native case remains UNRUN')
    args = parser.parse_args()
    tls = None
    if args.device:
        if not args.local_tls: parser.error('--device requires the approved --local-tls profile')
        from m4_device import LocalTLS, configure_project, private_workspace, scan_app_container
        from m4_native import DeviceNative, authenticated_control
        tls = LocalTLS.load(args.local_tls)
    elif args.local_tls or args.prepare_only: parser.error('Device options require --device')
    if args.seed_only and args.prepare_only: parser.error('Choose source diagnostic or device build preparation')
    os.umask(0o077)
    output, build = args.output.resolve(), args.build_dir.resolve()
    if tls: device_project_root, build = private_workspace(output, build)
    if output.is_relative_to(ROOT) or build.is_relative_to(ROOT):
        raise ValueError('Evidence and build output must stay outside the repository')
    output.mkdir(parents=True)
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT):
        raise ValueError('Commit candidate first; preserve previous evidence')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    env = {k: v for k, v in os.environ.items() if not k.startswith(('PG', 'LIBPQ', 'SIMCTL_CHILD_', 'G2C_DEV_', 'CJ_LOCAL_'))}
    env.update(CJ_ENV='local', OS_ACTIVITY_MODE='disable', DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer')
    for key in tuple(os.environ):
        if key.startswith(('PG', 'LIBPQ', 'CJ_LOCAL_')):
            os.environ.pop(key)
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
    from cj_agent.draft import proposal_id_for
    from run_worker import run_once

    context = load_run_context(args.run_context)
    sources = [*list((ROOT / 'ios/App').glob('*.swift')),
               *list((ROOT / 'ios/Modules/CJOfflineTrip/Sources').rglob('*.swift')),
               *list((ROOT / 'ios/Modules/CJShell/Sources').rglob('*.swift')),
               *list((ROOT / 'ios/Modules/CJAuth/Sources/CJSession').glob('*.swift')),
               Path(__file__), HERE / 'DevelopmentOfflineTripUITests.swift']
    if tls: sources += [HERE / name for name in ('m4_device.py','m4_native.py','m4_artifacts.py','M4DeviceControl.swift','M4DeviceTestSession.swift')]
    report = dict(status='RUNNING', head=head, cases={}, checks={}, faults=[], unrun_cases=list(CASES),
                  source_hashes={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
                  run_context=json.loads(args.run_context.read_text()),
                  unrun=['#24 box4 original account-cleanup operation/device receipt bridge',
                         'real accounts/providers/cloud/fees', 'physical offline device/VoiceOver (#29)', 'deployment'])
    if args.case:
        report['unrun'] += [case for case in CASES if case != args.case]
    if tls: report.update(layer='signed approved iPhone/local pinned HTTPS/private PG/formal worker/FakeProvider',
        raw_native_bundle_shareable=False, build_inputs_shareable=False,
        device_font_scope='system default font; no size override',
        unrun=['physical Wi-Fi/airplane-mode outage','real 14-day elapsed time','physical locked file protection',
               'VoiceOver','real accounts/providers/cloud/fees'])
    def save():
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    save()
    tokens, records, models, audit = {}, {}, {}, []
    try:
        with tempfile.TemporaryDirectory(prefix='cj24-', dir='/tmp') as temporary:
            root = Path(temporary)
            with cluster('offlinetrip', port=55724, role='cj24_initializer', root=root / 'pg') as config:
                with psycopg.connect(**config, autocommit=True) as conn:
                    chain = migrate.load(); migrate.up(conn, chain, chain[-1]['version'])
                connection = root / 'connection.json'; connection.write_text(json.dumps(config))
                subjects = {case: {x: 'cj24-' + uuid.uuid4().hex for x in ('A', 'B')} for case in CASES}
                auth = root / 'auth'; dev_auth.init(auth, [s for pair in subjects.values() for s in pair.values()])
                for target in (os.environ, env):
                    target.update(CJ_LOCAL_CONNINFO=str(connection), CJ_LOCAL_AUTH_DIR=str(auth), CJ_LOCAL_RUN_CONTEXT=str(args.run_context.resolve()))
                database = LocalDatabase(connection, run_context=context)
                app = app_from_environment()
                mode = {'verification': 'normal'}

                async def observed(scope, receive, send):
                    if scope['type'] != 'http':
                        return await app(scope, receive, send)
                    path = scope['path']; query = parse_qs(scope.get('query_string', b'').decode()); captured = []
                    async def capture(message): captured.append(message)
                    await app(scope, receive, capture)
                    status = captured[0]['status']
                    body = b''.join(m.get('body', b'') for m in captured[1:])
                    raw_bearer = dict(scope.get('headers', [])).get(b'authorization', b'')
                    actor = next(((case, key) for case, pair in tokens.items() for key, value in pair.items()
                                  if raw_bearer == ('Bearer ' + value).encode()), None)
                    row = dict(method=scope['method'], path=path, query=query, status=status, actor=actor,
                               response_sha256=hashlib.sha256(body).hexdigest())
                    audit.append(row)
                    if path == '/v1/message-receipts' and status == 200 and mode['verification'] != 'normal':
                        # The real signature/admission/repository read already ran above.
                        value = json.loads(body); trace = value['request_id']
                        if mode['verification'] == '503':
                            payload = {'request_id': trace, 'error': {'code': 'INTERNAL_ERROR', 'category': 'dependency',
                                'message_en': 'Injected after real authenticated read', 'message_zh': '真实鉴权读取后的注入故障',
                                'outcome': 'unknown', 'recovery': 'retry_safe_read'}}
                            code = 503
                        else:
                            payload = value; payload['request_id'] = str(uuid.uuid4()); code = 200
                        changed = json.dumps(payload).encode()
                        report['faults'].append(dict(kind=mode['verification'], actual_status=status, actor=actor))
                        await send({'type': 'http.response.start', 'status': code, 'headers': [
                            (b'content-type', b'application/json'), (b'x-request-id', trace.encode()),
                            (b'cache-control', b'no-store'), (b'content-length', str(len(changed)).encode())]})
                        await send({'type': 'http.response.body', 'body': changed}); return
                    for message in captured: await send(message)

                with socket.socket() as sock:
                    sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
                endpoint = f'https://{tls.host}:{port}' if tls else f'http://127.0.0.1:{port}'
                runtime = {'server': None, 'thread': None}
                def start():
                    server = uvicorn.Server(uvicorn.Config(observed, host=tls.host if tls else '127.0.0.1', port=port,
                        log_level='critical', access_log=False, lifespan='off', **(tls.uvicorn_options() if tls else {})))
                    thread = threading.Thread(target=server.run, daemon=True)
                    runtime.update(server=server, thread=thread); thread.start()
                    deadline = time.monotonic() + 10
                    while not server.started:
                        if not thread.is_alive() or time.monotonic() > deadline:
                            raise RuntimeError('Actual signed API startup failed')
                        time.sleep(.02)
                def stop():
                    if runtime['server'] is not None: runtime['server'].should_exit = True
                    if runtime['thread'] is not None:
                        runtime['thread'].join(10)
                        if runtime['thread'].is_alive(): raise RuntimeError('Actual API did not stop')
                start()

                def operator(subject,*arguments):
                    subprocess.run([sys.executable,'-B',str(ROOT/'scripts/local_run_context.py'),'--conninfo-json',str(connection),
                        '--auth-dir',str(auth),'--run-context',str(args.run_context.resolve()),'--subject',subject,*arguments],env=env,stdout=subprocess.DEVNULL,check=True)
                def create(case):
                    row=records[case];model=models[case];headers={'Authorization':'Bearer '+tokens[case]['A'],'X-CJ-Trip-Content':'provenance.1'}
                    count=1
                    with TestClient(app) as client:
                        for index in range(count):
                            cid=uuid.uuid4().hex;subject=subjects[case]['A']
                            client.put('/v1/conversations',params={'conversation_id':cid},headers=headers).raise_for_status()
                            needs=root/('needs-'+cid+'.json');needs.write_text(json.dumps(dict(action_id='needs-'+cid,needs_id='needs-'+cid,expected_version=0,
                                source={'kind':'manual','text':'Synthetic operator-supplied party size for browser acceptance'},changes={'party_size':{'state':'known','value':1}})))
                            operator(subject,'put-needs','--input-json',str(needs));operator(subject,'bind-needs','--conversation-id',cid,'--needs-id','needs-'+cid)
                            state=client.get('/v1/message-send-status',params={'conversation_id':cid},headers=headers);state.raise_for_status();message_head=state.json()['head']
                            command=dict(version='MESSAGE-send.1',conversation_id=cid,message_id=uuid.uuid4().hex,text='请安排北京三日游，保留中文地点。本地合成离线验收 '+str(index),
                                trip_id=None,creation_intent='consider_trip',expected_generation=message_head['generation'],expected_sequence=message_head['last_sequence'])
                            response=client.post('/v1/messages',content=json.dumps(command).encode(),headers={**headers,'Content-Type':'application/octet-stream'});response.raise_for_status()
                            outcomes=run_once(database,model,auth)
                            report.setdefault('worker_outcomes', {})[case] = [dict(run_id=o.run_id,status=o.status,proposal_id=o.proposal_id) for o in outcomes]
                            report.setdefault('provider_calls', {})[case] = model.calls
                            save()
                            pid=proposal_id_for(response.json()['receipt']['run_id'])
                            proposal=client.get('/v1/trip-proposals',params={'proposal_id':pid},headers=headers)
                            if proposal.status_code != 200:
                                snapshot=client.get('/v2/run-draft-status',params={'message_id':command['message_id']},headers=headers)
                                report.setdefault('source_diagnostics', {})[case] = dict(proposal_status=proposal.status_code,
                                    error_code=proposal.json().get('error',{}).get('code'),run_status=snapshot.status_code,
                                    run_fields={key:value for key,value in snapshot.json().items() if key in {'run_status','status','draft_outcome','budget_exhausted_stage','limit_reason'}})
                                save()
                            proposal.raise_for_status();proposal=proposal.json()['proposal']
                            action_id=uuid.uuid4().hex
                            prepared=client.post('/v1/trip-confirmations',json=dict(action_id=action_id,kind='accept',proposal_id=pid,candidate_hash=proposal['candidate_hash']),headers=headers);prepared.raise_for_status()
                            original=base64.b64decode(prepared.json()['action_utf8_base64'])
                            accepted=client.post('/v1/trip-actions',content=original,headers={**headers,'Content-Type':'application/octet-stream'});accepted.raise_for_status()
                            assert accepted.json()['receipt']['committed_version']==1
                        page=client.get('/v1/trips',params={'limit':50},headers=headers);page.raise_for_status();trips=page.json()['trips']
                        assert len(trips)==count and model.calls==count*2
                    row['formal']=[dict(trip_id=t['trip_id'],version=t['version'],title=t['document']['title'],sha256=hashlib.sha256(base64.b64decode(t['content_utf8_base64'])).hexdigest()) for t in trips]
                    row['calls']=model.calls;return row['formal']

                if args.seed_only:
                    case = args.case or CASES[0]
                    tokens[case] = {x: dev_auth.token(auth, subject, 120) for x, subject in subjects[case].items()}
                    for subject in subjects[case].values(): operator(subject, 'init-budget')
                    models[case] = FakeProvider(chunks_per_reply=2)
                    records[case] = dict(audit_start=len(audit))
                    try:
                        report['formal_source_preparation'] = create(case)
                        report['status'] = 'UNRUN'
                        report['mode'] = 'formal_source_diagnostic_only'
                        save()
                    finally: stop()
                    return

                def app_files():
                    if tls:
                        container = Path(tempfile.mkdtemp(prefix='device-offline-snapshot-', dir=root)) / 'app-data'
                        scan_app_container(args.device, BUNDLE, container, tokens[active_case].values())
                    else:
                        container = Path(subprocess.check_output(['xcrun', 'simctl', 'get_app_container', args.simulator, BUNDLE, 'data'], env=env, text=True).strip())
                    environment_id = str(uuid.UUID(bytes=hashlib.sha256(('G2C.DEBUG.TRIP.environment|' + endpoint).encode()).digest()[:16])).upper()
                    files = sorted((container / 'Library/Application Support/G2COfflineTrip' / environment_id).glob('*/snapshot.aesgcm'))
                    return container, files

                def verify(case, query):
                    row = records[case]
                    scope = scope_for(ISSUER, subjects[case]['A'])
                    with database.connect(scope) as conn:
                        assert conn.execute('SELECT current_user').fetchone()[0] == 'cj_m1_runtime'
                    assert models[case].calls == row['calls'] == 2
                    requests = audit[row['audit_start']:]
                    assert all(x['method'] in ('GET', 'HEAD') for x in requests)
                    expected_hash = query.get('snapshot_hash', [''])[0]
                    if expected_hash:
                        assert any(x['actor'] == (case, 'A') and x['path'] == '/v1/trip-details' and x['status'] == 200
                                   and x['response_sha256'] == expected_hash for x in requests)
                    _, files = app_files()
                    expected_files = int(query.get('files', ['1'])[0])
                    assert len(files) == expected_files
                    hashes = {p.name + ':' + p.parent.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
                    for file in files:
                        assert file.stat().st_mode & 0o777 == 0o600
                        assert row['formal'][0]['title'].encode() not in file.read_bytes()
                    if query.get('stage') == ['unchanged']:
                        assert hashes == row['file_checkpoint']
                    if query.get('stage') == ['checkpoint']:
                        row['file_checkpoint'] = hashes
                    if query.get('network') == ['none']:
                        assert len(audit) == row['network_checkpoint']
                    if query.get('stage') == ['denied']:
                        assert any(x['actor'] == (case, 'A') and x['status'] == 403 for x in requests)
                        with TestClient(app) as client:
                            response = client.get('/v1/message-receipts', params={'message_id': 'verify-b'},
                                headers={'Authorization': 'Bearer ' + tokens[case]['B']})
                            assert response.status_code == 200
                    proof = dict(stage=query.get('stage'), files=len(files), encrypted_file_hashes=hashes,
                        provider_calls=models[case].calls, runtime_role='cj_m1_runtime', app_requests=requests)
                    report['checks'].setdefault(case, []).append(proof); save(); return proof

                prepared = {}
                def prepare_case(case):
                    if tls and case in prepared: return prepared[case]
                    mode['verification'] = 'normal'
                    tokens[case] = {x: dev_auth.token(auth, s, 120) for x, s in subjects[case].items()}
                    for s in subjects[case].values(): operator(s, 'init-budget')
                    models[case] = FakeProvider(chunks_per_reply=2)
                    records[case] = dict(audit_start=len(audit))
                    value = dict(endpoint=endpoint, accounts={} if tls else tokens[case], subjects=subjects[case], case_id=case)
                    if tls: prepared[case] = value
                    return value
                class Control(BaseHTTPRequestHandler):
                    def log_message(self, *args): pass
                    def do_GET(self):
                        try:
                            query = parse_qs(self.path.split('?', 1)[1]) if '?' in self.path else {}
                            path, case = self.path.split('?', 1)[0], query['case'][0]
                            if path == '/prepare':
                                value = prepare_case(case)
                            elif path == '/create': value = create(case)
                            elif path == '/verify': value = verify(case, query)
                            elif path == '/checkpoint': records[case]['network_checkpoint'] = len(audit); value = {}
                            elif path == '/offline': stop(); value = {}
                            elif path == '/online': start(); mode['verification'] = 'normal'; value = {}
                            elif path == '/mode':
                                requested = query['value'][0]
                                assert requested in {'normal', '503', 'unknown'}
                                mode['verification'] = requested; value = {}
                            elif path == '/revoke':
                                invited = set(json.loads((auth / 'invited.json').read_text()))
                                invited.remove(subjects[case]['A'])
                                (auth / 'invited.json').write_text(json.dumps(sorted(invited)))
                                value = {}
                            elif path == '/size':
                                size = query['value'][0]
                                assert size in {'large', 'accessibility-extra-extra-extra-large'}
                                value = {}
                            else: raise ValueError('Unknown control route')
                            raw = json.dumps(value).encode(); self.send_response(200); self.end_headers(); self.wfile.write(raw)
                        except Exception as error:
                            import traceback
                            report.setdefault('control_errors', []).append(dict(type=type(error).__name__,
                                frames=[dict(function=f.name, line=f.lineno) for f in traceback.extract_tb(error.__traceback__)]))
                            save(); self.send_response(500); self.end_headers(); self.wfile.write(type(error).__name__.encode())
                control_token = secrets.token_urlsafe(32) if tls else None; native = None; active_case = None
                def stage_input(request):
                    query = parse_qs(request.split('?', 1)[1])
                    if set(query) != {'case'} or query['case'] != [active_case]: raise ValueError('Staging requires the active offline case')
                    native.stage(case=query['case'][0])
                control = ThreadingHTTPServer((tls.host if tls else '127.0.0.1', 0),
                    authenticated_control(Control, control_token, stage_input, lambda: active_case) if tls else Control)
                if tls: tls.secure_http_server(control)
                threading.Thread(target=control.serve_forever, daemon=True).start()
                try:
                    spec = importlib.util.spec_from_file_location('trip_builder', ROOT / 'scripts/check_ios_trip_confirm.py')
                    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                    builder = object.__new__(module.XCTestDriver); builder.directory = (device_project_root if tls else output) / 'project'
                    builder.directory.mkdir(); builder.write_project(0)
                    control_url = ('https://' + tls.host if tls else 'http://127.0.0.1') + ':' + str(control.server_port)
                    (builder.directory / 'G2CControl.swift').write_text((HERE / 'DevelopmentOfflineTripUITests.swift').read_text()
                        .replace('__FIXTURE_URL__', control_url))
                    project = builder.directory / 'G2CAcceptance.xcodeproj'; pbx = project / 'project.pbxproj'
                    text = pbx.read_text().replace('space.go2china.foundation.local', BUNDLE).replace('space.go2china.foundation.control', BUNDLE + '.control')
                    entitlement = builder.directory / 'Offline.entitlements'
                    entitlement.write_bytes(plistlib.dumps({'application-identifier': BUNDLE, 'keychain-access-groups': [BUNDLE]}))
                    text = text.replace(json.dumps(str(ROOT / 'ios/App/Development.entitlements')), json.dumps(str(entitlement)))
                    pbx.write_text(text)
                    if tls: _, configuration_file, _ = configure_project(project, tls, control_url, control_token, bundle=BUNDLE)
                    for case in ([args.case] if args.case else CASES):
                        assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == head
                        assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)
                        if tls:
                            active_case = case; prepare_case(case)
                            detail = dict(status='RUNNING'); report.setdefault('device_native', {})[case] = detail
                            case_output = output / 'device-native' / case; case_output.mkdir(parents=True, mode=0o700)
                            native = DeviceNative(args.device, BUNDLE, project, configuration_file, build, ROOT,
                                case_output, tokens[case], control_token, detail, evidence_root=output,case_id=case)
                            selected = ['DevelopmentOfflineTripUITests/' + case]
                            native.build_for_testing('Debug', selected, env)
                            if args.prepare_only:
                                detail['status'] = 'PREPARED_EXECUTION_UNRUN'; report['cases'][case] = 'UNRUN'; save(); continue
                            native.run('Debug', selected, env); native.scan('Debug')
                            detail['status'] = 'PASS'; report['cases'][case] = 'PASS'; report['unrun_cases'].remove(case); save(); continue
                        result = output / (case + '.xcresult')
                        command = ['xcodebuild', '-project', str(project), '-scheme', 'G2CControl', '-configuration', 'Debug',
                            '-destination', 'platform=iOS Simulator,id=' + args.simulator, '-derivedDataPath', str(build),
                            '-resultBundlePath', str(result), '-scmProvider', 'system', '-skipPackageUpdates',
                            '-onlyUsePackageVersionsFromResolvedFile', '-parallel-testing-enabled', 'NO', '-collect-test-diagnostics', 'never',
                            'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=YES', 'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGN_IDENTITY=-',
                            '-only-testing:G2CControl/DevelopmentOfflineTripUITests/' + case, 'test']
                        report['cases'][case] = 'RUNNING'; report['unrun_cases'].remove(case); save()
                        print('Offline native: ' + case, flush=True)
                        run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=1200)
                        log = run.stdout + run.stderr
                        for pair in tokens.values():
                            for token in pair.values(): log = log.replace(token, '<redacted-local-token>')
                        (output / (case + '.log')).write_text(log)
                        summary = json.loads(subprocess.check_output(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', str(result)], env=env, text=True))
                        report.setdefault('results', {})[case] = {x: summary[x] for x in ('passedTests', 'failedTests', 'skippedTests')}
                        if run.returncode != 0: report['cases'][case] = 'FAIL'
                        save(); run.check_returncode()
                        assert summary['passedTests'] == 1 and summary['failedTests'] == summary['skippedTests'] == 0
                        report['cases'][case] = 'PASS'; save()
                    if not args.prepare_only:
                        container, _ = app_files()
                        for path in [*container.rglob('*'), *output.rglob('*')]:
                            if path.is_file():
                                raw = path.read_bytes()
                                assert not any(token.encode() in raw for pair in tokens.values() for token in pair.values())
                                assert b'-----BEGIN PRIVATE KEY-----' not in raw
                        report['token_key_scan'] = 'PASS'
                        report['status'] = 'VERIFYING_CLEANUP'
                    else: report.update(status='PREPARED_EXECUTION_UNRUN'); save()
                finally:
                    stop(); control.shutdown(); control.server_close()
                    if tls:
                        try:
                            if native is not None: native.cleanup_input()
                        finally: (device_project_root / 'project/M4ControlBootstrap.plist').unlink(missing_ok=True)
                        for path in output.rglob('*'):
                            if path.is_file() and not path.is_symlink():
                                assert not any(value.encode() in path.read_bytes() for value in [*[t for pair in tokens.values() for t in pair.values()], control_token]), 'credential in evidence export'
                        report['artifact_token_scan'] = 'PASS'; save()
            report['private_pg_stopped'] = True
            assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == head, 'head changed during execution'
            assert all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == digest for p, digest in report['source_hashes'].items()), 'source changed during execution'
            report['status'] = 'PREPARED_EXECUTION_UNRUN' if args.prepare_only else ('PARTIAL_PASS' if args.case else 'PASS')
    except BaseException as error:
        report['status'] = 'FAIL'; report['error'] = type(error).__name__; raise
    finally:
        save()
    print(json.dumps(dict(status=report['status'], head=head, cases=report['cases']), indent=2))


if __name__ == '__main__': main()
