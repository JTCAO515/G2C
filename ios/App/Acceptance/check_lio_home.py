"""Drive the actual Lio App in a simulator with sample replies only."""
import argparse
import base64
import importlib.util
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent



def recorded_trip_fixture():
    path = ROOT / "ios/Modules/CJTripClient/Tests/CJTripClientTests/Fixtures/STRUCTURED-V1.json"
    source = next(row for row in json.loads(path.read_text()) if row["name"] == "sources")
    content = json.loads(base64.b64decode(source["canonical_utf8_base64"]))
    trace = "B35279D6-8B42-466D-A55D-8A16B64BB270"
    envelope = {"version": "TRIP-structured-read.1", "request_id": trace}
    saved = {"trip_id": "trip:lio-map-demo", "version": 1, "content_sha256": source["sha256"]}
    detail = {**envelope, "trip": {**saved, "content": content}}
    listing = {**envelope, "trips": [{**saved, "title": content["title"], "content_version": content["content_version"]}],
               "next_after": None}

    def encoded(value):
        return base64.b64encode(json.dumps(value, separators=(",", ":")).encode()).decode()

    return encoded({"trace": trace, "list": encoded(listing), "detail": encoded(detail)})

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulator", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--build-dir", required=True, type=Path)
    parser.add_argument("--case", action="append", help="Run just this XCTest method. May be repeated.")
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
    tests = (HERE / "LioHomeUITests.swift").read_text()
    (output / "G2CControl.swift").write_text(tests.replace("__LIO_RECORDED_TRIP_FIXTURE__", recorded_trip_fixture()))
    project = output / "G2CAcceptance.xcodeproj"
    settings = project / "project.pbxproj"
    app_source = ROOT / "ios/App/CJProbeApp.swift"
    generated_source = output / app_source.name
    app = app_source.read_text()
    preview = '        if let encoded = ProcessInfo.processInfo.environment["G2C_LIO_PREVIEW_TRIP"] {'
    if app.count(preview) != 1:
        raise ValueError("Expected a single sample preview")
    fixture_routes = (
        '        if ProcessInfo.processInfo.arguments.contains("--lio-scroll-acceptance") {\n'
        '            LioScrollFixture(shell: shell)\n'
        '        } else if ProcessInfo.processInfo.arguments.contains("--lio-journey-acceptance") {\n'
        '            LioJourneyFixture(shell: shell)\n'
        '        } else if ProcessInfo.processInfo.arguments.contains("--lio-timeline-acceptance") {\n'
        '            LioTimelineFixture(shell: shell, exerciseResend: ProcessInfo.processInfo.arguments.contains("--lio-resend-acceptance"))\n'
        '        } else ' + preview.lstrip()
    )
    fixtures = ("LioScrollFixture.swift", "LioTimelineFixture.swift", "LioJourneyFixture.swift", "LioMemoryJourneyFixture.swift")
    generated_source.write_text(app.replace(preview, fixture_routes)
                                .replace("import CJLioUser\n", "@testable import CJLioUser\n")
                                + "\n" + "\n".join((HERE / name).read_text() for name in fixtures))
    settings.write_text(settings.read_text().replace("space.go2china.foundation.local", "space.go2china.lio.acceptance")
                        .replace(json.dumps(str(app_source)), json.dumps(str(generated_source))))
    result = output / "lio-home.xcresult"
    env = {key: value for key, value in os.environ.items() if not key.startswith(("G2C_DEV_", "SIMCTL_CHILD_"))}
    suite = "G2CControl/LioHomeUITests"
    selectors = [f"-only-testing:{suite}/{case}" for case in args.case] if args.case else [f"-only-testing:{suite}"]
    command = [
        "xcodebuild", "-project", str(project), "-scheme", "G2CControl",
        "-destination", f"platform=iOS Simulator,id={args.simulator}",
        "-derivedDataPath", str(build), "-resultBundlePath", str(result),
        "-onlyUsePackageVersionsFromResolvedFile", "-parallel-testing-enabled", "NO",
        "ARCHS=arm64", "ONLY_ACTIVE_ARCH=YES", "CODE_SIGNING_ALLOWED=YES", "CODE_SIGN_IDENTITY=-",
        *selectors, "test",
    ]
    with (output / "lio-home.log").open("w") as log:
        subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600)
    summary = subprocess.check_output(["xcrun", "xcresulttool", "get", "test-results", "summary", "--path", str(result)])
    (output / "summary.json").write_bytes(summary)
    assert json.loads(summary)["passedTests"] == (len(args.case) if args.case else 14), summary


if __name__ == "__main__":
    main()
