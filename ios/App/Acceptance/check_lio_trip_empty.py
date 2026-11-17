"""Audit the actual Home -> empty Trips action, with local demo content only."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulator', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--build-dir', type=Path, required=True)
    parser.add_argument('--case', action='append')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(ROOT) or args.build_dir.resolve().is_relative_to(ROOT):
        parser.error('Keep evidence and products outside the repository')
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('project_builder', ROOT / 'scripts/check_ios_trip_confirm.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    builder = object.__new__(module.XCTestDriver)
    builder.directory = output
    builder.write_project(0)
    test_file = HERE / 'LioTripEmptyUITests.swift'
    tests = test_file.read_bytes()
    (output / 'G2CControl.swift').write_bytes(tests)
    assert (output / 'G2CControl.swift').read_bytes() == tests
    project = output / 'G2CAcceptance.xcodeproj'
    settings = project / 'project.pbxproj'
    settings.write_text(settings.read_text().replace('space.go2china.foundation.local', 'space.go2china.trip.empty.acceptance'))
    sources = [test_file, ROOT / 'ios/App/CJProbeApp.swift', ROOT / 'ios/Modules/CJShell/Sources/CJLioUser/LioHome.swift',
               ROOT / 'ios/Modules/CJShell/Sources/CJLioUser/LioTripsView.swift']
    (output / 'source.json').write_text(json.dumps({
        'head': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
        'dirty': bool(subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'], text=True)),
        'simulator': args.simulator,
        'hashes': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
        'generated_test': hashlib.sha256(tests).hexdigest(),
        'scope': 'Actual ordinary preview Home and Trips; no account, transport, provider or map fixture'
    }, indent=2))
    suite = 'G2CControl/LioTripEmptyUITests'
    selectors = [f'-only-testing:{suite}/{case}' for case in args.case] if args.case else [f'-only-testing:{suite}']
    command = ['xcodebuild', '-project', str(project), '-scheme', 'G2CControl', '-destination', f'platform=iOS Simulator,id={args.simulator}',
               '-derivedDataPath', str(args.build_dir), '-resultBundlePath', str(output / 'empty-trip.xcresult'),
               '-onlyUsePackageVersionsFromResolvedFile', '-parallel-testing-enabled', 'NO', 'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=YES',
               'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGN_IDENTITY=-', *selectors, 'test']
    (output / 'command.json').write_text(json.dumps(command, indent=2))
    env = {key: value for key, value in os.environ.items() if not key.startswith(('G2C_DEV_', 'SIMCTL_CHILD_'))}
    with (output / 'empty-trip.log').open('w') as log:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=900)
    summary = json.loads(subprocess.check_output(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', str(output / 'empty-trip.xcresult')]))
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    expected = len(args.case) if args.case else 4
    if summary['passedTests'] + summary['failedTests'] != expected or summary['skippedTests'] != 0:
        raise RuntimeError('Native method count mismatch; do not treat as PASS')
    print(json.dumps({'native_exit': result.returncode, 'passed': summary['passedTests'], 'failed': summary['failedTests'], 'skipped': summary['skippedTests']}))
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
