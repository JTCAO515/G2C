"""#15 actual App, signed API, restricted PG and original worker/FakeProvider.

A separately pinned backend candidate is permitted only through --backend-source
and --backend-head; its imports and clean source are verified. No manufactured
message/feedback receipt is passed to the App. Faults affect ACK delivery only.
"""
import argparse
import asyncio
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
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BUNDLE = 'space.go2china.feedback.acceptance'
CASES = ['testAnswerAndGeneralEnglish', 'testAnswerAndGeneralChinese',
         'testUnknownReopenAndOriginalLookup', 'testLateACKAccountSwitch']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--simulator'); target.add_argument('--device')
    parser.add_argument('--local-tls', type=Path); parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--run-context', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--build-dir', required=True, type=Path)
    parser.add_argument('--backend-source', required=True, type=Path)
    parser.add_argument('--backend-head', required=True)
    parser.add_argument('--case', choices=CASES)
    args = parser.parse_args()
    tls = None
    if args.device:
        if not args.local_tls: parser.error('--device requires the approved --local-tls profile')
        from m4_device import LocalTLS, configure_project, private_workspace
        from m4_native import DeviceNative, authenticated_control
        tls = LocalTLS.load(args.local_tls)
    elif args.local_tls or args.prepare_only: parser.error('Device options require --device')
    os.umask(0o077)
    output, build, backend = args.output.resolve(), args.build_dir.resolve(), args.backend_source.resolve()
    if tls: device_project_root, build = private_workspace(output, build)
    if any(p.is_relative_to(ROOT) or p.is_relative_to(backend) for p in (output, build)):
        raise ValueError('External evidence/build directory required')
    output.mkdir(parents=True)
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT):
        raise ValueError('Commit the App candidate first')
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=backend):
        raise ValueError('Backend candidate must be clean')
    backend_head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=backend, text=True).strip()
    if backend_head != args.backend_head:
        raise ValueError('Backend head differs from explicit pin')
    sys.path.insert(0, str(backend / 'scripts'))
    env = {k: v for k, v in os.environ.items() if not k.startswith(('PG', 'LIBPQ', 'SIMCTL_CHILD_', 'G2C_DEV_', 'CJ_LOCAL_'))}
    env.update(CJ_ENV='local', OS_ACTIVITY_MODE='disable', DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer')
    for key in tuple(os.environ):
        if key.startswith(('PG', 'LIBPQ', 'CJ_LOCAL_')):
            os.environ.pop(key)
    os.environ['CJ_ENV'] = 'local'
    import psycopg
    import uvicorn
    import cj_api.local_app as local_app
    import cj_feedback.postgres as feedback_repository
    import cj_agent.provider as provider
    import dev_auth
    import migrate
    from pg_suites import cluster
    from fastapi.testclient import TestClient
    from cj_api.local_run_context import load_run_context
    from run_worker import run_once
    for module in (local_app, feedback_repository, provider):
        if not Path(module.__file__).resolve().is_relative_to(backend):
            raise ValueError('Python imported another source tree')
    context = load_run_context(args.run_context)
    report = dict(status='RUNNING', head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  backend_head=backend_head, cases={}, database_proofs={}, checks={}, faults=[],
                  unrun=['real providers/cloud/accounts', 'physical device (#29)', 'release/deployment'],
                  run_context=json.loads(args.run_context.read_text()))
    sources = [*list((ROOT / 'ios/App').glob('*.swift')), Path(__file__), HERE / 'DevelopmentFeedbackUITests.swift']
    if tls: sources += [HERE / name for name in ('m4_device.py','m4_native.py','m4_artifacts.py','M4DeviceControl.swift','M4DeviceTestSession.swift')]
    for package in ('CJFeedbackClient', 'CJShell', 'CJMessageClient'):
        sources += list((ROOT / 'ios/Modules' / package / 'Sources').rglob('*.swift'))
    report['source_hashes'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    report['backend_trees'] = {p: subprocess.check_output(['git', 'rev-parse', 'HEAD:' + p], cwd=backend, text=True).strip()
                               for p in ('backend', 'contracts', 'scripts')}
    def save():
        (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    save()
    tokens, records, audit, errors = {}, {}, [], []
    stop, held, released, finished = (threading.Event() for _ in range(4))
    lock = threading.Lock()
    mode = {'fault': None}
    worker_thread = api_thread = control = server = native = control_token = None
    if tls: report.update(layer='signed approved iPhone/local pinned HTTPS/private PG/formal worker/FakeProvider',
        raw_native_bundle_shareable=False, build_inputs_shareable=False,
        device_font_scope='system default font; no size override',
        unrun=['real accounts/providers/cloud/fees'])
    try:
        with tempfile.TemporaryDirectory(prefix='cj15-', dir='/tmp') as temporary:
            root = Path(temporary)
            with cluster('feedbackapp', port=55715, role='cj15_initializer', root=root / 'pg') as config:
                with psycopg.connect(**config, autocommit=True) as conn:
                    chain = migrate.load(); migrate.up(conn, chain, chain[-1]['version'])
                connection = root / 'connection.json'; connection.write_text(json.dumps(config))
                subjects = {case: {key: 'cj15-' + uuid.uuid4().hex for key in ('A', 'B')} for case in CASES}
                auth = root / 'auth'; dev_auth.init(auth, [s for pair in subjects.values() for s in pair.values()])
                for target in (os.environ, env):
                    target.update(CJ_LOCAL_CONNINFO=str(connection), CJ_LOCAL_AUTH_DIR=str(auth), CJ_LOCAL_RUN_CONTEXT=str(args.run_context.resolve()))
                for case, pair in subjects.items():
                    tokens[case] = {key: dev_auth.token(auth, subject, 120) for key, subject in pair.items()}
                    for subject in pair.values():
                        run = subprocess.run([sys.executable, '-B', str(backend / 'scripts/local_run_context.py'),
                            '--conninfo-json', str(connection), '--auth-dir', str(auth), '--run-context', str(args.run_context.resolve()),
                            '--subject', subject, 'init-budget'], env=env, capture_output=True, text=True, timeout=30)
                        run.check_returncode()
                database = local_app.LocalDatabase(connection, run_context=context)
                app = local_app.app_from_environment()
                model = provider.FakeProvider(chunks_per_reply=2)
                def worker():
                    try:
                        while not stop.is_set():
                            run_once(database, model, auth); stop.wait(.05)
                    except BaseException as error:
                        errors.append(type(error).__name__); stop.set()
                worker_thread = threading.Thread(target=worker, daemon=True); worker_thread.start()

                try:
                    async def observed(scope, receive, send):
                        if scope['type'] != 'http':
                            return await app(scope, receive, send)
                        entry = dict(method=scope['method'], path=scope['path'])
                        async def read():
                            message = await receive()
                            if message['type'] == 'http.request':
                                entry.setdefault('_body', bytearray()).extend(message.get('body', b''))
                            return message
                        messages = []
                        async def capture(message):
                            messages.append(message)
                        feedback_post = scope['method'] == 'POST' and scope['path'] == '/v1/feedback'
                        if feedback_post:
                            await app(scope, read, capture) # original handler/auth/transaction commits before a delivery fault
                            entry['status'] = next(m['status'] for m in messages if m['type'] == 'http.response.start')
                            entry['sha256'] = hashlib.sha256(entry.pop('_body', b'')).hexdigest()
                            with lock:
                                audit.append(entry); fault = mode['fault']; mode['fault'] = None
                            if fault == 'hold':
                                held.set()
                                if not await asyncio.to_thread(released.wait, 60):
                                    raise TimeoutError('held original ACK not released')
                            elif fault == 'drop':
                                report['faults'].append(dict(kind='post-commit ACK replaced by 503', actual_status=entry['status'], sha256=entry['sha256']))
                                await send({'type': 'http.response.start', 'status': 503, 'headers': [(b'content-type', b'application/json')]})
                                await send({'type': 'http.response.body', 'body': b'{}'})
                                return
                            for message in messages: await send(message)
                            if fault == 'hold': finished.set()
                        else:
                            async def forward(message):
                                if message['type'] == 'http.response.start': entry['status'] = message['status']
                                await send(message)
                            await app(scope, receive, forward)
                            with lock: audit.append(entry)
                    with socket.socket() as sock:
                        sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
                    endpoint = f'https://{tls.host}:{port}' if tls else f'http://127.0.0.1:{port}'
                    server = uvicorn.Server(uvicorn.Config(observed, host=tls.host if tls else '127.0.0.1', port=port, log_level='error', access_log=False,
                        **(tls.uvicorn_options() if tls else {})))
                    api_thread = threading.Thread(target=server.run, daemon=True); api_thread.start()
                    deadline = time.monotonic() + 10
                    while not server.started:
                        if not api_thread.is_alive() or time.monotonic() > deadline: raise RuntimeError('API startup failed')
                        time.sleep(.02)

                    def proof(case):
                        result = dict(accounts={}, provider_calls=model.calls - records[case]['provider_start'])
                        for key, subject in subjects[case].items():
                            scope = local_app.scope_for(local_app.ISSUER, subject)
                            with database.connect(scope) as conn:
                                role = conn.execute('SELECT current_user').fetchone()[0]
                                assert role == 'cj_m1_runtime'
                                rows = conn.execute('SELECT action_id,original_input,input_sha256,source_reference FROM cj_feedback_action WHERE scope=%s ORDER BY submitted_at,action_id', (scope,)).fetchall()
                                feedback = []
                                for action_id, raw, digest, source in rows:
                                    value = json.loads(bytes(raw))
                                    assert hashlib.sha256(bytes(raw)).hexdigest() == digest
                                    assert set(value) == {'action_id', 'problem', 'expectation', 'references'}
                                    assert all(r['kind'] in ('message', 'run') for r in value['references'])
                                    assert b'PRIVATE_TRANSCRIPT_NOT_FEEDBACK' not in bytes(raw)
                                    feedback.append(dict(action_id=action_id, sha256=digest, problem=value['problem'], expectation=value['expectation'], references=value['references'], source=source))
                                messages = conn.execute('SELECT message_id,run_id,input_sha256 FROM cj_message_receipt WHERE scope=%s', (scope,)).fetchall()
                            result['accounts'][key] = dict(role=role, feedback=feedback, messages=[dict(message_id=m, run_id=r, sha256=h) for m,r,h in messages])
                        with lock: result['feedback_posts'] = sum(x['method'] == 'POST' and x['path'] == '/v1/feedback' for x in audit)
                        report['database_proofs'][case] = result; save(); return result

                    class Control(BaseHTTPRequestHandler):
                        def log_message(self, *args): pass
                        def do_GET(self):
                            try:
                                parsed = urlsplit(self.path); query = {k: v[0] for k,v in parse_qs(parsed.query).items()}
                                case = query['case']
                                if case not in CASES: raise ValueError('unregistered case')
                                if parsed.path == '/prepare':
                                    conversation = 'cj15-' + uuid.uuid4().hex
                                    with TestClient(app) as client:
                                        client.put('/v1/conversations', params={'conversation_id': conversation}, headers={'Authorization': 'Bearer ' + tokens[case]['A']}).raise_for_status()
                                    records[case] = dict(provider_start=model.calls, endpoint=endpoint, accounts={} if tls else tokens[case], subjects=subjects[case], case_id=case, conversation=conversation,
                                                         prompt='PRIVATE_TRANSCRIPT_NOT_FEEDBACK 北京地铁站信息 ' + conversation)
                                    value = records[case]
                                elif parsed.path == '/proof': value = proof(case)
                                elif parsed.path == '/fault':
                                    if query['kind'] not in ('drop', 'hold'): raise ValueError('unregistered fault')
                                    held.clear(); released.clear(); finished.clear(); mode['fault'] = query['kind']; value = {}
                                elif parsed.path == '/wait-held':
                                    if not held.wait(20): raise TimeoutError('no actual committed ACK held')
                                    value = proof(case)
                                elif parsed.path == '/release':
                                    released.set()
                                    if not finished.wait(20): raise TimeoutError('no actual ACK delivered')
                                    value = proof(case)
                                elif parsed.path == '/size':
                                    if query['value'] not in ('large', 'accessibility-extra-extra-extra-large'): raise ValueError('unsupported size')
                                    value = {}
                                elif parsed.path == '/validate':
                                    value = proof(case)
                                    with TestClient(app) as client:
                                        for original in value['accounts']['A']['feedback']:
                                            aid = original['action_id']; headers = {'Authorization': 'Bearer ' + tokens[case]['A']}
                                            own = client.get('/v1/feedback-action-receipts', params={'action_id': aid}, headers=headers)
                                            own.raise_for_status(); receipt = own.json()['receipt']
                                            assert receipt['input_sha256'] == original['sha256']
                                            foreign_headers = {'Authorization': 'Bearer ' + tokens[case]['B']}
                                            assert client.get('/v1/feedback-action-receipts', params={'action_id': aid}, headers=foreign_headers).json()['receipt'] is None
                                            located = client.get('/internal/v1/feedback-diagnostics', params={'action_id': aid}, headers=headers)
                                            located.raise_for_status(); diagnostic = located.json()
                                            assert 'PRIVATE_TRANSCRIPT_NOT_FEEDBACK' not in json.dumps(diagnostic)
                                            if original['references']:
                                                assert diagnostic['current_locator']['message_version'] == 'MESSAGE-send.1'
                                                assert diagnostic['current_locator']['operations']
                                                assert diagnostic['external_model_version'] is None
                                                assert receipt['source']['message_id'] == value['accounts']['A']['messages'][0]['message_id']
                                                forged = dict(action_id='foreign-' + aid, problem='voluntary forged association negative', expectation='', references=original['references'])
                                                denied = client.post('/v1/feedback', content=json.dumps(forged).encode(), headers=dict(foreign_headers, **{'Content-Type': 'application/octet-stream'}))
                                                assert denied.status_code == 503
                                            else: assert receipt['source'] is None and diagnostic['current_locator'] is None
                                            assert client.get('/internal/v1/feedback-diagnostics', params={'action_id': aid}, headers=foreign_headers).status_code == 503
                                    report['checks'][case] = dict(original_hash_receipt=True, signed_cross_owner_refused=True, minimal_content=True, actual_locator=True)
                                    save()
                                else: raise ValueError('unsupported control')
                                raw = json.dumps(value).encode(); self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(raw)
                            except Exception as error:
                                import traceback
                                report.setdefault('control_errors', []).append(dict(type=type(error).__name__, frames=[dict(function=f.name, line=f.lineno) for f in traceback.extract_tb(error.__traceback__)]))
                                save(); self.send_response(500); self.end_headers(); self.wfile.write(type(error).__name__.encode())
                    control_token = secrets.token_urlsafe(32) if tls else None; active_case = None; last_device_container = None
                    def stage_input(request):
                        query = parse_qs(urlsplit(request).query)
                        if set(query) != {'case'} or query['case'] != [active_case]: raise ValueError('Staging requires the active feedback case')
                        native.stage(case=query['case'][0])
                    control = ThreadingHTTPServer((tls.host if tls else '127.0.0.1', 0),
                        authenticated_control(Control, control_token, stage_input, lambda: active_case) if tls else Control)
                    if tls: tls.secure_http_server(control)
                    threading.Thread(target=control.serve_forever, daemon=True).start()
                    spec = importlib.util.spec_from_file_location('feedback_builder', ROOT / 'scripts/check_ios_trip_confirm.py')
                    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                    builder = object.__new__(module.XCTestDriver); builder.directory = (device_project_root if tls else output) / 'project'; builder.directory.mkdir(); builder.write_project(0)
                    control_url = ('https://' + tls.host if tls else 'http://127.0.0.1') + ':' + str(control.server_port)
                    (builder.directory / 'G2CControl.swift').write_text((HERE / 'DevelopmentFeedbackUITests.swift').read_text().replace('__FIXTURE_URL__', control_url))
                    project = builder.directory / 'G2CAcceptance.xcodeproj'; pbx = project / 'project.pbxproj'
                    text = pbx.read_text().replace('space.go2china.foundation.local', BUNDLE).replace('space.go2china.foundation.control', BUNDLE + '.control')
                    entitlement = builder.directory / 'Feedback.entitlements'; entitlement.write_bytes(plistlib.dumps({'application-identifier': BUNDLE, 'keychain-access-groups': [BUNDLE]}))
                    pbx.write_text(text.replace(json.dumps(str(ROOT / 'ios/App/Development.entitlements')), json.dumps(str(entitlement))))
                    if tls: _, configuration_file, _ = configure_project(project, tls, control_url, control_token, bundle=BUNDLE)
                    for case in ([args.case] if args.case else CASES):
                        report['cases'][case] = 'RUNNING'; save()
                        if tls:
                            active_case = case
                            detail = dict(status='RUNNING'); report.setdefault('device_native', {})[case] = detail
                            case_output = output / 'device-native' / case; case_output.mkdir(parents=True, mode=0o700)
                            native = DeviceNative(args.device, BUNDLE, project, configuration_file, build, ROOT,
                                case_output, tokens[case], control_token, detail, evidence_root=output,case_id=case)
                            selected = ['DevelopmentFeedbackUITests/' + case]
                            native.build_for_testing('Debug', selected, env)
                            if args.prepare_only:
                                detail['status'] = 'PREPARED_EXECUTION_UNRUN'; report['cases'][case] = 'UNRUN'; save(); continue
                            try:
                                native.run('Debug', selected, env)
                            except BaseException:
                                detail['status'] = 'FAIL'; report['cases'][case] = 'FAIL'
                                try:
                                    last_device_container = native.scan('Debug')
                                    detail['failure_container_scan'] = {'status': 'PASS'}
                                except Exception as scan_error:
                                    detail['failure_container_scan'] = {
                                        'status': 'FAIL' if isinstance(scan_error, AssertionError) else 'UNRUN',
                                        'error_type': type(scan_error).__name__}
                                save()
                                raise
                            last_device_container = native.scan('Debug')
                            detail['status'] = 'PASS'; report['cases'][case] = 'PASS'; save(); continue
                        result = output / (case + '.xcresult')
                        command = ['xcodebuild', '-project', str(project), '-scheme', 'G2CControl', '-configuration', 'Debug', '-destination', 'platform=iOS Simulator,id=' + args.simulator,
                            '-derivedDataPath', str(build), '-resultBundlePath', str(result), '-scmProvider', 'system', '-skipPackageUpdates', '-onlyUsePackageVersionsFromResolvedFile',
                            '-parallel-testing-enabled', 'NO', '-collect-test-diagnostics', 'never', 'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=YES', 'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGN_IDENTITY=-',
                            '-only-testing:G2CControl/DevelopmentFeedbackUITests/' + case, 'test']
                        print('Running ' + case, flush=True)
                        run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=1200)
                        log = run.stdout + run.stderr
                        for pair in tokens.values():
                            for token in pair.values(): log = log.replace(token, '<redacted-local-token>')
                        (output / (case + '.log')).write_text(log)
                        if run.returncode: report['cases'][case] = 'FAIL'; save(); run.check_returncode()
                        summary = json.loads(subprocess.check_output(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', str(result)], env=env, text=True))
                        report.setdefault('results', {})[case] = {k: summary[k] for k in ('passedTests', 'failedTests', 'skippedTests')}
                        assert summary['passedTests'] == 1 and summary['failedTests'] == summary['skippedTests'] == 0
                        report['cases'][case] = 'PASS'; save()
                    if not args.prepare_only:
                        container = last_device_container if tls else Path(subprocess.check_output(['xcrun', 'simctl', 'get_app_container', args.simulator, BUNDLE, 'data'], env=env, text=True).strip())
                        for path in [*container.rglob('*'), *output.rglob('*')]:
                            if path.is_file():
                                raw = path.read_bytes()
                                assert not any(token.encode() in raw for pair in tokens.values() for token in pair.values())
                                assert b'-----BEGIN PRIVATE KEY-----' not in raw
                                if path.is_relative_to(container): assert b'PRIVATE_TRANSCRIPT_NOT_FEEDBACK' not in raw
                        assert not errors
                        assert all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == digest for p, digest in report['source_hashes'].items()), 'App source changed during native execution'
                        assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == report['head'], 'App head changed during execution'
                        assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT), 'App working tree changed during execution'
                        report['checks']['source_hashes_unchanged'] = 'PASS'
                        report['checks']['token_private_key_and_app_plaintext_scan'] = 'PASS'
                        report['status'] = 'VERIFYING_CLEANUP'
                    else: report.update(status='PREPARED_EXECUTION_UNRUN'); save()
                finally:
                    stop.set(); released.set()
                    if worker_thread: worker_thread.join(timeout=10)
                    if server: server.should_exit = True
                    if api_thread: api_thread.join(timeout=10)
                    if control: control.shutdown(); control.server_close(); control = None
            report['private_pg_stopped'] = True
    except BaseException as error:
        report['status'] = 'FAIL'; report['error'] = type(error).__name__
        for case, status in report['cases'].items():
            if status == 'RUNNING': report['cases'][case] = 'FAIL'
        raise
    finally:
        stop.set(); released.set()
        if worker_thread: worker_thread.join(timeout=10)
        if server: server.should_exit = True
        if api_thread: api_thread.join(timeout=10)
        if control: control.shutdown(); control.server_close()
        if tls:
            try:
                if native is not None: native.cleanup_input()
            except Exception:
                report['status'] = 'FAIL'; raise
            finally:
                (device_project_root / 'project/M4ControlBootstrap.plist').unlink(missing_ok=True); save()
            if control_token is not None:
                for path in output.rglob('*'):
                    if path.is_file() and not path.is_symlink():
                        if any(value.encode() in path.read_bytes() for value in [*[t for pair in tokens.values() for t in pair.values()], control_token]):
                            report['status'] = 'FAIL'; save(); raise AssertionError('credential in evidence export')
                report['artifact_token_scan'] = 'PASS'
        else:
            subprocess.run(['xcrun', 'simctl', 'terminate', args.simulator, BUNDLE], env=env, capture_output=True)
        report['worker_errors'] = errors; report['request_audit'] = audit
        if (worker_thread and worker_thread.is_alive()) or (api_thread and api_thread.is_alive()): report['status'] = 'FAIL'; report['shutdown'] = 'thread alive'
        if report['status'] != 'FAIL':
            try:
                assert all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == digest for p, digest in report['source_hashes'].items()), 'App source changed during execution'
                assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == report['head'], 'App head changed during execution'
                assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=backend, text=True).strip() == args.backend_head, 'backend pin changed during execution'
                assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT), 'App working tree changed during execution'
            except BaseException as error:
                report.update(status='FAIL', error=type(error).__name__); save(); raise
            report['status'] = 'PREPARED_EXECUTION_UNRUN' if args.prepare_only else ('PARTIAL_PASS' if args.case else 'PASS')
        save()


if __name__ == '__main__': main()
