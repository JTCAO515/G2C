"""Shared native execution for the authorized M4 device matrix.

Owning suites retain their API/database assertions. Raw native bundles remain
private; only gated, redacted text is exported. No SDK or Keychain discovery.
"""
import hmac
import json
from pathlib import Path
import plistlib
import subprocess
import tempfile
import time

from m4_artifacts import export_native_logs, redact
from m4_device import copy_accounts, discard_staged_accounts, scan_app_container


def authenticated_control(base, token, stage):
    class AuthenticatedControl(base):
        def do_GET(self):
            supplied = self.headers.get('X-G2C-M4-Control', '')
            if not hmac.compare_digest(supplied.encode(), token.encode()):
                self.send_response(403); self.end_headers(); self.wfile.write(b'forbidden')
                return
            if self.path == '/m4-stage-accounts':
                try:
                    stage()
                except Exception:
                    self.send_error(500, 'device input staging failed')
                    return
                self.send_response(200); self.end_headers(); self.wfile.write(b'{"staged":true}')
                return
            super().do_GET()
    return AuthenticatedControl


class DeviceNative:
    def __init__(self, device, bundle, project, configuration_file, build, root, output,
                 tokens, control_token, report):
        self.device, self.bundle = device, bundle
        self.project, self.configuration_file = Path(project), Path(configuration_file)
        self.build, self.root, self.output = Path(build), Path(root), Path(output)
        self.tokens = tokens
        self.secrets = [*tokens.values(), control_token]
        self.report = report
        self.private = Path(tempfile.mkdtemp(prefix='g2c-m4-private-native-'))
        self.private.chmod(0o700)
        self.staging_attempted = False
        self.configuration = None

    def command(self, configuration, tests, destination, result, action):
        return ['xcodebuild', '-project', str(self.project), '-scheme', 'G2CControl',
                '-configuration', configuration, '-xcconfig', str(self.configuration_file),
                '-allowProvisioningUpdates', '-allowProvisioningDeviceRegistration',
                '-destination', destination, '-derivedDataPath', str(self.build),
                '-resultBundlePath', str(result), '-scmProvider', 'system',
                '-skipPackageUpdates', '-onlyUsePackageVersionsFromResolvedFile',
                '-parallel-testing-enabled', 'NO', '-collect-test-diagnostics', 'never',
                'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=YES',
                *['-only-testing:G2CControl/' + case for case in tests], action]

    def build_for_testing(self, configuration, tests, env):
        result = self.private / (configuration + '-build.xcresult')
        run = subprocess.run(self.command(configuration, tests, 'generic/platform=iOS',
                             result, 'build-for-testing'), cwd=self.root, env=env,
                             capture_output=True, text=True, timeout=1800)
        export = self.output / (configuration + '-build-exports'); export.mkdir(mode=0o700)
        gate = export_native_logs(result, export, self.secrets, run.stdout + run.stderr,
                                  kinds=('build',))
        self.report.setdefault('device_builds', {})[configuration] = dict(
            exit_code=run.returncode, artifacts=gate, raw_bundle_shareable=False)
        if not gate['status'].startswith('PASS'):
            raise RuntimeError('Device build log failed credential/export gate')
        run.check_returncode()
        if configuration == 'Release':
            app = self.build / 'Build/Products/Release-iphoneos/CJProbeApp.app'
            info = plistlib.loads((app / 'Info.plist').read_bytes())
            if info.get('NSAppTransportSecurity') or (app / 'G2CM4LocalServer.cer').exists():
                self.report['device_builds'][configuration]['product_local_network_boundary'] = 'FAIL'
                raise RuntimeError('Release product contains local network test configuration')
            self.report['device_builds'][configuration]['product_local_network_boundary'] = 'PASS'

    def install(self, configuration):
        app = self.build / 'Build/Products' / (configuration + '-iphoneos') / 'CJProbeApp.app'
        result = subprocess.run(['xcrun', 'devicectl', 'device', 'install', 'app',
                                '--device', self.device, str(app), '--timeout', '60'],
                                capture_output=True)
        if result.returncode:
            raise RuntimeError('Approved device App install failed')

    def stage(self):
        # Set intent first: a failed copy can still leave an input on device.
        self.staging_attempted = True
        copy_accounts(self.device, self.bundle, self.private, self.tokens)

    def run(self, configuration, tests, env):
        self.configuration = configuration
        deadline = time.monotonic() + 1200
        while True:
            state = json.loads(subprocess.check_output(['xcrun', 'devicectl', 'device',
                'info', 'lockState', '--device', self.device, '--json-output', '-',
                '--quiet', '--timeout', '20'], text=True))['result']
            if not state['passcodeRequired']:
                break
            self.report['status'] = 'WAITING_DEVICE_UNLOCK'
            (self.output / 'report.json').write_text(json.dumps(self.report, indent=2))
            if time.monotonic() > deadline:
                raise TimeoutError('Approved device remained locked after build')
            time.sleep(5)
        self.install(configuration)
        self.report['status'] = 'RUNNING'
        result = self.private / (configuration + '-test.xcresult')
        run = subprocess.run(self.command(configuration, tests, 'platform=iOS,id=' + self.device,
                             result, 'test-without-building'), cwd=self.root, env=env,
                             capture_output=True, text=True, timeout=1800)
        export = self.output / (configuration + '-test-exports'); export.mkdir(mode=0o700)
        gate = export_native_logs(result, export, self.secrets, run.stdout + run.stderr,
                                  kinds=('action',))
        self.report.setdefault('device_tests', {})[configuration] = dict(
            exit_code=run.returncode, artifacts=gate, raw_bundle_shareable=False)
        if not gate['status'].startswith('PASS'):
            raise RuntimeError('Device test log failed credential/export gate')
        run.check_returncode()
        text = subprocess.check_output(['xcrun', 'xcresulttool', 'get', 'test-results',
                                       'summary', '--path', str(result)], text=True)
        safe, hits = redact(text, self.secrets)
        (self.output / (configuration + '-summary.json')).write_text(safe)
        if hits:
            raise RuntimeError('Native summary contained credential; raw bundle quarantined')
        summary = json.loads(safe)
        assert summary['passedTests'] == len(tests)
        assert summary['failedTests'] == summary['skippedTests'] == 0
        return summary

    def scan(self, configuration):
        # During Release the unconfigured product must ignore the staged file.
        # Remove that exact operator input before scanning other App data.
        self.cleanup_input()
        scan_app_container(self.device, self.bundle,
                           self.output / (configuration + '-app-data'), self.tokens.values())

    def cleanup_input(self):
        if not self.staging_attempted:
            return
        try:
            if self.configuration == 'Release':
                # Same run's signed Debug package exposes only the existing
                # exact one-use-file discard action. No business data is erased.
                self.install('Debug')
                self.configuration = 'Debug'
            discard_staged_accounts(self.device, self.bundle)
        except Exception:
            self.report['staged_credential_cleanup'] = 'FAIL: device cleanup pending'
            raise
        self.report['staged_credential_cleanup'] = 'PASS: exact one-use input absent'
        self.staging_attempted = False
