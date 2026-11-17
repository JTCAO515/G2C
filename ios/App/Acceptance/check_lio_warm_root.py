"""Real App Root/account/clients with the existing B691 loopback seam; no live service.

Every invocation creates a fresh owned simulator before the canonical Beta
bundle/Keychain is used. No existing App account, journal or key is read/cleared.
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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

from lio_basic_ui_driver import decode

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).parent
BASELINE_COMMIT = 'c4db80a3258a0e3170c501eb4fdfa5fc1263ee12'
TRACE = '69169169-1691-4691-8691-691691691691'


def fixture_object(raw):
    value = decode(raw)
    if type(value) is not dict:
        raise ValueError('Local fixture JSON must be an object')
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--build-dir', type=Path, required=True)
    parser.add_argument('--language', choices=('en', 'zh-Hans'), default='en')
    parser.add_argument('--baseline-root', action='store_true')
    parser.add_argument('--cold-restart', action='store_true')
    parser.add_argument('--read-fault', choices=('service', 'connection-lost'), default='service')
    parser.add_argument('--denial-status', type=int, choices=(401, 403), default=401)
    parser.add_argument('--deny-after-cold', action='store_true')
    parser.add_argument('--initial-cold-fault', action='store_true')
    parser.add_argument('--scenario', choices=('session', 'timeline-timeout', 'lock-screen', 'cold-denial-notes'), default='session')
    parser.add_argument('--lock-fault', choices=('read', 'denied', 'timeline-timeout'), default='read')
    parser.add_argument('--simulator-control', type=Path, help='AXe executable for the explicit native lock-screen case only')
    args = parser.parse_args()
    if args.initial_cold_fault and not args.cold_restart:
        parser.error('Initial cold fault requires the cold-restart sequence')
    if args.scenario == 'lock-screen' and (args.simulator_control is None or not args.simulator_control.is_file()):
        parser.error('Native lock-screen scenario requires an existing --simulator-control executable')
    if args.scenario == 'lock-screen' and (args.baseline_root or args.cold_restart or args.deny_after_cold or args.initial_cold_fault):
        parser.error('Native lock-screen controls cannot claim baseline or cold-start coverage')
    if args.scenario != 'lock-screen' and args.lock_fault != 'read':
        parser.error('Lock fault selection requires the native lock-screen scenario')
    if args.scenario == 'lock-screen' and args.lock_fault != 'read' and args.read_fault != 'service':
        parser.error('Choose one native fault class')
    if args.scenario == 'cold-denial-notes' and (args.baseline_root or args.cold_restart or args.deny_after_cold
            or args.initial_cold_fault or args.read_fault != 'service' or args.simulator_control is not None):
        parser.error('Cold-denial notes requires its own explicit scope without baseline, alternate faults or native control')
    output = args.output.resolve()
    if output.is_relative_to(ROOT) or args.build_dir.resolve().is_relative_to(ROOT):
        parser.error('Keep evidence and products outside the repository')
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    simulator = subprocess.check_output(['xcrun', 'simctl', 'create', 'G2C-A-Warm-Root-Local-' + output.name,
        'com.apple.CoreSimulator.SimDeviceType.iPhone-15-Pro', 'com.apple.CoreSimulator.SimRuntime.iOS-17-5'], text=True).strip()
    report = dict(layer='actual Root/account/clients + synthetic loopback + fresh simulator', simulator=simulator,
                  language=args.language, cold_restart=args.cold_restart, read_fault=args.read_fault, initial_cold_fault=args.initial_cold_fault, denial_status=args.denial_status, deny_after_cold=args.deny_after_cold, baseline_root=args.baseline_root, baseline_commit=BASELINE_COMMIT if args.baseline_root else None,
                  scenario=args.scenario, lock_fault=args.lock_fault, real_service='UNRUN', requests=[])
    if args.scenario == 'cold-denial-notes':
        report.update(proof_transition='cold-restart', fixture_grant='legacy-default',
                      expected_note=f'signIn|sessionCheck|http|0|{args.denial_status}|{TRACE}')
    lock = threading.Lock()
    released = threading.Event(); released.set()
    finished = threading.Event()
    mode = ['ready']; resumed = [False]

    def save():
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    save()

    def has_identifier(value, identifier):
        if isinstance(value, dict):
            return value.get('AXUniqueId') == identifier or any(has_identifier(v, identifier) for v in value.values())
        if isinstance(value, list):
            return any(has_identifier(v, identifier) for v in value)
        return False

    def native_lock_state(phase, index):
        raw = subprocess.check_output(['xcrun', 'simctl', 'spawn', simulator, 'notifyutil',
            '-g', 'com.apple.springboard.lockstate'], timeout=5)
        (output / ('native-' + phase + '-state-' + str(index) + '.txt')).write_bytes(raw)
        fields = raw.decode().split()
        if len(fields) != 2 or fields[0] != 'com.apple.springboard.lockstate' or fields[1] not in ('0', '1'):
            raise ValueError('Unsupported simulator lock-state observation')
        return fields[1], hashlib.sha256(raw).hexdigest()

    def lock_screen():
        control = str(args.simulator_control.resolve())
        observation = dict(layer='native simulator cover sheet, not physical keybag', observed=False)
        def observe(identifier, phase):
            deadline = time.monotonic() + 5
            index = 0
            while time.monotonic() < deadline:
                raw = subprocess.check_output([control, 'describe-ui', '--udid', simulator], timeout=5)
                index += 1
                (output / (phase + '-native-' + str(index) + '.json')).write_bytes(raw)
                if has_identifier(json.loads(raw), identifier):
                    return hashlib.sha256(raw).hexdigest()
            raise TimeoutError('Native phase was not observed')
        try:
            # XCTest presses Home; acknowledge actual background presentation
            # before the single native lock command is dispatched.
            observation['home_snapshot_sha256'] = observe('Home screen icons', 'home')
            initial, initial_hash = native_lock_state('lock', 0)
            if initial != '0': raise ValueError('The fresh simulator must start unlocked')
            observation['initial_lock_state_sha256'] = initial_hash
            subprocess.run([control, 'button', 'lock', '--duration', '0.2', '--udid', simulator], check=True, capture_output=True, timeout=5)
            # A successful HID command is not a completed lock transition.
            deadline = time.monotonic() + 5
            index = 0
            while time.monotonic() < deadline:
                index += 1
                state, state_hash = native_lock_state('lock', index)
                if state == '1':
                    observation['locked_state_sha256'] = state_hash
                    break
                time.sleep(0.05)
            else: raise TimeoutError('Native simulator lock was not acknowledged')
            # Wake only after the actual transition, rather than racing the lock key.
            subprocess.run([control, 'button', 'side-button', '--udid', simulator], check=True, capture_output=True, timeout=5)
            observation.update(observed=True, native_snapshot_sha256=observe('SBCoverSheetWindow', 'lock'))
        except (subprocess.SubprocessError, ValueError, OSError) as error:
            observation['control_failure'] = type(error).__name__
        with lock:
            report['lock_control'] = observation
            save()
        return observation['observed']

    def observe_unlock():
        observation = dict(layer='native simulator cover sheet, not physical keybag', observed=False)
        try:
            deadline = time.monotonic() + 10
            index = 0
            while time.monotonic() < deadline:
                index += 1
                state, state_hash = native_lock_state('unlock', index)
                if state == '0':
                    observation.update(observed=True, native_state_sha256=state_hash)
                    break
                time.sleep(0.05)
        except (subprocess.SubprocessError, ValueError, OSError) as error:
            observation['control_failure'] = type(error).__name__
        with lock:
            report['unlock_control'] = observation
            save()
        return observation['observed']

    class Server(BaseHTTPRequestHandler):
        def log_message(self, *unused): pass
        def send_json(self, status, value):
            raw = json.dumps(dict(request_id=TRACE, **value), separators=(',', ':')).encode()
            self.send_response(status)
            for key, value in [('Content-Type', 'application/json'), ('X-Request-ID', TRACE),
                               ('Cache-Control', 'no-store'), ('Content-Length', str(len(raw)))]: self.send_header(key, value)
            self.end_headers()
            try: self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError): pass  # A cancelled local URLSession.
        def claims(self):
            auth = self.headers.get('Authorization', '')
            if not auth.startswith('Bearer b691fixture.') or not auth.endswith('.synthetic'): return None
            payload = auth.split('.')[1]
            try: claims = fixture_object(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
            except (ValueError, KeyError): return None
            return claims if claims.get('sub') in ('m4-synthetic-demo-aaaaaaaaaaaa', 'm4-synthetic-demo-bbbbbbbbbbbb') else None
        def record(self, status):
            with lock:
                report['requests'].append(dict(method=self.command, path=urlsplit(self.path).path, status=status))
                save()
        def do_GET(self):
            path = urlsplit(self.path).path
            claims = self.claims()
            if claims is None: self.send_error(403); return
            if path == '/v1/message-receipts':
                if not released.wait(timeout=15): self.record(503); self.send_json(503, {}); return
                with lock: current = mode[0]
                if current == 'offline' and args.read_fault == 'connection-lost':
                    self.record(None)
                    self.connection.shutdown(2); self.connection.close()
                    return
                status = args.denial_status if current == 'denied' else 503 if current == 'offline' else 200
                self.record(status)
                if status == 200: self.send_json(200, dict(receipt=None))
                else: self.send_json(status, dict(error=dict(code='ACCESS_DENIED' if status in (401, 403) else 'UNAVAILABLE',
                    category='access' if status in (401, 403) else 'dependency', message_en='Synthetic connection failure',
                    message_zh='本地合成连接失败', outcome='failed', recovery='do_not_retry')))
            elif path in ('/v1/lio/timeline', '/v2/lio/timeline'):
                with lock: current = mode[0]
                if current == 'timeline-timeout':
                    self.record(None)
                    # The real URLSession's five-second request timeout must fire
                    # before any response. No synthetic timeout is thrown in Swift.
                    finished.wait(timeout=12)
                    return
                other = claims['sub'].endswith('bbbbbbbbbbbb')
                rows = [dict(message_id='synthetic-root-b' if other else 'synthetic-root-a', text='Owner B question' if other else 'Existing owner A question',
                             answer='Independent owner B answer' if other else 'Existing owner A answer', status='completed', sources=[])]
                with lock: later = resumed[0]
                if not other and later:
                    rows.append(dict(message_id='synthetic-root-resumed', text='Same owner question', answer='Same owner after renewal', status='completed', sources=[]))
                self.record(200)
                self.send_json(200, dict(version='LIO-timeline.1' if path.startswith('/v1/') else 'LIO-timeline.2',
                    conversation_id='lio-dialogue-' + ('b' if other else 'a') * 32, messages=rows, next_before=None))
            elif path == '/v2/lio/messages':
                self.record(200); self.send_json(200, dict(version='LIO-conversations.1', conversations=[]))
            else: self.record(404); self.send_error(404)
        def body(self):
            length = self.headers.get('Content-Length')
            if length is not None:
                size = int(length)
                if not 0 <= size <= 16384: raise ValueError('Local fixture body limit')
                return fixture_object(self.rfile.read(size))
            if self.headers.get('Transfer-Encoding', '').lower() != 'chunked': raise ValueError('Local fixture body format')
            parts = []; size = 0
            while True:
                line = self.rfile.readline(128)
                if not line.endswith(b'\r\n'): raise ValueError('Local chunk header')
                amount = int(line.strip(), 16)
                if not 0 <= amount <= 16384 - size: raise ValueError('Local chunk limit')
                if amount == 0:
                    if self.rfile.read(2) != b'\r\n': raise ValueError('chunk ending')
                    return fixture_object(b''.join(parts))
                size += amount
                if size > 16384: raise ValueError('Local fixture body limit')
                part = self.rfile.read(amount)
                if len(part) != amount or self.rfile.read(2) != b'\r\n': raise ValueError('chunk length')
                parts.append(part)
        def do_POST(self):
            path = urlsplit(self.path).path
            try: value = self.body()
            except (ValueError, UnicodeError): self.send_error(400); return
            if path == '/fixture-lock-screen' and args.scenario == 'lock-screen' and value == {'action': 'observe-unlock'}:
                observed = observe_unlock()
                self.send_json(200 if observed else 503, dict(observed=observed)); return
            if path == '/fixture-lock-screen' and args.scenario == 'lock-screen' and value == {'action': 'lock'}:
                observed = lock_screen()
                self.send_json(200 if observed else 503, dict(observed=observed)); return
            if path == '/fixture-mode' and set(value) == {'mode'} and value['mode'] in ('ready', 'hold', 'offline', 'denied', 'timeline-timeout'):
                with lock:
                    mode[0] = value['mode']
                    if mode[0] == 'hold': resumed[0] = True; released.clear()
                    else: released.set()
                self.send_json(200, dict(accepted=True)); return
            if path == '/v4/cleanup-devices' and self.claims() is not None:
                self.record(200)
                self.send_json(200, dict(version='CLEANUP-DEVICE@4', binding_id='binding-warm-fixture',
                    device_id=value['device_id'], state_ref=value['state_ref'], scope_digest='a'*64,
                    device_token='DEVICE.SYNTHETIC.WARM', server_time=1000, business_access='not_granted')); return
            self.record(403); self.send_error(403)

    server = ThreadingHTTPServer(('127.0.0.1', 0), Server)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        endpoint = 'http://127.0.0.1:' + str(server.server_port)
        spec = importlib.util.spec_from_file_location('original_builder', ROOT / 'scripts/check_ios_trip_confirm.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        builder = object.__new__(module.XCTestDriver); builder.directory = output; builder.write_project(0)
        tests = (HERE / 'LioWarmRootUITests.swift').read_text().replace('__WARM_ENDPOINT__', endpoint).replace('__WARM_LANGUAGE__', args.language).replace('__WARM_COLD_RESTART__', '1' if args.cold_restart else '0').replace('__WARM_DENY_COLD__', '1' if args.deny_after_cold else '0').replace('__WARM_COLD_FAULT__', '1' if args.initial_cold_fault else '0').replace('__WARM_EXPECTED_PROBLEM__', ('0|sessionCheck|-' if args.read_fault == 'connection-lost' else '503|sessionCheck|' + TRACE)).replace('__WARM_EXPECTED_CATEGORY__', 'network' if args.read_fault == 'connection-lost' else 'service')
        tests = tests.replace('__WARM_DENIAL_STATUS__', str(args.denial_status)).replace('__WARM_TRACE__', TRACE)
        (output / 'G2CControl.swift').write_text(tests)
        entry = ROOT / 'ios/App/CJProbeApp.swift'
        source = entry.read_text().replace('@main\nstruct CJProbeApp: App', 'struct CJProbeApp: App')
        combined = output / 'WarmRootApp.swift'; combined.write_text(source + '\n' + (HERE / 'LioWarmRootFixture.swift').read_text())
        project = output / 'G2CAcceptance.xcodeproj'; pbx = project / 'project.pbxproj'; text = pbx.read_text()
        text = text.replace(json.dumps(str(entry)), json.dumps(str(combined)))
        text = text.replace('DEBUG G2C_LIO_APP', 'DEBUG G2C_LIO_APP G2C_DEMO_BETA')
        for name in ('DevelopmentTripHost.swift', 'DemoBetaApp.swift'):
            path = ROOT / 'ios/App' / name
            data = subprocess.check_output(['git', 'show', BASELINE_COMMIT + ':ios/App/' + name]).decode() if args.baseline_root else path.read_text()
            if name == 'DevelopmentTripHost.swift':
                data += '\n#if DEBUG && G2C_DEMO_BETA && targetEnvironment(simulator)\nextension DevelopmentAccountRoot {\n'
                data += '    func fixtureHasNoSavedMaterial() throws -> Bool { try persistence.load() == nil }\n'
                data += '    var fixtureHasRetained: Bool { ' + ('trip' if args.baseline_root else 'lioRetainedTrip') + ' != nil }\n'
                data += '    var fixtureDisplayID: UUID? { ' + ('trip?.id' if args.baseline_root else 'lioPresentationID') + ' }\n}\n#endif\n'
            generated = output / name; generated.write_text(data)
            text = text.replace(json.dumps(str(path)), json.dumps(str(generated)))
        text = text.replace('space.go2china.foundation.local', 'space.go2china.app').replace('space.go2china.foundation.control', 'space.go2china.warm-root.control')
        info = output / 'WarmRoot.Info.plist'; properties = plistlib.loads((ROOT / 'ios/App/Info.plist').read_bytes())
        properties.update(G2CDemoBeta=True, G2CB691LocalFixture=True); info.write_bytes(plistlib.dumps(properties))
        text = text.replace(json.dumps(str(ROOT / 'ios/App/Info.plist')), json.dumps(str(info)))
        entitlement = output / 'WarmRoot.entitlements'
        entitlement.write_bytes(plistlib.dumps({'application-identifier': 'space.go2china.app', 'keychain-access-groups': ['space.go2china.app']}))
        text = text.replace(json.dumps(str(ROOT / 'ios/App/Development.entitlements')), json.dumps(str(entitlement))); pbx.write_text(text)
        report['generated_source_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (combined, output/'DevelopmentTripHost.swift', output/'DemoBetaApp.swift', output/'G2CControl.swift')}
        save()
        command = ['xcodebuild', '-project', str(project), '-scheme', 'G2CControl', '-destination', 'platform=iOS Simulator,id='+simulator,
                   '-derivedDataPath', str(args.build_dir), '-resultBundlePath', str(output/'warm-root.xcresult'), '-onlyUsePackageVersionsFromResolvedFile',
                   '-parallel-testing-enabled', 'NO', 'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=YES', 'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGN_IDENTITY=-',
                   '-only-testing:G2CControl/LioWarmRootUITests/' + {
                       'session': 'testActualRootRetainsOnlyTheSameOwnerAndRetiresItsOriginalClients',
                       'timeline-timeout': 'testColdTimelineTimeoutKeepsTheSessionAndDraftAndNamesTheReadStage',
                       'cold-denial-notes': 'testColdAuthoritativeDenialKeepsItsOwnSafeProblemRecord',
                       'lock-screen': {
                           'read': 'testNativeLockScreenReturnsToTheSameChatAndDraftAfterAReadFailure',
                           'denied': 'testNativeLockScreenWithAuthoritativeDenialReturnsToSignIn',
                           'timeline-timeout': 'testNativeLockScreenTimelineTimeoutRetainsConversationAndDraft'
                       }[args.lock_fault]
                   }[args.scenario], 'test']
        env = {k: v for k, v in os.environ.items() if not k.startswith(('G2C_DEV_', 'SIMCTL_CHILD_'))}
        with (output/'xcodebuild.log').open('w') as log:
            subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=900)
        summary = subprocess.check_output(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', str(output/'warm-root.xcresult')])
        (output/'summary.json').write_bytes(summary)
        values = json.loads(summary)
        assert values['passedTests'] == 1 and values['failedTests'] == 0 and values['skippedTests'] == 0
        if args.scenario == 'cold-denial-notes':
            assert any(row['method'] == 'GET' and row['path'] == '/v1/message-receipts'
                       and row['status'] == args.denial_status for row in report['requests'])
        if args.scenario == 'timeline-timeout':
            reads = [row for row in report['requests'] if row['path'] in ('/v1/lio/timeline', '/v2/lio/timeline')]
            assert sum(row['status'] is None for row in reads) >= 2
            assert reads[-1]['status'] == 200
        if args.scenario == 'lock-screen':
            assert report['lock_control']['observed'] is True
            assert report['unlock_control']['observed'] is True
            if args.lock_fault == 'timeline-timeout':
                reads = [row for row in report['requests'] if row['path'] in ('/v1/lio/timeline', '/v2/lio/timeline')]
                assert any(row['status'] is None for row in reads)
                assert reads[-1]['status'] == 200
        assert not any(row['method']=='POST' and row['path']!='/v4/cleanup-devices' for row in report['requests'])
    finally:
        released.set(); finished.set(); server.shutdown(); server.server_close()
        stopped = subprocess.run(['xcrun', 'simctl', 'shutdown', simulator], capture_output=True, text=True)
        report['owned_simulator_shutdown_exit'] = stopped.returncode
        save()


if __name__ == '__main__': main()
