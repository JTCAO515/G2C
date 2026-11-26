"""Actual invite client/account/Root over the B691 synthetic HTTP boundary.

No credential files, provider calls or existing simulator data are used. The
transport template is reused from the Root regression; product parsing stays
unchanged. Every invocation creates its own simulator and deletes it at the end.
"""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import subprocess
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from check_lio_warm_root import TRACE, fixture_object

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).parent
BASELINE = 'f15c126335717a334eba2044c4cd0ebc98c2bca1'


def source_pin():
    names = subprocess.check_output(['git', 'ls-files', 'ios'], cwd=ROOT, text=True).splitlines()
    files = [dict(path=name, sha256=hashlib.sha256((ROOT / name).read_bytes()).hexdigest()) for name in names
             if Path(name).suffix in ('.swift', '.py', '.json', '.plist', '.xcscheme')
             or Path(name).name in ('project.pbxproj', 'Package.resolved')]
    return dict(commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                files_sha256=hashlib.sha256(json.dumps(files, sort_keys=True, separators=(',', ':')).encode()).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--build-dir', type=Path, required=True)
    parser.add_argument('--language', choices=('en', 'zh-Hans'), required=True)
    parser.add_argument('--appearance', choices=('light', 'dark'), default='light')
    parser.add_argument('--scenario', choices=('valid', 'malformed'), default='valid')
    parser.add_argument('--baseline-client', action='store_true')
    parser.add_argument('--new-signin', action='store_true', help='turn on G2CNewSignInScreenEnabled (#1891)')
    args = parser.parse_args()
    output, build = args.output.resolve(), args.build_dir.resolve()
    if output.is_relative_to(ROOT) or build.is_relative_to(ROOT):
        parser.error('Keep generated projects and evidence outside the repository')
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    before = source_pin()
    simulator = subprocess.check_output(['xcrun', 'simctl', 'create', 'G2C-A-SignIn-Local-' + output.name,
        'com.apple.CoreSimulator.SimDeviceType.iPhone-15-Pro', 'com.apple.CoreSimulator.SimRuntime.iOS-17-5'], text=True).strip()
    report = dict(layer='local actual invite client/Root + synthetic HTTP only', simulator=simulator,
                  language=args.language, appearance=args.appearance, scenario=args.scenario, baseline_client=args.baseline_client,
                  new_signin=args.new_signin,
                  source=before, real_service='UNRUN', requests=[])
    lock = threading.Lock()

    def save():
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')

    class Server(BaseHTTPRequestHandler):
        def log_message(self, *unused): pass

        def send_json(self, value):
            raw = json.dumps(dict(request_id=TRACE, **value), separators=(',', ':')).encode()
            self.send_response(200)
            for key, val in [('Content-Type', 'application/json'), ('X-Request-ID', TRACE),
                             ('Cache-Control', 'no-store'), ('Content-Length', str(len(raw)))]:
                self.send_header(key, val)
            self.end_headers(); self.wfile.write(raw)

        def record(self, status=200):
            with lock:
                report['requests'].append(dict(method=self.command, path=urlsplit(self.path).path,
                                               status=status, time=datetime.now(timezone.utc).isoformat()))
                save()

        def body(self):
            if self.headers.get('Content-Length') is not None:
                size = int(self.headers['Content-Length'])
                if not 0 <= size <= 16384: raise ValueError('Fixture body size')
                return fixture_object(self.rfile.read(size))
            if self.headers.get('Transfer-Encoding', '').lower() != 'chunked': raise ValueError('Fixture body format')
            parts, size = [], 0
            while True:
                line = self.rfile.readline(128)
                if not line.endswith(b'\r\n'): raise ValueError('Fixture chunk header')
                amount = int(line.strip(), 16)
                if not 0 <= amount <= 16384 - size: raise ValueError('Fixture chunk size')
                if amount == 0:
                    if self.rfile.read(2) != b'\r\n': raise ValueError('Fixture ending')
                    return fixture_object(b''.join(parts))
                size += amount; part = self.rfile.read(amount)
                if len(part) != amount or self.rfile.read(2) != b'\r\n': raise ValueError('Fixture chunk length')
                parts.append(part)

        def do_POST(self):
            path = urlsplit(self.path).path
            try: value = self.body()
            except (ValueError, UnicodeError): self.record(400); self.send_error(400); return
            if path == '/v2/demo-invite-sessions':
                if value != dict(version='DEMO-invite-session.2', invite_code='D1-aaaaaaaaaaaa.bbbbbbbbbbbbbbbbbbbbbb', consent=True):
                    self.record(403); self.send_error(403); return
                self.record()
                if args.scenario == 'malformed': self.send_json(dict(version='broken-fixture')); return
                expiry = int(time.time()) + 604000
                subject = 'm4-synthetic-demo-aaaaaaaaaaaa'
                claims = dict(sub=subject, iss='https://local.g2c.invalid', aud='g2c-local', exp=expiry)
                payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')
                self.send_json(dict(version='DEMO-invite-session.2', access_token='b691fixture.' + payload + '.synthetic',
                                    subject=subject, expires_at=datetime.fromtimestamp(expiry, timezone.utc).isoformat()))
            elif path == '/v4/cleanup-devices' and self.headers.get('Authorization', '').startswith('Bearer b691fixture.'):
                self.record()
                self.send_json(dict(version='CLEANUP-DEVICE@4', binding_id='binding-signin-fixture',
                    device_id=value['device_id'], state_ref=value['state_ref'], scope_digest='a' * 64,
                    device_token='DEVICE.SYNTHETIC.SIGNIN', server_time=1000, business_access='not_granted'))
            else: self.record(403); self.send_error(403)

        def do_GET(self):
            path = urlsplit(self.path).path
            if not self.headers.get('Authorization', '').startswith('Bearer b691fixture.'):
                self.record(403); self.send_error(403); return
            if path not in ('/v1/message-receipts', '/v1/conversations', '/v1/needs', '/v1/lio/timeline',
                            '/v2/lio/timeline', '/v2/lio/messages') and not path.startswith('/v1/travel-context-actions/'):
                self.record(404); self.send_error(404); return
            self.record()
            if path == '/v1/message-receipts': self.send_json(dict(receipt=None))
            elif path == '/v1/conversations':
                self.send_json(dict(conversations=[dict(conversation_id='existing-' + str(i), generation='generation',
                    list_sequence=i + 1) for i in range(20)]))
            elif path == '/v1/needs': self.send_json(dict(needs=None))
            elif path.startswith('/v1/travel-context-actions/'): self.send_json(dict(receipt=None))
            elif path in ('/v1/lio/timeline', '/v2/lio/timeline'):
                self.send_json(dict(version='LIO-timeline.1' if path.startswith('/v1/') else 'LIO-timeline.2',
                    conversation_id='lio-dialogue-' + 'a' * 32, next_before=None, messages=[dict(
                        message_id='synthetic-existing-lio', text='Existing Lio question', answer='Existing Lio answer',
                        status='completed', sources=[])]))
            elif path == '/v2/lio/messages': self.send_json(dict(version='LIO-conversations.1', conversations=[]))
            else: self.send_error(404)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Server)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        endpoint = 'http://127.0.0.1:' + str(server.server_port)
        spec = importlib.util.spec_from_file_location('trip_builder', ROOT / 'scripts/check_ios_trip_confirm.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        builder = object.__new__(module.XCTestDriver); builder.directory = output; builder.write_project(0)
        tests = (HERE / 'LioSignInUITests.swift').read_text().replace('__SIGNIN_ENDPOINT__', endpoint)
        tests = tests.replace('__SIGNIN_LANGUAGE__', args.language).replace('__SIGNIN_SCENARIO__', args.scenario)
        tests = tests.replace('__SIGNIN_APPEARANCE__', args.appearance)
        tests = tests.replace('__SIGNIN_NEW_SCREEN__', '1' if args.new_signin else '0')
        tests = tests.replace('__SIGNIN_OK__', '好' if args.language == 'zh-Hans' else 'OK')
        tests = tests.replace('__SIGNIN_SOON_TEXT__', '即将开放' if args.language == 'zh-Hans' else 'coming soon')
        tests = tests.replace('__SIGNIN_ERROR_TEXT__', '登录暂未完成' if args.language == 'zh-Hans' else 'Sign-in could not be completed')
        (output / 'G2CControl.swift').write_text(tests)
        # Reuse the existing fail-closed B691 HTTP transport, extending only this
        # generated fixture's allowlist. The production endpoint stays fixed.
        transport = (HERE / 'LioWarmRootFixture.swift').read_text().split('@main struct LioWarmRootFixture: App')[0]
        assert transport.startswith('#if DEBUG')
        transport = transport.replace('private nonisolated final class WarmRootHTTP', 'nonisolated final class LioSignInFixtureHTTP')
        auth = 'request.value(forHTTPHeaderField: "Authorization")?.hasPrefix("Bearer b691fixture.") == true'
        assert transport.count(auth) == 1
        transport = transport.replace(auth, '(request.value(forHTTPHeaderField: "X-G2C-SignIn-Fixture") == "synthetic-only" && original.path == "/v2/demo-invite-sessions") || ' + auth)
        marker = '"/v1/message-receipts",'
        transport = transport.replace(marker, marker + ' "/v1/conversations", "/v1/needs", "/v1/travel-context-actions/demo-starter-zh-travel", "/v1/travel-context-actions/demo-starter-en-travel",')
        transport = transport.replace('["/v4/cleanup-devices",', '["/v2/demo-invite-sessions", "/v4/cleanup-devices",')
        entry = ROOT / 'ios/App/CJProbeApp.swift'
        combined = output / 'SignInApp.swift'
        combined.write_text(entry.read_text().replace('@main\nstruct CJProbeApp: App', 'struct CJProbeApp: App')
                            + '\n' + transport + '\n#endif\n' + (HERE / 'LioSignInFixture.swift').read_text())
        project = output / 'G2CAcceptance.xcodeproj'; pbx = project / 'project.pbxproj'; text = pbx.read_text()
        text = text.replace(json.dumps(str(entry)), json.dumps(str(combined)))
        text = text.replace('DEBUG G2C_LIO_APP', 'DEBUG G2C_LIO_APP G2C_DEMO_BETA')
        client_path = ROOT / 'ios/App/DemoInviteClient.swift'
        client = subprocess.check_output(['git', 'show', BASELINE + ':ios/App/DemoInviteClient.swift']).decode() if args.baseline_client else client_path.read_text()
        needle = 'let session = URLSession(configuration: configuration, delegate: DemoInviteRedirectBlocker(), delegateQueue: nil)'
        assert client.count(needle) == 2
        client = client.replace(needle, 'configuration.protocolClasses = [LioSignInFixtureHTTP.self]\n        configuration.httpAdditionalHeaders = ["X-G2C-SignIn-Fixture": "synthetic-only"]\n        ' + needle)
        generated_client = output / 'DemoInviteClient.swift'; generated_client.write_text(client)
        text = text.replace(json.dumps(str(client_path)), json.dumps(str(generated_client)))
        host = ROOT / 'ios/App/DevelopmentTripHost.swift'
        generated_host = output / 'DevelopmentTripHost.swift'
        generated_host.write_text(host.read_text() + '\n#if DEBUG && G2C_DEMO_BETA && targetEnvironment(simulator)\nextension DevelopmentAccountRoot { func fixtureHasNoSavedMaterial() throws -> Bool { try persistence.load() == nil } }\n#endif\n')
        text = text.replace(json.dumps(str(host)), json.dumps(str(generated_host)))
        text = text.replace('space.go2china.foundation.local', 'space.go2china.app').replace('space.go2china.foundation.control', 'space.go2china.signin.control')
        info = output / 'SignIn.Info.plist'; values = plistlib.loads((ROOT / 'ios/App/Info.plist').read_bytes())
        values.update(G2CDemoBeta=True, G2CB691LocalFixture=True)
        if args.new_signin: values['G2CNewSignInScreenEnabled'] = 'YES'
        info.write_bytes(plistlib.dumps(values))
        text = text.replace(json.dumps(str(ROOT / 'ios/App/Info.plist')), json.dumps(str(info)))
        entitlements = output / 'SignIn.entitlements'
        entitlements.write_bytes(plistlib.dumps({'application-identifier': 'space.go2china.app', 'keychain-access-groups': ['space.go2china.app']}))
        text = text.replace(json.dumps(str(ROOT / 'ios/App/Development.entitlements')), json.dumps(str(entitlements)))
        pbx.write_text(text)
        report['sources'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (combined, generated_client, generated_host, output / 'G2CControl.swift')}
        report['baseline_commit'] = subprocess.check_output(['git', 'rev-parse', BASELINE], text=True).strip() if args.baseline_client else None
        save()
        cmd = ['xcodebuild', '-project', str(project), '-scheme', 'G2CControl', '-destination', 'platform=iOS Simulator,id=' + simulator,
               '-derivedDataPath', str(build), '-resultBundlePath', str(output / 'signin.xcresult'), '-onlyUsePackageVersionsFromResolvedFile',
               '-parallel-testing-enabled', 'NO', 'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=YES', 'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGN_IDENTITY=-', 'test']
        env = {k: v for k, v in os.environ.items() if not k.startswith(('G2C_DEV_', 'SIMCTL_CHILD_'))}
        with (output / 'xcodebuild.log').open('w') as log:
            result = subprocess.run(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=900)
        report['xcodebuild_exit'] = result.returncode; save()
        report['source_unchanged'] = source_pin() == before; save()
        assert report['source_unchanged'], 'Source changed during the test; preserve result without qualifying it'
        summary = subprocess.check_output(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', str(output / 'signin.xcresult')])
        (output / 'summary.json').write_bytes(summary); value = json.loads(summary)
        # The largest-text case runs only with --new-signin and is skipped otherwise.
        assert value['passedTests'] == (2 if args.new_signin else 1) and value['failedTests'] == 0
        assert value['skippedTests'] == (0 if args.new_signin else 1)
        routes = [(r['method'], r['path']) for r in report['requests']]
        assert routes.count(('POST', '/v2/demo-invite-sessions')) == 1
        # #1891: the placeholder channels send nothing, so the invitation is the first request.
        if args.new_signin: assert routes[0] == ('POST', '/v2/demo-invite-sessions'), routes[:3]
        assert not any(p.startswith(('/v1/conversations', '/v1/needs', '/v1/travel-context-actions')) for _, p in routes)
        assert not any(method == 'POST' and path not in ('/v2/demo-invite-sessions', '/v4/cleanup-devices') for method, path in routes)
        if args.scenario == 'malformed': assert len(routes) == 1
    finally:
        server.shutdown(); server.server_close(); save()
        subprocess.run(['xcrun', 'simctl', 'shutdown', simulator], capture_output=True)
        # The simulator exists only for this run; delete it so they don't pile up on disk (JT 2026-11-26).
        subprocess.run(['xcrun', 'simctl', 'delete', simulator], capture_output=True)


if __name__ == '__main__': main()
