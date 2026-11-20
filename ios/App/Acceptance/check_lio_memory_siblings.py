"""Native sibling-memory confirmation and grid refresh; synthetic local data only."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).parent


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
    spec = importlib.util.spec_from_file_location('trip_acceptance', ROOT / 'scripts/check_ios_trip_confirm.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    builder = object.__new__(module.XCTestDriver); builder.directory = output; builder.write_project(0)
    (output / 'G2CControl.swift').write_bytes((HERE / 'LioMemorySiblingUITests.swift').read_bytes())
    entry = ROOT / 'ios/App/CJProbeApp.swift'
    source = entry.read_text().replace('import CJLioUser\n', '@testable import CJLioUser\n')
    marker = '                    lioPreview\n'
    if source.count(marker) != 1: raise ValueError('Existing preview composition changed')
    source = source.replace(marker, '                    LioMemorySiblingFixture(shell: shell)\n')
    fixtures = ('LioJourneyFixture.swift', 'LioMemoryJourneyFixture.swift', 'LioMemorySiblingFixture.swift')
    generated = output / 'CJProbeApp.swift'
    generated.write_text(source + '\n' + '\n'.join((HERE / name).read_text() for name in fixtures))
    project = output / 'G2CAcceptance.xcodeproj'; settings = project / 'project.pbxproj'
    settings.write_text(settings.read_text().replace(str(entry), str(generated))
                        .replace('space.go2china.foundation.local', 'space.go2china.memory-siblings.acceptance'))
    result = output / 'memory-siblings.xcresult'
    suite = 'G2CControl/LioMemorySiblingUITests'
    selectors = [f'-only-testing:{suite}/{case}' for case in args.case] if args.case else [f'-only-testing:{suite}']
    command = ['xcodebuild', '-project', str(project), '-scheme', 'G2CControl', '-destination', 'platform=iOS Simulator,id=' + args.simulator,
               '-derivedDataPath', str(args.build_dir), '-resultBundlePath', str(result), '-onlyUsePackageVersionsFromResolvedFile',
               '-parallel-testing-enabled', 'NO', 'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=YES', 'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGN_IDENTITY=-',
               *selectors, 'test']
    env = {k: v for k, v in os.environ.items() if not k.startswith(('G2C_DEV_', 'SIMCTL_CHILD_'))}
    with (output / 'xcodebuild.log').open('w') as log:
        subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
    summary = subprocess.check_output(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', str(result)])
    (output / 'summary.json').write_bytes(summary)
    value = json.loads(summary)
    assert value['passedTests'] == (len(args.case) if args.case else 2)
    assert value['failedTests'] == 0 and value['skippedTests'] == 0


if __name__ == '__main__': main()
