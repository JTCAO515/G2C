"""Drive the actual Lio App in a simulator with sample replies only."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulator", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--build-dir", required=True, type=Path)
    args = parser.parse_args()
    output, build = args.output.resolve(), args.build_dir.resolve()
    if output.is_relative_to(ROOT) or build.is_relative_to(ROOT):
        parser.error("Keep build and evidence outside the repository")
    output.mkdir(parents=True, exist_ok=False)

    spec = importlib.util.spec_from_file_location("trip_acceptance", ROOT / "scripts/check_ios_trip_confirm.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    builder = object.__new__(module.XCTestDriver)
    builder.directory = output
    builder.write_project(0)
    (output / "G2CControl.swift").write_text((HERE / "LioHomeUITests.swift").read_text())
    project = output / "G2CAcceptance.xcodeproj"
    settings = project / "project.pbxproj"
    app_source = ROOT / "ios/App/CJProbeApp.swift"
    generated_source = output / app_source.name
    app = app_source.read_text()
    preview = "                LioHome(language: shell.language.lio, service: .demo, isDemo: true) { LioLanguagePicker(shell: shell) }"
    if app.count(preview) != 1:
        raise ValueError("Expected a single sample preview")
    scroll_fixture = (
        '                if ProcessInfo.processInfo.arguments.contains("--lio-scroll-acceptance") {\n'
        '                    LioScrollFixture(shell: shell)\n'
        '                } else {\n'
        f'    {preview}\n'
        '                }'
    )
    generated_source.write_text(app.replace(preview, scroll_fixture)
                                .replace("import CJLioUser\n", "@testable import CJLioUser\n")
                                + "\n" + (HERE / "LioScrollFixture.swift").read_text())
    settings.write_text(settings.read_text().replace("space.go2china.foundation.local", "space.go2china.lio.acceptance")
                        .replace(json.dumps(str(app_source)), json.dumps(str(generated_source))))
    result = output / "lio-home.xcresult"
    env = {key: value for key, value in os.environ.items() if not key.startswith(("G2C_DEV_", "SIMCTL_CHILD_"))}
    command = [
        "xcodebuild", "-project", str(project), "-scheme", "G2CControl",
        "-destination", f"platform=iOS Simulator,id={args.simulator}",
        "-derivedDataPath", str(build), "-resultBundlePath", str(result),
        "-onlyUsePackageVersionsFromResolvedFile", "-parallel-testing-enabled", "NO",
        "ARCHS=arm64", "ONLY_ACTIVE_ARCH=YES", "CODE_SIGNING_ALLOWED=YES", "CODE_SIGN_IDENTITY=-",
        "-only-testing:G2CControl/LioHomeUITests", "test",
    ]
    with (output / "lio-home.log").open("w") as log:
        subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
    summary = subprocess.check_output(["xcrun", "xcresulttool", "get", "test-results", "summary", "--path", str(result)])
    (output / "summary.json").write_bytes(summary)
    assert json.loads(summary)["passedTests"] == 3, summary


if __name__ == "__main__":
    main()
