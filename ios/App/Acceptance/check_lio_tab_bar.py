"""Run actual Lio native tab configuration and Home/history accessibility, without services."""
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
    parser.add_argument('--unit', action='store_true')
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
    test_path = HERE / ('LioTabBarUnitTests.swift' if args.unit else 'LioTabBarUITests.swift')
    tests = test_path.read_bytes()
    (output / 'G2CControl.swift').write_bytes(tests)
    assert (output / 'G2CControl.swift').read_bytes() == tests
    app_source = ROOT / 'ios/App/CJProbeApp.swift'
    if args.unit:
        generated = '''import SwiftUI
import CJLioUser
@main struct TabColorUnitHost: App {
    var body: some Scene { WindowGroup {
        if ProcessInfo.processInfo.arguments.contains("--unit-show-home") {
            LioHome(language: .english, service: .unavailable, isDemo: true) { EmptyView() }
        } else { Color.clear }
    } }
}
'''
    else:
        generated = app_source.read_text().replace('import CJLioUser\n', '@testable import CJLioUser\n')
        marker = '                    lioPreview\n'
        if generated.count(marker) != 1:
            raise ValueError('The existing Lio preview composition changed')
        generated = generated.replace(marker, '                    LioTabAcceptanceFixture(shell: shell)\n')
        generated += '\n' + '\n'.join((HERE / name).read_text() for name in (
            'LioJourneyFixture.swift', 'LioMemoryJourneyFixture.swift', 'LioChatHistoryFixture.swift')) + '''
@MainActor private struct LioTabAcceptanceFixture: View {
    let shell: ShellState
    var body: some View {
        if ProcessInfo.processInfo.arguments.contains("--lio-tab-history-acceptance") {
            LioChatHistoryFixture(shell: shell)
        } else if ProcessInfo.processInfo.arguments.contains("--lio-tab-order-acceptance") {
            LioHome(language: shell.language.lio, service: .demo, isDemo: true,
                    savedMemory: AnyView(Text(shell.language.text("Sample memory", "示例记忆"))),
                    showsTools: true) { LioMenuSettings(shell: shell) }
        } else {
            LioHome(language: shell.language.lio, service: .demo, isDemo: true) { LioMenuSettings(shell: shell) }
        }
    }
}
'''
    (output / 'CJProbeApp.swift').write_text(generated)
    project = output / 'G2CAcceptance.xcodeproj'
    pbx = project / 'project.pbxproj'
    contents = pbx.read_text().replace(str(app_source), str(output / 'CJProbeApp.swift'))
    contents = contents.replace('space.go2china.foundation.local', 'space.go2china.tab.acceptance')
    if args.unit:
        contents = contents.replace('com.apple.product-type.bundle.ui-testing', 'com.apple.product-type.bundle.unit-test')
        contents = contents.replace('TEST_TARGET_NAME = CJProbeApp;', 'TEST_HOST = "$(BUILT_PRODUCTS_DIR)/CJProbeApp.app/CJProbeApp"; BUNDLE_LOADER = "$(TEST_HOST)";')
    pbx.write_text(contents)
    sources = [ROOT / 'ios/Modules/CJShell/Sources/CJLioUser/LioHome.swift', test_path]
    if not args.unit:
        sources.extend(HERE / name for name in ('LioJourneyFixture.swift', 'LioMemoryJourneyFixture.swift', 'LioChatHistoryFixture.swift'))
    bridge = ROOT / 'ios/Modules/CJShell/Sources/CJLioUser/LioTabBarAppearance.swift'
    if bridge.exists():
        sources.append(bridge)
    (output / 'source.json').write_text(json.dumps({
        'head': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
        'dirty': bool(subprocess.check_output(['git', '-C', str(ROOT), 'status', '--porcelain'], text=True)),
        'simulator': args.simulator, 'unit': args.unit,
        'hashes': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
        'generated': {name: hashlib.sha256((output / name).read_bytes()).hexdigest() for name in ('G2CControl.swift', 'CJProbeApp.swift')}
    }, indent=2))
    suite = 'LioTabBarColorUnitTests' if args.unit else 'LioTabBarUITests'
    selectors = [f'-only-testing:G2CControl/{suite}/{case}' for case in args.case] if args.case else [f'-only-testing:G2CControl/{suite}']
    command = ['xcodebuild', '-project', str(project), '-scheme', 'G2CControl', '-destination', f'platform=iOS Simulator,id={args.simulator}',
               '-derivedDataPath', str(args.build_dir), '-resultBundlePath', str(output / 'tabs.xcresult'),
               '-onlyUsePackageVersionsFromResolvedFile', '-parallel-testing-enabled', 'NO', 'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=YES',
               'CODE_SIGNING_ALLOWED=YES', 'CODE_SIGN_IDENTITY=-', *selectors, 'test']
    (output / 'command.json').write_text(json.dumps(command, indent=2))
    env = {key: value for key, value in os.environ.items() if not key.startswith(('G2C_DEV_', 'SIMCTL_CHILD_'))}
    with (output / 'tabs.log').open('w') as log:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=900)
    summary = json.loads(subprocess.check_output(['xcrun', 'xcresulttool', 'get', 'test-results', 'summary', '--path', str(output / 'tabs.xcresult')]))
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    expected = len(args.case) if args.case else (3 if args.unit else 5)
    if summary['passedTests'] + summary['failedTests'] != expected or summary['skippedTests'] != 0:
        raise RuntimeError('Actual method count does not match the requested native suite; do not treat as PASS')
    print(json.dumps({'native_exit': result.returncode, 'passed': summary['passedTests'], 'failed': summary['failedTests'], 'skipped': summary['skippedTests']}))
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
