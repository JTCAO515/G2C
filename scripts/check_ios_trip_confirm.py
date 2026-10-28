"""Disposable iOS 17.5 Trip confirmation acceptance (local signed API + FakeProvider).

Requires Xcode with XCTest and PostgreSQL 17. A temporary native UI-test driver
operates the actual App. Output/evidence must be outside the repository. No cloud or paid
model is used. Tokens are passed only in SIMCTL_CHILD_ environment variables.
"""
import argparse
import asyncio
import contextlib
import json
import os
from pathlib import Path
import queue
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[1]
BUNDLE = 'space.go2china.foundation.local'


class XCTestDriver:
    """Native XCTest input for headless iOS 17; no Simulator.app/AXe dependency.

    The temporary project points at the actual App and sibling packages. It adds
    only an external UI-test target; the repository Xcode project is not expanded.
    The runner receives UI commands, never tokens or business API instructions.
    """
    def __init__(self, check):
        self.check = check
        self.commands = queue.Queue()
        self.answers = queue.Queue()
        self.ready = threading.Event()
        self.failed = False
        owner = self
        class Controller(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                owner.ready.set()
                try: command = owner.commands.get(timeout=1)
                except queue.Empty: command = {'kind': 'idle'}
                raw = json.dumps(command).encode()
                self.send_response(200); self.send_header('Content-Length', str(len(raw))); self.end_headers(); self.wfile.write(raw)
            def do_POST(self):
                owner.answers.put(json.loads(self.rfile.read(int(self.headers['Content-Length']))))
                self.send_response(200); self.send_header('Content-Length', '0'); self.end_headers()
        self.http = ThreadingHTTPServer(('127.0.0.1', 0), Controller)
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True); self.thread.start()
        self.directory = check.output / 'ui-driver'; self.directory.mkdir(exist_ok=True)
        self.write_project(self.http.server_port)
        self.log = (check.output / 'ui-driver.log').open('w')
        self.process = subprocess.Popen(['xcodebuild', '-project', str(self.directory / 'G2CAcceptance.xcodeproj'),
            '-scheme', 'G2CControl', '-destination', f'platform=iOS Simulator,id={check.args.simulator}',
            '-derivedDataPath', str(check.output / 'ui-dd'), '-scmProvider', 'system', '-skipPackageUpdates', '-onlyUsePackageVersionsFromResolvedFile',
            '-parallel-testing-enabled', 'NO', 'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=YES',
            'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGN_IDENTITY=-', 'test'],
            cwd=ROOT, env=os.environ, stdout=self.log, stderr=subprocess.STDOUT)
        deadline = time.monotonic() + 240
        while not self.ready.wait(.5):
            if self.process.poll() is not None or time.monotonic() >= deadline:
                self.close(force=True)
                raise RuntimeError('native UI runner did not start; inspect ui-driver.log')

    def write_project(self, port):
        source = r'''
import XCTest
import Foundation
@MainActor final class G2CControl: XCTestCase {
    func testDrive() async throws {
        continueAfterFailure = false
        let base = URL(string: "http://127.0.0.1:__PORT__")!
        let session = URLSession(configuration: .ephemeral)
        while true {
            let (data, _) = try await session.data(from: base.appendingPathComponent("next"))
            let command = try JSONSerialization.jsonObject(with: data) as! [String: Any]
            let kind = command["kind"] as! String
            if kind == "idle" { continue }
            var result: [String: Any] = ["id": command["id"]!, "ok": true]
            let app = XCUIApplication(bundleIdentifier: "space.go2china.foundation.local")
            if kind == "terminate" {
                if app.state != .notRunning { app.terminate() }
            } else if kind != "stop" {
                if app.state != .notRunning && app.state != .runningForeground { app.activate() }
                if !app.wait(for: .runningForeground, timeout: 5) {
                    result["nodes"] = [[String: Any]]()
                    if kind != "snapshot" { result["error"] = "App not running" }
                } else if kind == "tap" {
                    let label = command["label"] as! String
                    let point = CGPoint(x: (command["x"] as! NSNumber).doubleValue, y: (command["y"] as! NSNumber).doubleValue)
                    func matches(_ node: any XCUIElementSnapshot) -> Bool {
                        if node.elementType == .button && node.label == label && node.isEnabled && node.frame.contains(point) { return true }
                        return node.children.contains(where: matches)
                    }
                    if matches(try app.snapshot()) {
                        app.coordinate(withNormalizedOffset: CGVector(dx: 0, dy: 0)).withOffset(CGVector(dx: point.x, dy: point.y)).tap()
                    } else { result["error"] = "Current button not found at observed point: " + label }
                } else if kind == "swipe" {
                    app.swipeUp()
                } else if kind == "snapshot" {
                    func node(_ element: any XCUIElementSnapshot, type: String) -> [String: Any] {
                        let r = element.frame.isNull || element.frame.isInfinite ? CGRect.zero : element.frame
                        return ["AXLabel": element.label, "AXUniqueId": element.identifier,
                            "type": type, "enabled": element.isEnabled,
                            "frame": ["x": r.minX, "y": r.minY, "width": r.width, "height": r.height]]
                    }
                    // One immutable snapshot avoids per-element identity races while
                    // async confirmation replaces the view's loading/result children.
                    let snapshot = try app.snapshot()
                    var nodes = [[String: Any]]()
                    func visit(_ element: any XCUIElementSnapshot) {
                        let type = element.elementType == .application ? "Application" : element.elementType == .button ? "Button" : element.elementType == .staticText ? "StaticText" : "Other"
                        nodes.append(node(element, type: type))
                        element.children.forEach(visit)
                    }
                    visit(snapshot); result["nodes"] = nodes
                }
            }
            var request = URLRequest(url: base.appendingPathComponent("result"))
            request.httpMethod = "POST"
            request.httpBody = try JSONSerialization.data(withJSONObject: result)
            _ = try await session.data(for: request)
            if kind == "stop" { break }
        }
    }
}
'''.replace('__PORT__', str(port))
        swift = self.directory / 'G2CControl.swift'; swift.write_text(source)
        project = self.directory / 'G2CAcceptance.xcodeproj'; project.mkdir(exist_ok=True)
        pbx = (ROOT / 'ios/CJProbeApp.xcodeproj/project.pbxproj').read_text()
        quote = lambda value: json.dumps(str(value))
        pbx = re.sub(r'path = (App/[^;]+);', lambda m: 'path = ' + quote(ROOT / 'ios' / m[1]) + ';', pbx)
        pbx = re.sub(r'path = "(Branding/[^"]+)";', lambda m: 'path = ' + quote(ROOT / 'ios' / m[1]) + ';', pbx)
        pbx = pbx.replace('relativePath = Modules/CJShell;', 'relativePath = ' + quote(ROOT / 'ios/Modules/CJShell') + ';')
        for key, path in [('INFOPLIST_FILE', 'App/Info.plist'), ('\"CODE_SIGN_ENTITLEMENTS[sdk=iphonesimulator*]\"', 'App/Development.entitlements')]:
            pbx = pbx.replace(f'{key} = {path};', f'{key} = ' + quote(ROOT / 'ios' / path) + ';')
        ids = {i: f'A{i:023X}' for i in range(1, 12)}
        app = '000000000000000000000004'; root = '000000000000000000000001'
        pbx = pbx.replace(f'targets = ({app});', f'targets = ({app}, {ids[1]});')
        pbx = pbx.replace('isa = PBXProject;', f'isa = PBXProject; attributes = {{ TargetAttributes = {{ {ids[1]} = {{ TestTargetID = {app}; }}; }}; }};')
        entries = f'''
{ids[1]} = {{isa = PBXNativeTarget; name = G2CControl; productName = G2CControl; productType = "com.apple.product-type.bundle.ui-testing"; productReference = {ids[2]}; buildConfigurationList = {ids[3]}; buildPhases = ({ids[7]}, {ids[8]}, {ids[9]}); buildRules = (); dependencies = ({ids[10]}); }};
{ids[2]} = {{isa = PBXFileReference; explicitFileType = wrapper.cfbundle; path = G2CControl.xctest; sourceTree = BUILT_PRODUCTS_DIR; }};
{ids[3]} = {{isa = XCConfigurationList; buildConfigurations = ({ids[4]}); defaultConfigurationIsVisible = 0; defaultConfigurationName = Debug; }};
{ids[4]} = {{isa = XCBuildConfiguration; name = Debug; buildSettings = {{SDKROOT = iphoneos; IPHONEOS_DEPLOYMENT_TARGET = 17.0; SWIFT_VERSION = 6.0; PRODUCT_BUNDLE_IDENTIFIER = space.go2china.foundation.control; PRODUCT_NAME = "$(TARGET_NAME)"; GENERATE_INFOPLIST_FILE = YES; TEST_TARGET_NAME = CJProbeApp; CODE_SIGNING_ALLOWED = YES; CODE_SIGN_IDENTITY = "-"; TARGETED_DEVICE_FAMILY = 1; LD_RUNPATH_SEARCH_PATHS = "$(inherited) @executable_path/Frameworks @loader_path/Frameworks"; }}; }};
{ids[5]} = {{isa = PBXFileReference; lastKnownFileType = sourcecode.swift; path = {quote(swift)}; sourceTree = "<absolute>"; }};
{ids[6]} = {{isa = PBXBuildFile; fileRef = {ids[5]}; }};
{ids[7]} = {{isa = PBXSourcesBuildPhase; buildActionMask = 2147483647; files = ({ids[6]}); runOnlyForDeploymentPostprocessing = 0; }};
{ids[8]} = {{isa = PBXFrameworksBuildPhase; buildActionMask = 2147483647; files = (); runOnlyForDeploymentPostprocessing = 0; }};
{ids[9]} = {{isa = PBXResourcesBuildPhase; buildActionMask = 2147483647; files = (); runOnlyForDeploymentPostprocessing = 0; }};
{ids[10]} = {{isa = PBXTargetDependency; target = {app}; targetProxy = {ids[11]}; }};
{ids[11]} = {{isa = PBXContainerItemProxy; containerPortal = {root}; proxyType = 1; remoteGlobalIDString = {app}; remoteInfo = CJProbeApp; }};
'''
        pbx = pbx.replace('};\nrootObject', entries + '};\nrootObject')
        (project / 'project.pbxproj').write_text(pbx)
        lock = project / 'project.xcworkspace/xcshareddata/swiftpm/Package.resolved'
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_bytes((ROOT / 'ios/CJProbeApp.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved').read_bytes())
        schemes = project / 'xcshareddata/xcschemes'; schemes.mkdir(parents=True, exist_ok=True)
        ref = lambda target, name: f'<BuildableReference BuildableIdentifier="primary" BlueprintIdentifier="{target}" BuildableName="{name}" BlueprintName="{name.split(".")[0]}" ReferencedContainer="container:G2CAcceptance.xcodeproj"/>'
        (schemes / 'G2CControl.xcscheme').write_text(f'''<?xml version="1.0" encoding="UTF-8"?>
<Scheme LastUpgradeVersion="2700" version="1.3"><BuildAction parallelizeBuildables="YES" buildImplicitDependencies="YES"><BuildActionEntries>
<BuildActionEntry buildForTesting="YES" buildForRunning="YES" buildForProfiling="NO" buildForArchiving="NO" buildForAnalyzing="YES">{ref(app, 'CJProbeApp.app')}</BuildActionEntry>
<BuildActionEntry buildForTesting="YES" buildForRunning="NO" buildForProfiling="NO" buildForArchiving="NO" buildForAnalyzing="YES">{ref(ids[1], 'G2CControl.xctest')}</BuildActionEntry>
</BuildActionEntries></BuildAction><TestAction buildConfiguration="Debug" selectedDebuggerIdentifier="Xcode.DebuggerFoundation.Debugger.LLDB" selectedLauncherIdentifier="Xcode.IDEFoundation.Launcher.LLDB" shouldUseLaunchSchemeArgsEnv="NO"><Testables><TestableReference skipped="NO">{ref(ids[1], 'G2CControl.xctest')}</TestableReference></Testables></TestAction></Scheme>''')

    def command(self, kind, **values):
        if self.failed or self.process.poll() is not None:
            raise RuntimeError('native UI runner is unavailable')
        command_id = uuid.uuid4().hex
        self.commands.put(dict(kind=kind, id=command_id, **values))
        try: answer = self.answers.get(timeout=60)
        except queue.Empty:
            self.failed = True
            raise RuntimeError('native UI command timed out') from None
        if answer.get('id') != command_id or answer.get('error'):
            raise RuntimeError(answer.get('error', 'native UI result mismatch'))
        return answer

    def close(self, force=False):
        try:
            if not force and not self.failed and self.process.poll() is None:
                self.command('stop'); self.process.wait(timeout=30)
            if self.process.poll() is None:
                self.process.terminate(); self.process.wait(timeout=10)
            if not force and not self.failed and self.process.returncode != 0:
                raise RuntimeError('native XCTest runner failed; inspect ui-driver.log')
        finally:
            self.http.shutdown(); self.http.server_close(); self.log.close()


def serve_fixture(root):
    import uvicorn
    from cj_api.local_app import app_from_environment
    app = app_from_environment()  # the actual signed entry; no permissive factory
    async def observed(scope, receive, send):
        is_action = scope.get('type') == 'http' and scope.get('method') == 'POST' and scope.get('path') == '/v1/trip-actions'
        if is_action:
            with (root / 'act-requests').open('a') as stream:
                stream.write('act\n'); stream.flush(); os.fsync(stream.fileno())
        lose_response = is_action and (root / 'lose-response').exists()
        async def forward(message):
            if lose_response:
                # The route/transaction has completed, but NO response reaches the
                # client. The controller now kills this disposable API process.
                if message['type'] == 'http.response.body' and not message.get('more_body', False):
                    (root / 'response-committed').touch()
                    await asyncio.Future()
            else:
                await send(message)
        await app(scope, receive, forward)
    uvicorn.run(observed, host='127.0.0.1', port=int(os.environ['G2C_FIXTURE_PORT']),
                log_level='error', access_log=False)


class Check:
    def __init__(self, args):
        self.args = args
        self.output = Path(args.output).resolve()
        if self.output.is_relative_to(ROOT.resolve()):
            raise ValueError('evidence output must be outside the repository')
        self.output.mkdir(parents=True, exist_ok=True)
        self.secrets = []
        previous = self.output / 'report.json'
        if previous.exists():
            history = self.output / 'reports'; history.mkdir(exist_ok=True)
            (history / (uuid.uuid4().hex + '.json')).write_bytes(previous.read_bytes())
        self.results = {'status': 'RUNNING'}
        previous.write_text(json.dumps(self.results))
        self.driver = None

    def redact(self, value):
        for secret in self.secrets:
            value = value.replace(secret, '<redacted-token>')
        return value

    def run(self, command, *, env=None, log=None, check=True):
        result = subprocess.run(list(map(str, command)), cwd=ROOT, env=env, capture_output=True, text=True)
        text = self.redact(result.stdout + result.stderr)
        if log:
            (self.output / log).write_text(text)
        if check and result.returncode:
            raise RuntimeError(f'{Path(str(command[0])).name} failed ({result.returncode}); {text[-1600:]}')
        return result

    def sim(self, *args, **kwargs):
        return self.run(['xcrun', 'simctl', *args], **kwargs)

    def ui(self):
        return self.driver.command('snapshot')['nodes']

    @staticmethod
    def nodes(tree):
        if isinstance(tree, list):
            for node in tree:
                yield from Check.nodes(node)
        elif isinstance(tree, dict):
            yield tree
            yield from Check.nodes(tree.get('children', []))

    def wait(self, predicate, description, timeout=20):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            if predicate():
                return
            time.sleep(0.25)
        raise AssertionError(description)

    def has_label(self, label):
        return any(n.get('AXLabel') == label for n in self.nodes(self.ui()))

    def tap(self, label):
        # Scroll actual UI, never call the domain action on behalf of the user.
        for _ in range(12):
            tree = self.ui(); nodes = list(self.nodes(tree)); frame = nodes[0]['frame']
            candidates = [n for n in nodes if n.get('AXLabel') == label and n.get('type') == 'Button' and n.get('enabled')]
            visible = [n for n in candidates if 50 < n['frame']['y'] + n['frame']['height'] / 2 < frame['height'] - 90]
            (self.output / 'last-ui.json').write_text(json.dumps(tree, ensure_ascii=False, indent=2))
            if visible:
                target = visible[0]['frame']
                self.driver.command('tap', label=label, x=target['x'] + target['width'] / 2, y=target['y'] + target['height'] / 2)
                return
            if self.has_label('Development trip connection unavailable') or self.has_label('开发行程连接不可用'):
                raise AssertionError('development composition failed; no action was performed')
            self.driver.command('swipe')
        self.capture('tap-failed')
        raise AssertionError(f'visible enabled button missing: {label}')

    def capture(self, name):
        (self.output / f'{name}.json').write_text(json.dumps(self.ui(), ensure_ascii=False, indent=2))
        self.sim('io', self.args.simulator, 'screenshot', self.output / f'{name}.png')

    def launch(self, token=None, proposal=None, language='en', endpoint=None):
        self.driver.command('terminate')
        env = {k: v for k, v in os.environ.items() if not k.startswith('SIMCTL_CHILD_')}
        if endpoint is not None:
            env['SIMCTL_CHILD_G2C_DEV_API_BASE_URL'] = endpoint
        if token is not None:
            env['SIMCTL_CHILD_G2C_DEV_TOKEN'] = token
        if proposal is not None:
            env['SIMCTL_CHILD_G2C_DEV_PROPOSAL_ID'] = proposal
        self.sim('launch', self.args.simulator, BUNDLE, '-cj.ui.language.v1', language, env=env)
        self.wait(lambda: any(n.get('AXLabel') == 'G2C' for n in self.nodes(self.ui())), 'App did not launch')
        time.sleep(.5)

    def build(self):
        for configuration in ('debug', 'release'):
            self.run(['swift', 'test', '--package-path', 'ios/App', '--scratch-path', self.output / 'config-tests',
                      '-c', configuration], log=f'config-{configuration}.log')
        for configuration in ('Debug', 'Release'):
            self.run(['xcodebuild', '-project', 'ios/CJProbeApp.xcodeproj', '-scheme', 'CJProbeApp',
                '-configuration', configuration, '-destination', f'platform=iOS Simulator,id={self.args.simulator}',
                '-derivedDataPath', self.output / 'dd', '-scmProvider', 'system', '-skipPackageUpdates', '-onlyUsePackageVersionsFromResolvedFile',
                'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=YES',
                'CODE_SIGNING_ALLOWED=YES' if configuration == 'Debug' else 'CODE_SIGNING_ALLOWED=NO',
                'CODE_SIGN_IDENTITY=-', 'build'], log=f'build-{configuration}.log')
        self.debug_app = self.output / 'dd/Build/Products/Debug-iphonesimulator/CJProbeApp.app'
        self.release_app = self.output / 'dd/Build/Products/Release-iphonesimulator/CJProbeApp.app'
        # Xcode supplies simulator-only embedded entitlements and ad-hoc signing.
        # Do not manually sign the host process with restricted iOS entitlements.
        # No Apple account, certificate, provisioning profile or system setting changes.
        release_strings = self.run(['strings', self.release_app / 'CJProbeApp']).stdout
        if 'G2C_DEV_TOKEN' in release_strings or 'G2C_DEV_API_BASE_URL' in release_strings:
            raise AssertionError('Release binary contains development activation inputs')
        self.results['configuration_debug_release'] = 'PASS'

    def check(self):
        if not os.environ.get('DEVELOPER_DIR') or not os.environ.get('CJ_PG_BINDIR'):
            raise ValueError('explicit DEVELOPER_DIR and CJ_PG_BINDIR are required')
        inventory = json.loads(self.sim('list', 'devices', 'available', '-j').stdout)
        devices = [(runtime, d) for runtime, values in inventory['devices'].items() for d in values if d['udid'] == self.args.simulator]
        if len(devices) != 1 or 'iOS-17-5' not in devices[0][0]:
            raise ValueError('the acceptance simulator must run iOS 17.5')
        if devices[0][1]['state'] != 'Booted':
            self.sim('boot', self.args.simulator)
        self.sim('bootstatus', self.args.simulator, '-b')
        print('Building Debug/Release and checking activation boundaries', flush=True)
        self.build()
        print('Starting native XCTest UI driver', flush=True)
        self.driver = XCTestDriver(self)
        self.sim('install', self.args.simulator, self.debug_app)
        self.launch()
        self.wait(lambda: self.has_label('This service is not connected yet. No records have been loaded.'), 'missing environment enabled a host')
        self.results['missing_environment'] = 'PASS'
        self.capture('missing-environment')
        self.fixture()

    def fixture(self):
        import httpx
        import psycopg
        from fastapi.testclient import TestClient
        import dev_auth
        import migrate
        from pg_suites import cluster
        from cj_api.local_app import app_from_environment, LocalDatabase, scope_for, ISSUER
        from cj_agent.worker import RunWorker
        from cj_agent.draft import DraftPublisher
        from cj_agent.provider import FakeProvider
        from cj_message.domain import Service as MessageService
        from cj_run.core import Service as RunService

        with tempfile.TemporaryDirectory(prefix='g2c-ios-trip-', dir='/tmp') as temp:
            root = Path(temp)
            with cluster('ios-trip', port=55491, role='cj_ios_trip', root=root / 'pg') as config:
                with psycopg.connect(**config, autocommit=True) as connection:
                    chain = migrate.load(); migrate.up(connection, chain, chain[-1]['version'])
                config_file = root / 'connection.json'; config_file.write_text(json.dumps(config))
                subjects = {case: 'ui-' + uuid.uuid4().hex for case in ('en', 'zh', 'reject', 'unknown', 'foreign', 'en-next')}
                subjects['en-next'] = subjects['en']
                auth = root / 'auth'; dev_auth.init(auth, list(subjects.values()))
                env = dict(os.environ, CJ_ENV='local', CJ_LOCAL_CONNINFO=str(config_file), CJ_LOCAL_AUTH_DIR=str(auth))
                os.environ.update({k: env[k] for k in ('CJ_ENV', 'CJ_LOCAL_CONNINFO', 'CJ_LOCAL_AUTH_DIR')})
                tokens = {case: dev_auth.token(auth, subject, 60) for case, subject in subjects.items()}
                self.secrets.extend(tokens.values())
                database = LocalDatabase(config_file)
                proposals = {}
                with TestClient(app_from_environment()) as api:
                    for case in ('en', 'zh', 'reject', 'unknown', 'en-next'):
                        subject, token = subjects[case], tokens[case]
                        headers = {'Authorization': 'Bearer ' + token}
                        conversation, message = uuid.uuid4().hex, uuid.uuid4().hex
                        api.put('/v1/conversations', params={'conversation_id': conversation}, headers=headers).raise_for_status()
                        status = api.get('/v1/message-send-status', params={'conversation_id': conversation}, headers=headers)
                        status.raise_for_status()
                        head = status.json()['head']
                        payload = dict(version='MESSAGE-send.1', conversation_id=conversation, message_id=message,
                            text='北京三日游' if case == 'zh' else 'Three days in Beijing', trip_id=None, creation_intent='consider_trip',
                            expected_generation=head['generation'], expected_sequence=head['last_sequence'])
                        received = api.post('/v1/messages', content=json.dumps(payload, ensure_ascii=False).encode(),
                            headers={**headers, 'Content-Type': 'application/octet-stream'})
                        received.raise_for_status()
                        scope = scope_for(ISSUER, subject)
                        messages = MessageService(database.message_repository(scope), new_run_id=lambda: None)
                        runs = RunService(database.run_repository(scope), valid=lambda b: messages.query(b.message_id) is not None)
                        RunWorker(scope=scope, messages=messages, runs=runs, provider=FakeProvider(),
                                  drafts=DraftPublisher(database.trip_repository(scope))).process()
                        pid = 'p-' + received.json()['receipt']['run_id']
                        response = api.get('/v1/trip-proposals', params={'proposal_id': pid}, headers=headers)
                        response.raise_for_status(); proposals[case] = response.json()['proposal']
                with socket.socket() as free_port:
                    free_port.bind(('127.0.0.1', 0)); port = free_port.getsockname()[1]
                endpoint = f'http://127.0.0.1:{port}'
                env['G2C_FIXTURE_PORT'] = str(port)
                server = None
                def start():
                    nonlocal server
                    server = subprocess.Popen([sys.executable, '-B', __file__, '--serve-fixture', str(root)],
                        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    def ready():
                        try: return httpx.get(endpoint + '/health', timeout=.5).status_code in (200, 404)
                        except httpx.HTTPError: return False
                    self.wait(ready, 'signed local API did not start')
                def stop():
                    nonlocal server
                    if server is not None:
                        server.kill(); server.wait(timeout=10); server = None
                def read(case):
                    result = httpx.get(endpoint + '/v1/trip-details', params={'trip_id': proposals[case]['trip_id']},
                        headers={'Authorization': 'Bearer ' + tokens[case]}, timeout=5)
                    result.raise_for_status(); return result.json()['trip']
                def act_count():
                    path = root / 'act-requests'
                    return len(path.read_text().splitlines()) if path.exists() else 0
                def open_proposal(case, language):
                    self.launch(tokens[case], proposals[case]['proposal_id'], language, endpoint)
                    self.tap('查看当前草稿' if language == 'zh-Hans' else 'View current draft')
                    self.tap('读取当前草稿' if language == 'zh-Hans' else 'Read current draft')
                    self.wait(lambda: self.has_label(proposals[case]['document']['title']), 'proposal was not displayed')
                try:
                    start()
                    for case, language, reject in [('en', 'en', False), ('zh', 'zh-Hans', False), ('reject', 'en', True)]:
                        print(f'Simulator UI: {case}', flush=True)
                        before = act_count(); open_proposal(case, language)
                        self.tap('拒绝草稿' if reject and language == 'zh-Hans' else 'Reject draft' if reject else '接受' if language == 'zh-Hans' else 'Accept')
                        self.wait(lambda: self.has_label('确认' if language == 'zh-Hans' else 'Confirm'), 'confirmation step missing')
                        assert read(case) is None, 'preparation changed the formal Trip'
                        self.capture(case + '-prepared')
                        self.tap('确认' if language == 'zh-Hans' else 'Confirm')
                        self.wait(lambda: self.has_label('已接受' if language == 'zh-Hans' else 'Rejected' if reject else 'Accepted'), 'decision was not acknowledged')
                        trip = read(case)
                        if reject:
                            assert trip is None, 'reject created a formal Trip'
                        else:
                            assert trip['version'] == 1 and trip['content_utf8_base64'] == proposals[case]['content_utf8_base64']
                        assert act_count() == before + 1, 'decision did not use exactly one POST'
                        self.capture(case + '-result')
                        if not reject:
                            self.tap('行程' if language == 'zh-Hans' else 'Trips')
                            self.tap('刷新行程' if language == 'zh-Hans' else 'Refresh trips')
                            title = proposals[case]['document']['title']
                            def formal_button():
                                return next((n.get('AXLabel') for n in self.nodes(self.ui())
                                    if n.get('type') == 'Button' and title in n.get('AXLabel', '') and n.get('enabled')), None)
                            self.wait(lambda: formal_button() is not None, 'formal trip not listed in App')
                            self.tap(formal_button())
                            self.tap('读取当前详情' if language == 'zh-Hans' else 'Read current detail')
                            self.wait(lambda: self.has_label('当前正式版本 1' if language == 'zh-Hans' else 'Current formal version 1'),
                                      'App did not read the formal Trip version')
                            self.capture(case + '-formal-detail')
                            assert act_count() == before + 1
                        self.results[case] = 'PASS'
                        if case == 'en':
                            print('Simulator UI: same account next proposal after restart', flush=True)
                            self.launch(tokens['en-next'], proposals['en-next']['proposal_id'], 'en', endpoint)
                            self.tap('Check original action')
                            self.wait(lambda: self.has_label('Accepted'), 'old receipt did not reconcile')
                            self.tap('Trips'); self.tap('View current draft'); self.tap('Read current draft')
                            self.wait(lambda: self.has_label(proposals['en-next']['document']['title']), 'next proposal not displayed')
                            next_before = act_count()
                            self.tap('Accept'); self.wait(lambda: self.has_label('Confirm'), 'next confirmation missing')
                            assert read('en-next') is None
                            self.tap('Confirm'); self.wait(lambda: self.has_label('Accepted'), 'next proposal not acknowledged')
                            next_trip = read('en-next')
                            assert next_trip['version'] == 1 and next_trip['content_utf8_base64'] == proposals['en-next']['content_utf8_base64']
                            assert act_count() == next_before + 1 and read('en')['version'] == 1
                            self.capture('same-account-next-proposal')
                            self.results['same_account_next_proposal'] = 'PASS'

                    print('Simulator UI: committed response loss and restart', flush=True)
                    open_proposal('unknown', 'en'); self.tap('Accept')
                    self.wait(lambda: self.has_label('Confirm'), 'unknown fixture preparation failed')
                    (root / 'lose-response').touch(); before = act_count()
                    lost = threading.Event(); fault_errors = []
                    def lose_api():
                        try:
                            self.wait(lambda: (root / 'response-committed').exists(), 'act did not reach committed response boundary')
                            stop()  # API becomes unreachable after the original commit.
                        except Exception as error: fault_errors.append(error)
                        finally: lost.set()
                    watcher = threading.Thread(target=lose_api, daemon=True); watcher.start()
                    self.tap('Confirm')
                    if not lost.wait(25) or fault_errors:
                        raise AssertionError('response loss injection did not complete')
                    watcher.join(timeout=1)
                    self.wait(lambda: self.has_label('Check original action'), 'lost response did not become unknown')
                    self.launch(tokens['unknown'], proposals['unknown']['proposal_id'], 'en', endpoint)
                    self.wait(lambda: self.has_label('Check original action'), 'restart did not restore query-only action')
                    assert not any(n.get('AXLabel') in ('Accept', 'Reject draft', 'Confirm') and n.get('enabled')
                                   for n in self.nodes(self.ui())), 'restart enabled a new write'
                    self.capture('unknown-offline-restart')
                    assert act_count() == before + 1
                    (root / 'lose-response').unlink(); start()
                    self.tap('Check original action')
                    self.wait(lambda: self.has_label('Accepted'), 'original receipt did not reconcile')
                    trip = read('unknown')
                    assert trip['version'] == 1 and trip['content_utf8_base64'] == proposals['unknown']['content_utf8_base64']
                    assert act_count() == before + 1, 'original action was resent'
                    self.capture('unknown-reconciled'); self.results['unknown'] = 'PASS'

                    print('Simulator UI: foreign token withholding', flush=True)
                    foreign = httpx.get(endpoint + '/v1/trip-proposals', params={'proposal_id': proposals['en']['proposal_id']},
                        headers={'Authorization': 'Bearer ' + tokens['foreign']}, timeout=5)
                    assert foreign.status_code == 503 and 'proposal' not in foreign.json()
                    self.launch(tokens['foreign'], proposals['en']['proposal_id'], 'en', endpoint)
                    self.tap('View current draft'); self.tap('Read current draft')
                    self.wait(lambda: self.has_label('Could not load. Retry the read when available.'), 'foreign proposal was not withheld in App')
                    assert not self.has_label(proposals['en']['document']['title'])
                    self.capture('foreign-refused'); self.results['cross_user'] = 'PASS'

                    # Audit the App's own files for accidental token persistence.
                    container = Path(self.sim('get_app_container', self.args.simulator, BUNDLE, 'data').stdout.strip())
                    for file in container.rglob('*'):
                        if file.is_file() and not file.is_symlink():
                            raw = file.read_bytes()
                            assert not any(token.encode() in raw for token in tokens.values()), 'token persisted in App container'
                    for folder in (container / 'Library/Application Support/G2CDevelopmentTrip').glob('*/*'):
                        assert folder.stat().st_mode & 0o777 == 0o700, 'pending directory is not 0700'
                    self.results['token_memory_and_private_storage'] = 'PASS'

                    self.driver.command('terminate')
                    self.sim('install', self.args.simulator, self.release_app)
                    before = act_count()
                    self.launch(tokens['en'], proposals['en']['proposal_id'], 'en', endpoint)
                    self.wait(lambda: self.has_label('This service is not connected yet. No records have been loaded.'), 'Release assembled development host')
                    assert act_count() == before
                    self.capture('release-disconnected'); self.results['release_no_assembly'] = 'PASS'
                except Exception:
                    with contextlib.suppress(Exception): self.capture('fixture-failure')
                    self.results['act_requests_at_failure'] = act_count()
                    with contextlib.suppress(Exception):
                        self.results['formal_versions_at_failure'] = {name: (read(name) or {}).get('version') for name in proposals}
                    raise
                finally:
                    with contextlib.suppress(Exception): self.driver.command('terminate')
                    self.sim('terminate', self.args.simulator, BUNDLE, check=False)
                    stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulator')
    parser.add_argument('--output')
    parser.add_argument('--serve-fixture', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.serve_fixture:
        serve_fixture(args.serve_fixture); return
    if not args.simulator or not args.output:
        parser.error('--simulator and --output are required')
    check = Check(args)
    try:
        check.check()
    except Exception as error:
        check.results['failure'] = check.redact(str(error))
        with contextlib.suppress(Exception): check.capture('failure')
        raise
    finally:
        try:
            if check.driver is not None: check.driver.close()
        except Exception as error:
            check.results['driver_failure'] = check.redact(str(error))
            raise
        finally:
            required = ('configuration_debug_release', 'missing_environment', 'en', 'zh', 'reject', 'unknown', 'cross_user', 'token_memory_and_private_storage', 'release_no_assembly', 'same_account_next_proposal')
            check.results['status'] = 'PASS' if all(check.results.get(k) == 'PASS' for k in required) and 'failure' not in check.results and 'driver_failure' not in check.results else 'FAIL'
            (check.output / 'report.json').write_text(json.dumps(check.results, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(check.results, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
