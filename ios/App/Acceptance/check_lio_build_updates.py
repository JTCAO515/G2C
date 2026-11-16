"""Run the actual local App's shared consent/update page; no external services."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'backend/strict_json'))
from cj_strict_json import reject_duplicates


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--simulator', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--build-dir', type=Path, required=True)
    parser.add_argument('--case', action='append')
    parser.add_argument('--section-language', choices=('zh', 'en'))
    parser.add_argument('--section-appearance', choices=('light', 'dark'))
    parser.add_argument('--section-period', choices=('current', 'previous'))
    parser.add_argument('--section', choices=('changes', 'comparison', 'testing', 'known', 'service'))
    args = parser.parse_args()
    output, build = args.output.resolve(), args.build_dir.resolve()
    if output.is_relative_to(ROOT) or build.is_relative_to(ROOT):
        parser.error('Keep evidence and products outside the repository')
    output.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('trip_acceptance', ROOT / 'scripts/check_ios_trip_confirm.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    driver = object.__new__(module.XCTestDriver); driver.directory = output; driver.write_project(0)
    book = json.loads((ROOT/'ios/Modules/CJShell/Sources/CJLioUser/Resources/LioBuildUpdates.v1.json').read_text(), object_pairs_hook=reject_duplicates(ValueError, 'duplicate build update field'))
    current = str(book['currentBuild'])
    previous = str(book['releases'][0]['previousBuild'])
    older = str(book['releases'][1]['previousBuild'])
    tests = (HERE/'LioBuildUpdatesUITests.swift').read_text().replace('__UPDATES_CURRENT_BUILD__', current).replace('__UPDATES_PREVIOUS_BUILD__', previous).replace('__UPDATES_OLDER_BUILD__', older)
    parameters = [args.section_language, args.section_appearance, args.section_period, args.section]
    if any(value is not None for value in parameters):
        if not all(value is not None for value in parameters):
            parser.error('All four direct-section parameters are required')
        pairs = dict(zip(['LIO_UPDATES_TEST_LANGUAGE', 'LIO_UPDATES_TEST_APPEARANCE', 'LIO_UPDATES_TEST_PERIOD', 'LIO_UPDATES_TEST_SECTION'], parameters))
        literal = '[' + ', '.join(json.dumps(key) + ': ' + json.dumps(value) for key, value in pairs.items()) + ']'
        tests = tests.replace('let env = ProcessInfo.processInfo.environment', 'let env: [String: String] = ' + literal)
        (output/'section-parameters.json').write_text(json.dumps(pairs, indent=2)+'\n')
    (output/'G2CControl.swift').write_text(tests)
    original_info = ROOT/'ios/App/Info.plist'
    info = original_info.read_text()
    marker = '<key>CFBundleVersion</key><string>1</string>'
    assert info.count(marker) == 1
    (output/'Info.plist').write_text(info.replace(marker, f'<key>CFBundleVersion</key><string>{current}</string>'))
    project = output/'G2CAcceptance.xcodeproj'
    settings = project/'project.pbxproj'
    app_source = ROOT/'ios/App/CJProbeApp.swift'
    generated_app = output/'CJProbeApp.swift'
    app = app_source.read_text()
    marker = 'LioOnboardingPreview(shell: shell)'
    assert app.count(marker) == 1
    generated_app.write_text(app.replace(marker, 'if ProcessInfo.processInfo.arguments.contains("--lio-invitation-traits-acceptance") { LioInvitationInputFixture { LioOnboardingPreview(shell: shell) } } else { LioOnboardingPreview(shell: shell) }')
                             + '\n' + (HERE/'LioInvitationInputFixture.swift').read_text())
    settings.write_text(settings.read_text().replace('space.go2china.foundation.local', 'space.go2china.updates.acceptance')
                        .replace(str(original_info), str(output/'Info.plist'))
                        .replace(str(app_source), str(generated_app)))
    result = output/'updates.xcresult'
    suite = 'G2CControl/LioBuildUpdatesUITests'
    selectors = [f'-only-testing:{suite}/{case}' for case in args.case] if args.case else [f'-only-testing:{suite}']
    command = ['xcodebuild','-project',str(project),'-scheme','G2CControl','-destination',f'platform=iOS Simulator,id={args.simulator}',
               '-derivedDataPath',str(build),'-resultBundlePath',str(result),'-onlyUsePackageVersionsFromResolvedFile','-parallel-testing-enabled','NO',
               'ARCHS=arm64','ONLY_ACTIVE_ARCH=YES','CODE_SIGNING_ALLOWED=YES','CODE_SIGN_IDENTITY=-',f'CURRENT_PROJECT_VERSION={current}',*selectors,'test']
    (output/'command.json').write_text(json.dumps(command, indent=2)+'\n')
    env = {k:v for k,v in os.environ.items() if not k.startswith(('G2C_DEV_','SIMCTL_CHILD_'))}
    expected = len(args.case) if args.case else 11
    with (output/'updates.log').open('w') as log:
        subprocess.run(command,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900 * expected)
    summary = subprocess.check_output(['xcrun','xcresulttool','get','test-results','summary','--path',str(result)])
    (output/'summary.json').write_bytes(summary)
    parsed = json.loads(summary)
    assert parsed['passedTests'] == expected and parsed['failedTests'] == 0 and parsed['skippedTests'] == 0,summary


if __name__ == '__main__':
    main()
