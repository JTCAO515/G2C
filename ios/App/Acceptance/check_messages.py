"""#164: actual App/XCTest + signed local API/private PG + Simulator Keychain.

No cloud, OTP or paid model. Faults are explicit local 503 injections before/after
real receipt commit. Generated UI-test project and all evidence stay outside Git.
"""
import argparse
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
BUNDLE = 'space.go2china.messages.acceptance'
sys.path.insert(0, str(ROOT / 'scripts'))
DEBUG_CASES = ['testNormalEnglish', 'testNormalChinese', 'testUnknownBeforeEnglish',
               'testUnknownBeforeChinese', 'testUnknownAfterEnglish', 'testUnknownAfterChinese']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulator', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--build-dir', type=Path)
    parser.add_argument('--diagnostic-test', choices=DEBUG_CASES + ['testReleaseClosed'])
    args = parser.parse_args()
    output = args.output.resolve(); build = (args.build_dir or output / 'dd').resolve()
    if output.is_relative_to(ROOT) or build.is_relative_to(ROOT):
        raise ValueError('Evidence/build output must be outside repository')
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'report.json').exists(): raise ValueError('Use a new output directory')
    env = {k: v for k, v in os.environ.items() if not k.startswith(('SIMCTL_CHILD_', 'G2C_DEV_', 'PG', 'LIBPQ'))}
    env.update(CJ_ENV='local', DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer')
    os.environ['CJ_ENV'] = 'local'
    devices = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '-j'], env=env))
    assert any('iOS-17-5' in runtime and d['udid'] == args.simulator
               for runtime, rows in devices['devices'].items() for d in rows)
    sources = [ROOT / 'ios/App/CJProbeApp.swift', ROOT / 'ios/App/DevelopmentTripHost.swift',
               ROOT / 'ios/App/DevelopmentSessionConfiguration.swift', ROOT / 'ios/Modules/CJShell/Package.swift']
    for directory in ('ios/Modules/CJMessageClient/Sources', 'ios/Modules/CJShell/Sources'):
        sources += list((ROOT / directory).rglob('*.swift'))
    report = dict(status='RUNNING', base_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  working_tree_dirty=bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT)),
                  scope='iOS17.5 actual App, signed synthetic identities, private PG, Simulator Keychain; no external service', cases={},
                  source_hashes={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(sources)})
    (output / 'report.json').write_text(json.dumps(report, indent=2))
    import psycopg
    import uvicorn
    import dev_auth
    import migrate
    from fastapi.testclient import TestClient
    from pg_suites import cluster
    from cj_api.local_app import app_from_environment, scope_for, ISSUER

    with tempfile.TemporaryDirectory(prefix='cj164-', dir='/tmp') as temporary:
        root = Path(temporary)
        with cluster('messages', port=55574, role='cj164_initializer', root=root / 'pg') as config:
            with psycopg.connect(**config, autocommit=True) as conn:
                chain = migrate.load(); migrate.up(conn, chain, chain[-1]['version'])
            connection = root / 'connection.json'; connection.write_text(json.dumps(config))
            subjects = {key: 'cj164-' + key.lower() + '-' + uuid.uuid4().hex[:8] for key in ('A', 'B')}
            auth = root / 'auth'; dev_auth.init(auth, list(subjects.values()))
            tokens = {key: dev_auth.token(auth, subject, 120) for key, subject in subjects.items()}
            os.environ.update(CJ_LOCAL_CONNINFO=str(connection), CJ_LOCAL_AUTH_DIR=str(auth))
            app = app_from_environment()
            primary = {key: 'chat-' + key + '-00' for key in subjects}
            last = {key: 'chat-' + key + '-20' for key in subjects}
            before = {key: 'recover-before-' + key for key in subjects}
            after = {key: 'recover-after-' + key for key in subjects}
            with TestClient(app) as client:
                for key in subjects:
                    headers = {'Authorization': 'Bearer ' + tokens[key]}
                    chats = [primary[key], before[key], after[key]] + ['chat-' + key + '-' + str(n).zfill(2) for n in range(1, 21)]
                    for cid in chats: client.put('/v1/conversations', params={'conversation_id': cid}, headers=headers).raise_for_status()
                    head = client.get('/v1/message-send-status', params={'conversation_id': primary[key]}, headers=headers).json()['head']
                    for n in range(21):
                        raw = json.dumps(dict(version='MESSAGE-send.1', conversation_id=primary[key], message_id=f'seed-{key}-{n:02}',
                            text=f'SEED {key} {n:02}', trip_id=None, creation_intent='none',
                            expected_generation=head['generation'], expected_sequence=head['last_sequence'])).encode()
                        result = client.post('/v1/messages', content=raw, headers={**headers, 'Content-Type': 'application/octet-stream'})
                        result.raise_for_status(); receipt = result.json()['receipt']
                        head = dict(generation=receipt['generation'], last_sequence=receipt['sequence'])
            with socket.socket() as port:
                port.bind(('127.0.0.1', 0)); api_port = port.getsockname()[1]
            endpoint = f'http://127.0.0.1:{api_port}'
            audit = []; lock = threading.Lock(); mode = {'drop': None}

            async def unavailable(send):
                trace = str(uuid.uuid4())
                body = json.dumps(dict(request_id=trace, error=dict(code='MESSAGE_OUTCOME_UNKNOWN', category='dependency',
                    message_en='Synthetic response loss', message_zh='合成响应丢失', outcome='unknown', recovery='reconcile_original'))).encode()
                await send(dict(type='http.response.start', status=503, headers=[(b'content-type', b'application/json'),
                    (b'x-request-id', trace.encode()), (b'content-length', str(len(body)).encode())]))
                await send(dict(type='http.response.body', body=body))

            async def observed(scope, receive, send):
                if scope['type'] != 'http': return await app(scope, receive, send)
                header = dict(scope.get('headers', [])).get(b'authorization', b'')
                account = next((k for k, token in tokens.items() if header == ('Bearer ' + token).encode()), None)
                query = parse_qs(scope.get('query_string', b'').decode())
                entry = dict(method=scope['method'], path=scope['path'], account=account,
                             conversation=query.get('conversation_id', [None])[0], message_id=query.get('message_id', [None])[0])
                is_message = scope['method'] == 'POST' and scope['path'] == '/v1/messages'
                if is_message:
                    chunks = []
                    while True:
                        item = await receive(); chunks.append(item.get('body', b''))
                        if not item.get('more_body', False): break
                    raw = b''.join(chunks); value = json.loads(raw)
                    entry.update(conversation=value['conversation_id'], message_id=value['message_id'], sha256=hashlib.sha256(raw).hexdigest())
                    consumed = False
                    upstream_receive = receive
                    async def replay():
                        nonlocal consumed
                        if consumed: return await upstream_receive()
                        consumed = True
                        return {'type': 'http.request', 'body': raw, 'more_body': False}
                    receive = replay
                with lock:
                    audit.append(entry)
                    fault = mode['drop'] if is_message else None
                    if is_message: mode['drop'] = None
                if fault == 'before': return await unavailable(send)
                if fault == 'after':
                    messages = []
                    async def capture(message): messages.append(message)
                    await app(scope, receive, capture)
                    assert messages[0]['status'] == 200, 'fault injection expected actual acceptance'
                    return await unavailable(send)
                return await app(scope, receive, send)

            server = uvicorn.Server(uvicorn.Config(observed, host='127.0.0.1', port=api_port, log_level='error', access_log=False))
            thread = threading.Thread(target=server.run, daemon=True); thread.start()
            deadline = time.monotonic() + 10
            while not server.started:
                if not thread.is_alive() or time.monotonic() > deadline: raise RuntimeError('API startup failed')
                time.sleep(.02)

            def proof(account, cid):
                if account not in subjects: raise ValueError('unknown fixture account')
                scope = scope_for(ISSUER, subjects[account])
                with psycopg.connect(**config) as conn:
                    rows = conn.execute('SELECT message_id,raw_input FROM cj_message_receipt WHERE scope=%s AND conversation_id=%s ORDER BY sequence', (scope, cid)).fetchall()
                    count = conn.execute('SELECT count(*) FROM cj_message_chat WHERE scope=%s', (scope,)).fetchone()[0]
                rows = [(mid, json.loads(bytes(raw))) for mid, raw in rows if json.loads(bytes(raw))['text'].startswith('CJ164 ')]
                with lock: calls = [dict(item) for item in audit]
                posts = [item for item in calls if item['method'] == 'POST' and item['account'] == account and item['conversation'] == cid]
                identities = {(item['message_id'], item['sha256']) for item in posts}
                return dict(posts=len(posts), receipts=len(rows), conversations=count,
                    message_id=rows[-1][0] if rows else None, creation_intent=rows[-1][1]['creation_intent'] if rows else None,
                    trip_is_null=all(row['trip_id'] is None for _, row in rows), matching_originals=len(identities) <= 1,
                    status_reads=sum(item['path'] == '/v1/message-send-status' and item['account'] == account and item['conversation'] == cid and item['message_id'] is not None for item in calls),
                    forbidden_writes=sum(item['method'] not in ('GET', 'HEAD') and item['path'] != '/v1/messages' for item in calls))

            class Control(BaseHTTPRequestHandler):
                def log_message(self, *args): pass
                def do_GET(self):
                    try:
                        parsed = urlsplit(self.path)
                        if parsed.path == '/config': value = dict(endpoint=endpoint, accounts=tokens, subjects=subjects, primary=primary, last=last, before=before, after=after)
                        elif parsed.path in ('/normal', '/before', '/after'):
                            with lock: mode['drop'] = None if parsed.path == '/normal' else parsed.path[1:]
                            value = {}
                        elif parsed.path == '/audit':
                            with lock: value = list(audit)
                        elif parsed.path == '/proof':
                            query = parse_qs(parsed.query); value = proof(query['account'][0], query['conversation'][0])
                        else: self.send_error(404); return
                        data = json.dumps(value).encode()
                        self.send_response(200); self.send_header('Content-Type', 'application/json')
                        self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
                    except Exception: self.send_error(500, 'local fixture control failed')
            control = ThreadingHTTPServer(('127.0.0.1', 0), Control)
            threading.Thread(target=control.serve_forever, daemon=True).start()
            try:
                spec = importlib.util.spec_from_file_location('trip_acceptance', ROOT / 'scripts/check_ios_trip_confirm.py')
                module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                builder = object.__new__(module.XCTestDriver)
                builder.directory = output / 'project'; builder.directory.mkdir(); builder.write_project(0)
                source = (HERE / 'DevelopmentMessageUITests.swift').read_text().replace('__FIXTURE_URL__', f'http://127.0.0.1:{control.server_port}')
                (builder.directory / 'G2CControl.swift').write_text(source)
                project = builder.directory / 'G2CAcceptance.xcodeproj'; pbx = project / 'project.pbxproj'
                text = pbx.read_text().replace('space.go2china.foundation.local', BUNDLE).replace('space.go2china.foundation.control', BUNDLE + '.control')
                entitlements = builder.directory / 'Development.entitlements'
                entitlements.write_bytes(plistlib.dumps({'application-identifier': BUNDLE, 'keychain-access-groups': [BUNDLE]}))
                text = text.replace(json.dumps(str(ROOT / 'ios/App/Development.entitlements')), json.dumps(str(entitlements)))
                line = next(line for line in text.splitlines() if line.startswith('A00000000000000000000004 = {isa = XCBuildConfiguration; name = Debug;'))
                release = line.replace('A00000000000000000000004', 'A0000000000000000000000C', 1).replace('name = Debug;', 'name = Release;', 1)
                text = text.replace(line, line + '\n' + release).replace('buildConfigurations = (A00000000000000000000004);', 'buildConfigurations = (A00000000000000000000004, A0000000000000000000000C);')
                pbx.write_text(text)
                variants = {'Debug': DEBUG_CASES, 'Release': ['testReleaseClosed']}
                if args.diagnostic_test:
                    report['unrun'] = [case for cases in variants.values() for case in cases if case != args.diagnostic_test]
                    variants = {'Release' if args.diagnostic_test == 'testReleaseClosed' else 'Debug': [args.diagnostic_test]}
                for configuration, tests in variants.items():
                    result = output / (configuration + '.xcresult')
                    command = ['xcodebuild', '-project', str(project), '-scheme', 'G2CControl', '-configuration', configuration,
                        '-destination', 'platform=iOS Simulator,id=' + args.simulator, '-derivedDataPath', str(build),
                        '-resultBundlePath', str(result), '-scmProvider', 'system', '-skipPackageUpdates', '-onlyUsePackageVersionsFromResolvedFile',
                        '-parallel-testing-enabled', 'NO', '-collect-test-diagnostics', 'never', 'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=YES',
                        'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGN_IDENTITY=-']
                    command += ['-only-testing:G2CControl/DevelopmentMessageUITests/' + case for case in tests]
                    print('Running native ' + configuration + ': ' + ', '.join(tests), flush=True)
                    run = subprocess.run(command + ['test'], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=1200)
                    log = run.stdout
                    for token in tokens.values(): log = log.replace(token, '<redacted-local-token>')
                    (output / (configuration + '.log')).write_text(log); run.check_returncode()
                    summary = json.loads(subprocess.check_output(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', str(result)], env=env))
                    (output / (configuration + '-summary.json')).write_text(json.dumps(summary, indent=2))
                    assert summary['passedTests'] == len(tests) and summary['failedTests'] == 0 and summary['skippedTests'] == 0
                    report['cases'][configuration] = dict(status='PASS', tests=tests)
                report['database_proofs'] = {key + '/' + cid: proof(key, cid) for key in subjects for cid in (primary[key], before[key], after[key])}
                container = Path(subprocess.check_output(['xcrun', 'simctl', 'get_app_container', args.simulator, BUNDLE, 'data'], env=env, text=True).strip())
                sealed = list(container.rglob('*.sealed'))
                if not args.diagnostic_test or args.diagnostic_test != 'testReleaseClosed': assert sealed, 'encrypted message snapshot missing'
                for path in container.rglob('*'):
                    if path.is_file() and not path.is_symlink():
                        data = path.read_bytes()
                        assert not any(token.encode() in data for token in tokens.values()), 'token in App data'
                        assert b'CJ164 unsent' not in data, 'unsent draft in plaintext App data'
                report['app_file_token_and_draft_scan'] = 'PASS'
                report['status'] = 'PARTIAL_PASS' if args.diagnostic_test else 'PASS'
            except BaseException as error:
                report['status'] = 'FAIL'; report['error'] = type(error).__name__; raise
            finally:
                server.should_exit = True; thread.join(timeout=10)
                control.shutdown(); control.server_close()
                subprocess.run(['xcrun', 'simctl', 'terminate', args.simulator, BUNDLE], env=env, capture_output=True)
                leaked = [str(path.relative_to(output)) for path in output.rglob('*') if path.is_file() and not path.is_symlink()
                          and any(token.encode() in path.read_bytes() for token in tokens.values())]
                report['artifact_token_scan'] = 'FAIL' if leaked else 'PASS'
                if leaked: report['status'] = 'FAIL'; report['token_artifacts'] = leaked
                (output / 'report.json').write_text(json.dumps(report, indent=2))
                if thread.is_alive(): raise RuntimeError('API did not stop')
                if leaked: raise RuntimeError('local token found in artifact')
    print(json.dumps({key: report[key] for key in ('status', 'cases', 'artifact_token_scan')}, indent=2))


if __name__ == '__main__': main()
