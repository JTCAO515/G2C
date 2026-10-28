"""Issue #157: native iOS 17.5 UI checks, with an external-only fixture project.

The ordinary App and actual CJShell run in an isolated test bundle. The second
host supplies labelled synthetic readonly memory responses; no Auth or business
write capability is enabled. Neither fixture Swift file belongs to the App target.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BUNDLE = "space.go2china.shell.acceptance"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--simulator", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.is_relative_to(ROOT):
        raise ValueError("Evidence output must be outside the repository")
    output.mkdir(parents=True, exist_ok=True)
    if (output / "report.json").exists():
        raise ValueError("Use a new output directory; preserve prior evidence")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SIMCTL_CHILD_", "G2C_DEV_"))}
    env["DEVELOPER_DIR"] = "/Applications/Xcode.app/Contents/Developer"
    devices = json.loads(subprocess.check_output(["xcrun", "simctl", "list", "devices", "available", "-j"], env=env))
    assert any("iOS-17-5" in runtime and d["udid"] == args.simulator
               for runtime, rows in devices["devices"].items() for d in rows), "iOS 17.5 simulator required"
    report = {"status": "RUNNING", "cases": {}, "scope": "ordinary App + labelled synthetic readonly Shell fixture; no real service"}
    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, indent=2))
    requests = {}; lock = threading.Lock()

    class Fixture(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def reply(self, status, value):
            data = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Request-ID", "00000000-0000-4000-8000-000000000157")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers(); self.wfile.write(data)

        def do_GET(self):
            url = urlsplit(self.path)
            if self.command == "GET" and url.path == "/audit":
                run = parse_qs(url.query)["run"][0]
                with lock: observed = requests.get(run, []) + requests.get("unattributed", [])
                self.reply(200, observed); return
            match = re.fullmatch(r"Bearer SYNTHETIC-(empty|failed)-([A-Fa-f0-9-]+)", self.headers.get("Authorization", ""))
            run = match[2] if match else "unattributed"
            with lock: requests.setdefault(run, []).append(self.command + " " + url.path)
            if self.command == "GET" and match and match[1] == "empty" and url.path == "/v1/memory-groups":
                self.reply(200, {"request_id": "00000000-0000-4000-8000-000000000157", "groups": []})
            else:
                self.reply(503, {"request_id": "00000000-0000-4000-8000-000000000157", "error": {
                    "code": "INTERNAL_ERROR", "category": "internal", "message_en": "Synthetic failure",
                    "message_zh": "Synthetic failure", "outcome": "failed", "recovery": "do_not_retry"}})

        do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_GET  # Audited; only GET can succeed.

    server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    spec = importlib.util.spec_from_file_location("trip_acceptance", ROOT / "scripts/check_ios_trip_confirm.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    try:
        for variant, tests in {
            "ordinary": ["testOrdinaryAppTabsLanguageAndDraft"],
            "fixture": ["testMemoryStatesKeepSettingsReachable", "testLanguagePreservesReferencesAndDoesNotRepeatRequests", "testPluginsAreInertInBothLanguages"]
        }.items():
            # Reuse only the existing external Xcode project generator, not its Trip
            # API/PG setup or polling driver. Our XCTest source drives UI directly.
            builder = object.__new__(module.XCTestDriver)
            builder.directory = output / variant; builder.directory.mkdir()
            builder.write_project(0)
            source = (HERE / "ShellStructureUITests.swift").read_text()
            (builder.directory / "G2CControl.swift").write_text(source.replace("__FIXTURE_URL__", f"http://127.0.0.1:{server.server_port}"))
            project = builder.directory / "G2CAcceptance.xcodeproj"
            pbx = project / "project.pbxproj"
            text = pbx.read_text().replace("space.go2china.foundation.local", BUNDLE).replace(
                "space.go2china.foundation.control", BUNDLE + ".control")
            text = re.sub(r'"CODE_SIGN_ENTITLEMENTS\[sdk=iphonesimulator\*\]"\s*=\s*[^;]+;', "", text)
            if variant == "fixture":
                text = text.replace(json.dumps(str(ROOT / "ios/App/CJProbeApp.swift")), json.dumps(str(HERE / "ShellFixtureApp.swift")))
            pbx.write_text(text)
            result = output / (variant + ".xcresult")
            command = ["xcodebuild", "-project", str(project), "-scheme", "G2CControl", "-destination",
                       "platform=iOS Simulator,id=" + args.simulator, "-derivedDataPath", str(output / "dd"),
                       "-resultBundlePath", str(result), "-scmProvider", "system", "-skipPackageUpdates",
                       "-onlyUsePackageVersionsFromResolvedFile", "-parallel-testing-enabled", "NO",
                       "ARCHS=arm64", "ONLY_ACTIVE_ARCH=YES", "CODE_SIGNING_ALLOWED=YES", "CODE_SIGN_IDENTITY=-"]
            command += ["-only-testing:G2CControl/ShellStructureUITests/" + test for test in tests]
            with (output / (variant + ".log")).open("w") as log:
                subprocess.run(command + ["test"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=900)
            summary = json.loads(subprocess.check_output(["xcrun", "xcresulttool", "get", "test-results", "summary", "--path", str(result)], env=env))
            (output / (variant + "-summary.json")).write_text(json.dumps(summary, indent=2))
            assert summary["passedTests"] == len(tests) and summary["failedTests"] == 0 and summary["skippedTests"] == 0, summary
            report["cases"][variant] = {"status": "PASS", "tests": tests}
        report["status"] = "PASS"
    except BaseException as error:
        report["status"] = "FAIL"; report["error"] = type(error).__name__
        raise
    finally:
        report_path.write_text(json.dumps(report, indent=2))
        server.shutdown(); server.server_close()
        subprocess.run(["xcrun", "simctl", "terminate", args.simulator, BUNDLE], env=env, capture_output=True)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
