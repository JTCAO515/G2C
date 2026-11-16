"""External native AX controller; no product hooks, credentials, or business HTTP.

The real Beta App must be built/installed and qualified separately. This module
does not grant login, message, release or provider authority.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'backend/strict_json'))
from cj_strict_json import compact, reject_duplicates


def decode(data):
    return json.loads(data, object_pairs_hook=reject_duplicates(ValueError, 'duplicate UI record field'))


def write(path, value):
    temporary = path.with_name(path.name + '.new')
    with temporary.open('xb') as stream:
        stream.write(compact(value, sort_keys=True))
    temporary.chmod(0o600)
    temporary.rename(path)


class NativeUI:
    """One fresh runner and directory. Never restart it or replay a missing ACK."""
    def __init__(self, directory, simulator, bundle, *, build_directory):
        self.directory = Path(directory).resolve()
        self.simulator, self.bundle = simulator, bundle
        self.sequence = 0
        if self.directory.is_relative_to(ROOT) or Path(build_directory).resolve().is_relative_to(ROOT):
            raise ValueError('Keep UI evidence and intermediates outside the repository')
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.commands = self.directory / 'commands'; self.commands.mkdir(mode=0o700)
        spec = importlib.util.spec_from_file_location('trip_acceptance', ROOT / 'scripts/check_ios_trip_confirm.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        generator = object.__new__(module.XCTestDriver)
        generator.directory = self.directory
        generator.write_project(0)
        source = (HERE / 'LioBasicSmokeUI.swift').read_text().replace('__COMMAND_DIRECTORY__', str(self.commands))
        (self.directory / 'G2CControl.swift').write_text(source)
        project = self.directory / 'G2CAcceptance.xcodeproj'
        path = project / 'project.pbxproj'; pbx = path.read_text()
        # The unrelated Debug target is only the existing runner host. It has a
        # separate bundle and is never launched as the ordinary Beta under test.
        pbx = pbx.replace('space.go2china.foundation.local', 'space.go2china.smoke.driver-host')
        strict_ref, strict_product, strict_build = ('B00000000000000000000001', 'B00000000000000000000002', 'B00000000000000000000003')
        pbx = pbx.replace('packageReferences = (000000000000000000000020);',
                          f'packageReferences = (000000000000000000000020, {strict_ref});')
        target = 'A00000000000000000000001'
        marker = f'{target} = {{isa = PBXNativeTarget;'
        if pbx.count(marker) != 1:
            raise ValueError('Existing native test target template changed')
        pbx = pbx.replace(marker, marker + f' packageProductDependencies = ({strict_product});')
        framework = 'A00000000000000000000008'
        marker = f'{framework} = {{isa = PBXFrameworksBuildPhase; buildActionMask = 2147483647; files = ();'
        if pbx.count(marker) != 1:
            raise ValueError('Existing native test framework template changed')
        pbx = pbx.replace(marker, marker.replace('files = ();', f'files = ({strict_build});'))
        entries = f'''
{strict_ref} = {{isa = XCLocalSwiftPackageReference; relativePath = {json.dumps(str(ROOT / 'ios/Modules/CJStrictJSON'))}; }};
{strict_product} = {{isa = XCSwiftPackageProductDependency; package = {strict_ref}; productName = CJStrictJSON; }};
{strict_build} = {{isa = PBXBuildFile; productRef = {strict_product}; }};
'''
        path.write_text(pbx.replace('};\nrootObject', entries + '};\nrootObject'))
        self.log = (self.directory / 'runner.log').open('xb')
        env = {k: v for k, v in os.environ.items() if not k.startswith(('G2C_DEV_', 'SIMCTL_CHILD_'))}
        command = ['xcodebuild', '-project', str(project), '-scheme', 'G2CControl',
                   '-destination', f'platform=iOS Simulator,id={simulator}', '-derivedDataPath', str(build_directory),
                   '-resultBundlePath', str(self.directory / 'runner.xcresult'),
                   '-onlyUsePackageVersionsFromResolvedFile', '-parallel-testing-enabled', 'NO',
                   'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=YES', 'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGN_IDENTITY=-',
                   '-only-testing:G2CControl/LioBasicSmokeUI/testDriveOrdinaryHome', 'test']
        self.process = subprocess.Popen(command, cwd=ROOT, env=env, stdout=self.log, stderr=subprocess.STDOUT)
        self.failed = False
        write(self.directory / 'driver-source.json', {
            'version': 'LIO-native-UI-driver-source.1', 'simulator': simulator, 'target_bundle': bundle,
            'checkout': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
            'controller_sha256': hashlib.sha256((HERE / 'LioBasicSmokeUI.swift').read_bytes()).hexdigest(),
            'scope': 'external native AX controller; not App artifact or Hong Kong qualification'})
        deadline = time.monotonic() + 300
        while not (self.commands / 'ready').exists():
            if self.process.poll() is not None or time.monotonic() >= deadline:
                self.failed = True
                self.close()
                raise RuntimeError('Native UI runner did not start; inspect its private log')
            time.sleep(.2)

    def command(self, kind, *, timeout=90, **fields):
        if self.failed or self.process.poll() is not None:
            raise RuntimeError('Native UI runner unavailable; do not replay an unknown action')
        stem = f'{self.sequence:05d}'
        request = dict(id=uuid.uuid4().hex, kind=kind, bundle=self.bundle, **fields)
        target = self.commands / (stem + '.request.json')
        if target.exists():
            raise RuntimeError('A UI action already has an execution record; do not overwrite or resend')
        write(target, request)
        response = self.commands / (stem + '.response.json')
        deadline = time.monotonic() + timeout
        while not response.exists():
            if self.process.poll() is not None or time.monotonic() >= deadline:
                self.failed = True
                raise RuntimeError('Native UI result UNKNOWN; preserve the original execution record')
            time.sleep(.1)
        result = decode(response.read_bytes())
        self.sequence += 1
        if result['id'] != request['id'] or result['ok'] is not True:
            self.failed = True
            raise RuntimeError('Native UI action failed; preserve its original record')
        return result

    def close(self):
        try:
            if not self.failed and self.process.poll() is None:
                self.command('stop', timeout=15)
                self.process.wait(timeout=30)
        finally:
            if self.process.poll() is None:
                self.process.terminate()
                self.process.wait(timeout=15)
            self.log.close()
