"""#161: actual App + native XCTest + local signed API/private PG; no real service."""
import argparse
import asyncio
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

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BUNDLE = 'space.go2china.accounts.acceptance'
sys.path.insert(0, str(ROOT / 'scripts'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulator', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--build-dir', type=Path)
    parser.add_argument('--diagnostic-test', choices=['testLifecycleEnglish', 'testLifecycleChinese', 'testFailuresEnglish', 'testFailuresChinese', 'testLateEnglish', 'testLateChinese'],
                        help='Run one failing scenario for diagnosis; remaining scenarios stay UNRUN')
    args = parser.parse_args()
    output = args.output.resolve()
    build = (args.build_dir or output / 'dd').resolve()
    if output.is_relative_to(ROOT) or build.is_relative_to(ROOT):
        raise ValueError('Evidence/build output must be outside repository')
    output.mkdir(parents=True, exist_ok=True)
    if (output / 'report.json').exists():
        raise ValueError('Use a new output directory; preserve previous results')
    env = {k: v for k, v in os.environ.items() if not k.startswith(('SIMCTL_CHILD_', 'G2C_DEV_', 'PG', 'LIBPQ'))}
    env.update(CJ_ENV='local', DEVELOPER_DIR='/Applications/Xcode.app/Contents/Developer')
    os.environ.update(CJ_ENV='local')
    devices = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '-j'], env=env))
    assert any('iOS-17-5' in runtime and d['udid'] == args.simulator
               for runtime, rows in devices['devices'].items() for d in rows)
    report = {'status': 'RUNNING', 'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'working_tree_dirty': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
              'scope': 'iOS17.5 actual App, signed local identities, real private PG and simulator Keychain; no OTP/cloud/model', 'cases': {}}
    (output / 'report.json').write_text(json.dumps(report, indent=2))

    import psycopg
    import uvicorn
    import dev_auth
    import migrate
    from pg_suites import cluster
    from cj_api.local_app import app_from_environment

    with tempfile.TemporaryDirectory(prefix='cj161-', dir='/tmp') as temporary:
        root = Path(temporary)
        with cluster('accounts', port=55571, role='cj161_initializer', root=root / 'pg') as config:
            with psycopg.connect(**config, autocommit=True) as conn:
                chain = migrate.load(); migrate.up(conn, chain, chain[-1]['version'])
            connection = root / 'connection.json'; connection.write_text(json.dumps(config))
            subjects = {key: 'cj161-' + key.lower() + '-' + uuid.uuid4().hex[:8] for key in ('A', 'B', 'Denied', 'Expired')}
            auth = root / 'auth'; dev_auth.init(auth, [subjects['A'], subjects['B'], subjects['Expired']])
            tokens = {key: dev_auth.token(auth, subject, -1 if key == 'Expired' else 60) for key, subject in subjects.items()}
            os.environ.update(CJ_LOCAL_CONNINFO=str(connection), CJ_LOCAL_AUTH_DIR=str(auth))
            app = app_from_environment()
            with socket.socket() as port:
                port.bind(('127.0.0.1', 0)); api_port = port.getsockname()[1]
            endpoint = f'http://127.0.0.1:{api_port}'
            audit = []; lock = threading.Lock(); held = threading.Event(); release = threading.Event()
            mode = {'hold': False}

            async def observed(scope, receive, send):
                if scope['type'] != 'http':
                    return await app(scope, receive, send)
                with lock: audit.append(scope['method'] + ' ' + scope['path'])
                header = dict(scope.get('headers', [])).get(b'authorization', b'')
                delay = mode['hold'] and scope['path'] == '/v1/message-receipts' and header == ('Bearer ' + tokens['A']).encode()
                if not delay:
                    return await app(scope, receive, send)
                messages = []
                async def capture(message): messages.append(message)
                await app(scope, receive, capture)  # real authentication and repository read first
                held.set()
                await asyncio.to_thread(release.wait, 20)
                for message in messages: await send(message)

            runtime = {'server': None, 'thread': None}
            def start():
                if runtime['thread'] is not None and runtime['thread'].is_alive(): return
                server = uvicorn.Server(uvicorn.Config(observed, host='127.0.0.1', port=api_port,
                    log_level='error', access_log=False, lifespan='off'))
                thread = threading.Thread(target=server.run, daemon=True)
                runtime.update(server=server, thread=thread); thread.start()
                for _ in range(100):
                    if server.started: return
                    if not thread.is_alive(): raise RuntimeError('local API exited')
                    time.sleep(.05)
                raise RuntimeError('local API startup timeout')
            def stop():
                release.set()
                if runtime['server'] is not None: runtime['server'].should_exit = True
                if runtime['thread'] is not None:
                    runtime['thread'].join(timeout=10)
                    if runtime['thread'].is_alive(): raise RuntimeError('local API did not stop')

            class Control(BaseHTTPRequestHandler):
                def log_message(self, *args): pass
                def do_GET(self):
                    try:
                        if self.path == '/config': value = dict(endpoint=endpoint, accounts=tokens, subjects=subjects)
                        elif self.path == '/offline': stop(); value = {}
                        elif self.path == '/online': start(); value = {}
                        elif self.path == '/normal': mode['hold'] = False; release.set(); start(); value = {}
                        elif self.path == '/hold': held.clear(); release.clear(); mode['hold'] = True; value = {}
                        elif self.path == '/wait-held': value = {'held': held.wait(timeout=10)}
                        elif self.path == '/release': mode['hold'] = False; release.set(); value = {}
                        elif self.path == '/audit':
                            with lock: value = list(audit)
                        else:
                            self.send_error(404); return
                        data = json.dumps(value).encode()
                        self.send_response(200); self.send_header('Content-Type', 'application/json')
                        self.send_header('Content-Length', str(len(data))); self.end_headers(); self.wfile.write(data)
                    except Exception:
                        self.send_error(500, 'local fixture control failed')

            control = ThreadingHTTPServer(('127.0.0.1', 0), Control)
            threading.Thread(target=control.serve_forever, daemon=True).start()
            start()
            try:
                spec = importlib.util.spec_from_file_location('trip_acceptance', ROOT / 'scripts/check_ios_trip_confirm.py')
                module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
                builder = object.__new__(module.XCTestDriver)
                builder.directory = output / 'project'; builder.directory.mkdir()
                builder.write_project(0)
                source = (HERE / 'DevelopmentAccountUITests.swift').read_text().replace('__FIXTURE_URL__', f'http://127.0.0.1:{control.server_port}')
                (builder.directory / 'G2CControl.swift').write_text(source)
                project = builder.directory / 'G2CAcceptance.xcodeproj'
                pbx = project / 'project.pbxproj'
                text = pbx.read_text().replace('space.go2china.foundation.local', BUNDLE).replace('space.go2china.foundation.control', BUNDLE + '.control')
                entitlements = builder.directory / 'Development.entitlements'
                entitlements.write_bytes(plistlib.dumps({'application-identifier': BUNDLE, 'keychain-access-groups': [BUNDLE]}))
                text = text.replace(json.dumps(str(ROOT / 'ios/App/Development.entitlements')), json.dumps(str(entitlements)))
                # The existing generator only has a Debug UITest config; add its Release counterpart externally.
                old = 'A00000000000000000000004 = {isa = XCBuildConfiguration; name = Debug;'
                config_line = next(line for line in text.splitlines() if line.startswith(old))
                release_line = config_line.replace('A00000000000000000000004', 'A0000000000000000000000C', 1).replace('name = Debug;', 'name = Release;', 1)
                text = text.replace(config_line, config_line + '\n' + release_line).replace('buildConfigurations = (A00000000000000000000004);', 'buildConfigurations = (A00000000000000000000004, A0000000000000000000000C);')
                pbx.write_text(text)
                variants = {'Debug': ['testLifecycleEnglish', 'testLifecycleChinese', 'testFailuresEnglish', 'testFailuresChinese', 'testLateEnglish', 'testLateChinese'],
                            'Release': ['testReleaseRemainsDisconnected']}
                if args.diagnostic_test:
                    report['unrun'] = [case for tests in variants.values() for case in tests if case != args.diagnostic_test]
                    variants = {'Debug': [args.diagnostic_test]}
                for configuration, tests in variants.items():
                    result = output / (configuration + '.xcresult')
                    command = ['xcodebuild', '-project', str(project), '-scheme', 'G2CControl', '-configuration', configuration,
                               '-destination', 'platform=iOS Simulator,id=' + args.simulator, '-derivedDataPath', str(build),
                               '-resultBundlePath', str(result), '-scmProvider', 'system', '-skipPackageUpdates',
                               '-onlyUsePackageVersionsFromResolvedFile', '-parallel-testing-enabled', 'NO',
                               '-collect-test-diagnostics', 'never', 'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=YES',
                               'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGN_IDENTITY=-']
                    command += ['-only-testing:G2CControl/DevelopmentAccountUITests/' + case for case in tests]
                    run = subprocess.run(command + ['test'], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=1200)
                    log = run.stdout
                    for token in tokens.values(): log = log.replace(token, '<redacted-local-token>')
                    (output / (configuration + '.log')).write_text(log)
                    run.check_returncode()
                    summary = json.loads(subprocess.check_output(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', str(result)], env=env))
                    (output / (configuration + '-summary.json')).write_text(json.dumps(summary, indent=2))
                    assert summary['passedTests'] == len(tests) and summary['failedTests'] == 0 and summary['skippedTests'] == 0
                    report['cases'][configuration] = {'status': 'PASS', 'tests': tests}
                    container = Path(subprocess.check_output(['xcrun', 'simctl', 'get_app_container', args.simulator, BUNDLE, 'data'], env=env, text=True).strip())
                    for path in container.rglob('*'):
                        if path.is_file() and not path.is_symlink():
                            content = path.read_bytes()
                            assert not any(token.encode() in content for token in tokens.values()), 'token in App data file'
                    report['cases'][configuration]['app_file_token_scan'] = 'PASS'
                report['status'] = 'PARTIAL_PASS' if args.diagnostic_test else 'PASS'
            except BaseException as error:
                report['status'] = 'FAIL'; report['error'] = type(error).__name__
                raise
            finally:
                release.set(); stop(); control.shutdown(); control.server_close()
                subprocess.run(['xcrun', 'simctl', 'terminate', args.simulator, BUNDLE], env=env, capture_output=True)
                leaked = []
                for path in output.rglob('*'):
                    if path.is_file() and not path.is_symlink():
                        if any(token.encode() in path.read_bytes() for token in tokens.values()):
                            leaked.append(str(path.relative_to(output)))
                report['artifact_token_scan'] = 'FAIL' if leaked else 'PASS'
                if leaked:
                    report['status'] = 'FAIL'
                    report['token_artifacts'] = leaked  # paths only, never token bytes
                (output / 'report.json').write_text(json.dumps(report, indent=2))
                if leaked: raise RuntimeError('local token found in test artifact')
    print(json.dumps(report, indent=2))


if __name__ == '__main__': main()
