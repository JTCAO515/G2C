"""#23 actual conversation history settings, signed API/runtime PG and App.

A separately pinned backend candidate is permitted only through --backend-source
and --backend-head; its imports and clean source are verified. No manufactured
message/history receipt is passed to the App. Faults affect only labelled actual response delivery.
"""
import argparse
import asyncio
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
BUNDLE = 'space.go2china.history.acceptance'
CASES = ['testHistoryEnglish', 'testHistoryChinese', 'testHistoryUnknownReopen',
         'testHistoryConflict', 'testHistoryLateSwitch', 'testHistoryReadUnavailable']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulator', required=True)
    parser.add_argument('--run-context', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--build-dir', required=True, type=Path)
    parser.add_argument('--backend-source', required=True, type=Path)
    parser.add_argument('--backend-head', required=True)
    parser.add_argument('--case', choices=CASES)
    args = parser.parse_args()
    output, build, backend = args.output.resolve(), args.build_dir.resolve(), args.backend_source.resolve()
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
    import cj_memory_jobs.postgres as history_repository
    from cj_memory_jobs.local_app import app_from_environment
    from datetime import datetime, timedelta, timezone
    import cj_agent.provider as provider
    import dev_auth
    import migrate
    from pg_suites import cluster
    from fastapi.testclient import TestClient
    from cj_api.local_run_context import load_run_context
    from run_worker import run_once
    for module in (local_app, history_repository, provider):
        if not Path(module.__file__).resolve().is_relative_to(backend):
            raise ValueError('Python imported another source tree')
    context = load_run_context(args.run_context)
    report = dict(status='RUNNING', head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  backend_head=backend_head, cases={}, database_proofs={}, checks={}, faults=[],
                  unrun=['real providers/cloud/accounts', 'physical device/VoiceOver (#29)', 'release/deployment'],
                  run_context=json.loads(args.run_context.read_text()))
    sources = [*list((ROOT / 'ios/App').glob('*.swift')), Path(__file__), HERE / 'DevelopmentHistoryUITests.swift']
    for package in ('CJMemoryClient', 'CJShell', 'CJMessageClient'):
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
    worker_thread = api_thread = control = server = None
    try:
        with tempfile.TemporaryDirectory(prefix='cj434-', dir='/tmp') as temporary:
            root = Path(temporary)
            with cluster('historyapp', port=55734, role='cj434_initializer', root=root / 'pg') as config:
                with psycopg.connect(**config, autocommit=True) as conn:
                    chain = migrate.load(); migrate.up(conn, chain, chain[-1]['version'])
                connection = root / 'connection.json'; connection.write_text(json.dumps(config))
                subjects = {case: {key: 'cj434-' + uuid.uuid4().hex for key in ('A', 'B')} for case in CASES}
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
                profile = dict(subjects=['self'], slots={'food.spice':dict(kind='preference',collection_allowed=True,semantic_resolved=True)},extents=['long_term'],context_ids=[])
                policy = dict(version='local-memory-policy.1',expires_at=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),
                    profiles={subject:profile for pair in subjects.values() for subject in pair.values()})
                policy_path=root/'memory-policy.json';policy_path.write_text(json.dumps(policy));policy_path.chmod(0o600)
                for target in (os.environ,env):target['CJ_LOCAL_MEMORY_POLICY']=str(policy_path)
                app = app_from_environment()
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
                        history_post = scope['method'] == 'POST' and scope['path'] == '/v3/memory-history-actions'
                        fault_read = scope['path'] == '/v3/memory-history-settings' and mode['fault'] == 'read-503'
                        if history_post or fault_read:
                            await app(scope, read, capture) # original handler/auth/transaction commits before a delivery fault
                            entry['status'] = next(m['status'] for m in messages if m['type'] == 'http.response.start')
                            entry['sha256'] = hashlib.sha256(entry.pop('_body', b'')).hexdigest()
                            with lock:
                                audit.append(entry); fault = mode['fault']; mode['fault'] = None
                            if fault == 'hold':
                                held.set()
                                if not await asyncio.to_thread(released.wait, 60):
                                    raise TimeoutError('held original ACK not released')
                            elif fault in ('drop','read-503'):
                                report['faults'].append(dict(kind='actual response delivery replaced by 503', actual_status=entry['status'], sha256=entry['sha256']))
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
                    endpoint = f'http://127.0.0.1:{port}'
                    server = uvicorn.Server(uvicorn.Config(observed, host='127.0.0.1', port=port, log_level='error', access_log=False))
                    api_thread = threading.Thread(target=server.run, daemon=True); api_thread.start()
                    deadline = time.monotonic() + 10
                    while not server.started:
                        if not api_thread.is_alive() or time.monotonic() > deadline: raise RuntimeError('API startup failed')
                        time.sleep(.02)

                    def proof(case):
                        result = dict(accounts={},provider_calls=model.calls-records[case]['provider_start'])
                        for key,subject in subjects[case].items():
                            scope=local_app.scope_for(local_app.ISSUER,subject)
                            with database.connect(scope) as conn:
                                role=conn.execute('SELECT current_user').fetchone()[0];assert role=='cj_m1_runtime'
                                rows=conn.execute('SELECT action_id,original_input,receipt FROM cj_memory_history_action WHERE scope=%s ORDER BY action_id',(scope,)).fetchall()
                                actions=[]
                                for aid,raw,receipt in rows:
                                    value=json.loads(bytes(raw));receipt=json.loads(bytes(receipt))
                                    assert set(value)=={'version','action_id','operation','conversation_id','expected_generation','expected_epoch','expected_source_version'}
                                    assert receipt['input_sha256']==hashlib.sha256(bytes(raw)).hexdigest()
                                    assert b'PRIVATE_HISTORY_INPUT' not in bytes(raw)
                                    actions.append(dict(action_id=aid,sha256=receipt['input_sha256'],conversation=value['conversation_id'],operation=value['operation'],source_version=receipt['source_version']))
                                consents=conn.execute('SELECT conversation_id,enabled,source_version FROM cj_memory_history_consent WHERE scope=%s ORDER BY conversation_id',(scope,)).fetchall()
                                memory=conn.execute('SELECT count(*) FROM cj_memory_item WHERE scope=%s',(scope,)).fetchone()[0]
                                jobs=conn.execute('SELECT count(*) FROM cj_memory_history_job WHERE scope=%s',(scope,)).fetchone()[0]
                            result['accounts'][key]=dict(role=role,actions=actions,consents=[dict(conversation=c,enabled=e,source_version=v) for c,e,v in consents],memory_items=memory,jobs=jobs)
                        with lock:
                            result['history_posts']=sum(x['method']=='POST' and x['path']=='/v3/memory-history-actions' for x in audit)
                            assert not any(x['method']=='POST' and x['path'].startswith('/internal/') for x in audit),'App dispatched an organizer job'
                        assert all(v['jobs']==0 for v in result['accounts'].values())
                        report['database_proofs'][case]=result;save();return result

                    class Control(BaseHTTPRequestHandler):
                        def log_message(self, *args): pass
                        def do_GET(self):
                            try:
                                parsed = urlsplit(self.path); query = {k: v[0] for k,v in parse_qs(parsed.query).items()}
                                case = query['case']
                                if case not in CASES: raise ValueError('unregistered case')
                                if parsed.path == '/prepare':
                                    conversation = 'cj434-' + uuid.uuid4().hex
                                    second='cj434-'+uuid.uuid4().hex;foreign='cj434-'+uuid.uuid4().hex
                                    with TestClient(app) as client:
                                        for cid,owner in ((conversation,'A'),(second,'A'),(foreign,'B')):
                                            client.put('/v1/conversations', params={'conversation_id': cid}, headers={'Authorization': 'Bearer ' + tokens[case][owner]}).raise_for_status()
                                    records[case] = dict(provider_start=model.calls, endpoint=endpoint, accounts=tokens[case], subjects=subjects[case], case_id=case, conversation=conversation,second_conversation=second,foreign_conversation=foreign,
                                                         profile=json.dumps(profile),prompt='PRIVATE_HISTORY_INPUT 保存一条偏好不授权全部历史 ' + conversation)
                                    value = records[case]
                                elif parsed.path == '/proof': value = proof(case)
                                elif parsed.path == '/fault':
                                    if query['kind'] not in ('drop', 'hold','read-503'): raise ValueError('unregistered fault')
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
                                elif parsed.path == '/other-change':
                                    with TestClient(app) as client:
                                        headers={'Authorization':'Bearer '+tokens[case]['A']}
                                        current=client.get('/v3/memory-history-settings',params={'conversation_id':records[case]['conversation']},headers=headers)
                                        current.raise_for_status();value=current.json()['result']
                                        original=dict(version='MEMORY-HISTORY@1',action_id='other-'+uuid.uuid4().hex,operation=query['operation'],conversation_id=value['conversation_id'],expected_generation=value['generation'],expected_epoch=value['epoch'],expected_source_version=value['source_version'])
                                        response=client.post('/v3/memory-history-actions',content=json.dumps(original).encode(),headers=dict(headers,**{'Content-Type':'application/octet-stream'}))
                                        response.raise_for_status()
                                    value=proof(case)
                                elif parsed.path == '/validate':
                                    value=proof(case)
                                    with TestClient(app) as client:
                                        for action in value['accounts']['A']['actions']:
                                            own={'Authorization':'Bearer '+tokens[case]['A']};foreign={'Authorization':'Bearer '+tokens[case]['B']}
                                            response=client.get('/v3/memory-history-receipts',params={'action_id':action['action_id']},headers=own)
                                            response.raise_for_status();assert response.json()['result']['input_sha256']==action['sha256']
                                            other=client.get('/v3/memory-history-receipts',params={'action_id':action['action_id']},headers=foreign)
                                            # B has no history domain. The published service's require_live
                                            # intentionally returns unavailable, never an absence/permission claim.
                                            assert other.status_code==503 and 'result' not in other.json()
                                            assert other.json()['error']['code']=='MEMORY_HISTORY_UNAVAILABLE'
                                            assert other.json()['error']['recovery']=='retry_safe_read'
                                        foreign={'Authorization':'Bearer '+tokens[case]['B']}
                                        denied=client.get('/v3/memory-history-settings',params={'conversation_id':records[case]['conversation']},headers=foreign)
                                        assert denied.status_code!=200 and 'result' not in denied.json()
                                        settings=client.get('/v3/memory-history-settings',params={'conversation_id':records[case]['conversation']},headers={'Authorization':'Bearer '+tokens[case]['A']})
                                        settings.raise_for_status();current=settings.json()['result']
                                        forged=dict(version='MEMORY-HISTORY@1',action_id='foreign-'+uuid.uuid4().hex,operation='enable',conversation_id=current['conversation_id'],expected_generation=current['generation'],expected_epoch=current['epoch'],expected_source_version=current['source_version'])
                                        denied=client.post('/v3/memory-history-actions',content=json.dumps(forged).encode(),headers=dict(foreign,**{'Content-Type':'application/octet-stream'}))
                                        assert denied.status_code==503 and 'result' not in denied.json()

                                    report['checks'][case]=dict(original_hash_receipt=True,foreign_source_refused=True,no_implicit_history_or_job=True)
                                    save()
                                else: raise ValueError('unsupported control')
                                raw = json.dumps(value).encode(); self.send_response(200); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(raw)
                            except Exception as error:
                                import traceback
                                report.setdefault('control_errors', []).append(dict(type=type(error).__name__, frames=[dict(function=f.name, line=f.lineno) for f in traceback.extract_tb(error.__traceback__)]))
                                save(); self.send_response(500); self.end_headers(); self.wfile.write(type(error).__name__.encode())
                    control = ThreadingHTTPServer(('127.0.0.1', 0), Control)
                    threading.Thread(target=control.serve_forever, daemon=True).start()
                    spec = importlib.util.spec_from_file_location('history_builder', ROOT / 'scripts/check_ios_trip_confirm.py')
                    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                    builder = object.__new__(module.XCTestDriver); builder.directory = output / 'project'; builder.directory.mkdir(); builder.write_project(0)
                    (builder.directory / 'G2CControl.swift').write_text((HERE / 'DevelopmentHistoryUITests.swift').read_text().replace('__FIXTURE_URL__', f'http://127.0.0.1:{control.server_port}'))
                    project = builder.directory / 'G2CAcceptance.xcodeproj'; pbx = project / 'project.pbxproj'
                    text = pbx.read_text().replace('space.go2china.foundation.local', BUNDLE).replace('space.go2china.foundation.control', BUNDLE + '.control')
                    entitlement = builder.directory / 'History.entitlements'; entitlement.write_bytes(plistlib.dumps({'application-identifier': BUNDLE, 'keychain-access-groups': [BUNDLE]}))
                    pbx.write_text(text.replace(json.dumps(str(ROOT / 'ios/App/Development.entitlements')), json.dumps(str(entitlement))))
                    for case in ([args.case] if args.case else CASES):
                        report['cases'][case] = 'RUNNING'; save()
                        result = output / (case + '.xcresult')
                        command = ['xcodebuild', '-project', str(project), '-scheme', 'G2CControl', '-configuration', 'Debug', '-destination', 'platform=iOS Simulator,id=' + args.simulator,
                            '-derivedDataPath', str(build), '-resultBundlePath', str(result), '-scmProvider', 'system', '-skipPackageUpdates', '-onlyUsePackageVersionsFromResolvedFile',
                            '-parallel-testing-enabled', 'NO', '-collect-test-diagnostics', 'never', 'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=YES', 'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGN_IDENTITY=-',
                            '-only-testing:G2CControl/DevelopmentHistoryUITests/' + case, 'test']
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
                    container = Path(subprocess.check_output(['xcrun', 'simctl', 'get_app_container', args.simulator, BUNDLE, 'data'], env=env, text=True).strip())
                    for path in [*container.rglob('*'), *output.rglob('*')]:
                        if path.is_file():
                            raw = path.read_bytes()
                            assert not any(token.encode() in raw for pair in tokens.values() for token in pair.values())
                            assert b'-----BEGIN PRIVATE KEY-----' not in raw
                            if path.is_relative_to(container): assert b'PRIVATE_HISTORY_INPUT' not in raw
                    assert not errors
                    assert all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == digest for p, digest in report['source_hashes'].items()), 'App source changed during native execution'
                    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == report['head'], 'App head changed during execution'
                    assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT), 'App working tree changed during execution'
                    report['checks']['source_hashes_unchanged'] = 'PASS'
                    report['checks']['token_private_key_and_app_plaintext_scan'] = 'PASS'
                    report['status'] = 'PARTIAL_PASS' if args.case else 'PASS'
                finally:
                    stop.set(); released.set()
                    if worker_thread: worker_thread.join(timeout=10)
                    if server: server.should_exit = True
                    if api_thread: api_thread.join(timeout=10)
                    if control: control.shutdown(); control.server_close(); control = None
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
        subprocess.run(['xcrun', 'simctl', 'terminate', args.simulator, BUNDLE], env=env, capture_output=True)
        report['worker_errors'] = errors; report['request_audit'] = audit
        if (worker_thread and worker_thread.is_alive()) or (api_thread and api_thread.is_alive()): report['status'] = 'FAIL'; report['shutdown'] = 'thread alive'
        save()


if __name__ == '__main__': main()
