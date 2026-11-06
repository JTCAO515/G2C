"""Issue #157: native iOS 17.5 UI checks, with an external-only fixture project.

The ordinary App and actual CJShell run in an isolated test bundle. The second
host supplies labelled synthetic readonly memory responses; no Auth or business
write capability is enabled. Neither fixture Swift file belongs to the App target.
"""
import argparse
import importlib.util
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BUNDLE = "space.go2china.shell.acceptance"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=["structure", "accessibility", "account-deletion"], default="structure")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--simulator"); target.add_argument("--device")
    parser.add_argument("--local-tls", type=Path); parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, help="Reusable external build cache; evidence remains separate")
    args = parser.parse_args()
    tls = None
    if args.device:
        if not args.local_tls: parser.error("--device requires the approved --local-tls profile")
        from m4_device import LocalTLS, configure_project, private_workspace
        from m4_native import DeviceNative
        tls = LocalTLS.load(args.local_tls)
        if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT): raise ValueError("commit device candidate first")
    elif args.local_tls or args.prepare_only: parser.error("Device options require --device")
    os.umask(0o077)
    output = args.output.resolve()
    if output.is_relative_to(ROOT):
        raise ValueError("Evidence output must be outside the repository")
    build_directory = (args.build_dir or output / "dd").resolve()
    if tls: device_project_root, build_directory = private_workspace(output, args.build_dir)
    if build_directory.is_relative_to(ROOT):
        raise ValueError("Build cache must be outside the repository")
    output.mkdir(parents=True, exist_ok=True)
    if (output / "report.json").exists():
        raise ValueError("Use a new output directory; preserve prior evidence")
    env = {k: v for k, v in os.environ.items() if not k.startswith(("SIMCTL_CHILD_", "G2C_DEV_"))}
    env["OS_ACTIVITY_MODE"] = "disable"
    env["DEVELOPER_DIR"] = "/Applications/Xcode.app/Contents/Developer"
    if not tls:
        devices = json.loads(subprocess.check_output(["xcrun", "simctl", "list", "devices", "available", "-j"], env=env))
        assert any("iOS-17-5" in runtime and d["udid"] == args.simulator
                   for runtime, rows in devices["devices"].items() for d in rows), "iOS 17.5 simulator required"
    report = {"status": "RUNNING", "suite": args.suite, "cases": {}, "scope": "ordinary App + labelled synthetic readonly Shell fixture; no real service"}
    native = None; control_token = secrets.token_urlsafe(32) if tls else None
    if tls:
        report.update(head=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            layer="signed approved iPhone/ordinary App + labelled synthetic readonly fixture", raw_native_bundle_shareable=False,
            build_inputs_shareable=False, device_font_scope="system default font; no size override",
            unrun=["real signed business flow (separate suites)"])
        sources = [*list((ROOT / "ios/App").glob("*.swift")), *list((ROOT / "ios/Modules").glob("*/Sources/**/*.swift")),
                   Path(__file__), *[HERE / name for name in ("ShellFixtureApp.swift", "ShellStructureUITests.swift", "ShellAccessibilityUITests.swift", "AccountDeletionUITests.swift", "m4_device.py", "m4_native.py", "m4_artifacts.py", "M4DeviceControl.swift", "M4DeviceTestSession.swift")]]
        report["source_hashes"] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, indent=2))
    requests = {}; releases = {}; lock = threading.Lock()

    class Fixture(BaseHTTPRequestHandler):
        def log_message(self, *args): pass

        def reply(self, status, value):
            data = json.dumps(value).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("X-Request-ID", "00000000-0000-4000-8000-000000000157")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try: self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError): pass  # App terminated a held readonly request.

        def do_GET(self):
            url = urlsplit(self.path)
            if tls and url.path in {"/audit", "/release"}:
                if not hmac.compare_digest(self.headers.get("X-G2C-M4-Control", "").encode(), control_token.encode()):
                    self.send_response(403); self.end_headers(); self.wfile.write(b"forbidden"); return
            if self.command == "GET" and url.path == "/audit":
                run = parse_qs(url.query)["run"][0]
                with lock: observed = requests.get(run, []) + requests.get("unattributed", [])
                self.reply(200, observed); return
            if self.command == "GET" and url.path == "/release":
                run = parse_qs(url.query)["run"][0]
                with lock: releases.setdefault(run, threading.Event()).set()
                self.reply(200, []); return
            match = re.fullmatch(r"Bearer SYNTHETIC-(empty|failed|loading)-([A-Fa-f0-9-]+)", self.headers.get("Authorization", ""))
            run = match[2] if match else "unattributed"
            with lock: requests.setdefault(run, []).append(self.command + " " + url.path)
            if match and match[1] == "loading":
                with lock: released = releases.setdefault(run, threading.Event())
                released.wait(timeout=20)
            if self.command == "GET" and match and match[1] in {"empty", "loading"} and url.path in {"/v1/memory-groups", "/v1/trips"}:
                value = {"request_id": "00000000-0000-4000-8000-000000000157"}
                value.update({"groups": []} if url.path == "/v1/memory-groups" else {"trips": [], "next_after": None})
                self.reply(200, value)
            else:
                self.reply(503, {"request_id": "00000000-0000-4000-8000-000000000157", "error": {
                    "code": "INTERNAL_ERROR", "category": "internal", "message_en": "Synthetic failure",
                    "message_zh": "Synthetic failure", "outcome": "failed", "recovery": "do_not_retry"}})

        do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_GET  # Audited; only GET can succeed.

    server = ThreadingHTTPServer((tls.host if tls else "127.0.0.1", 0), Fixture)
    if tls: tls.secure_http_server(server)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    spec = importlib.util.spec_from_file_location("trip_acceptance", ROOT / "scripts/check_ios_trip_confirm.py")
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    try:
        test_class = "ShellStructureUITests" if args.suite == "structure" else "ShellAccessibilityUITests"
        variants = {
            "ordinary": ["testOrdinaryAppTabsLanguageAndDraft", "testOrdinaryHelpPrivacySupportInBothLanguages"],
            "fixture": ["testMemoryStatesKeepSettingsReachable", "testLanguagePreservesReferencesAndDoesNotRepeatRequests", "testPluginsAreInertInBothLanguages"]
        } if args.suite == "structure" else {"fixture": ["testMaximumTextLayout", "testAssistantStateSamplesInBothLanguages", "testTripAndMemoryReadStatesInBothLanguages", "testLongTextKeyboardAndUnavailableControls"], "ordinary": ["testOrdinaryAppAccessibilityAudits"]}
        if args.suite == "account-deletion":
            test_class = "AccountDeletionUITests"
            variants = {"ordinary": ["testOrdinaryEntryAndAccountInBothLanguages"],
                        "fixture": ["testEmptyAndFailedMemoryEntry", "testMaximumTextAndFullAccessibilityAudit"]}
        for variant, tests in variants.items():
            # Reuse only the existing external Xcode project generator, not its Trip
            # API/PG setup or polling driver. Our XCTest source drives UI directly.
            builder = object.__new__(module.XCTestDriver)
            builder.directory = (device_project_root if tls else output) / variant; builder.directory.mkdir()
            builder.write_project(0)
            source = (HERE / (test_class + ".swift")).read_text()
            control_url = ("https://" + tls.host if tls else "http://127.0.0.1") + ":" + str(server.server_port)
            (builder.directory / "G2CControl.swift").write_text(source.replace("__FIXTURE_URL__", control_url))
            project = builder.directory / "G2CAcceptance.xcodeproj"
            pbx = project / "project.pbxproj"
            text = pbx.read_text().replace("space.go2china.foundation.local", BUNDLE).replace(
                "space.go2china.foundation.control", BUNDLE + ".control")
            text = re.sub(r'"CODE_SIGN_ENTITLEMENTS\[sdk=iphonesimulator\*\]"\s*=\s*[^;]+;', "", text)
            if variant == "fixture":
                text = text.replace(json.dumps(str(ROOT / "ios/App/CJProbeApp.swift")), json.dumps(str(HERE / "ShellFixtureApp.swift")))
            pbx.write_text(text)
            if tls:
                _, configuration_file, _ = configure_project(project, tls, control_url, control_token, bundle=BUNDLE)
                detail = dict(status="RUNNING"); report.setdefault("device_native", {})[variant] = detail
                variant_output = output / (variant + "-device"); variant_output.mkdir(mode=0o700)
                native = DeviceNative(args.device, BUNDLE, project, configuration_file, build_directory, ROOT,
                    variant_output, {}, control_token, detail, evidence_root=output)
                selected = [test_class + "/" + test for test in tests]
                native.build_for_testing("Debug", selected, env)
                if args.prepare_only:
                    detail["status"] = "PREPARED_EXECUTION_UNRUN"; report["cases"][variant] = dict(status="UNRUN", tests=tests); continue
                native.run("Debug", selected, env)
                native.scan("Debug")
                detail["status"] = "PASS"; report["cases"][variant] = dict(status="PASS", tests=tests); continue
            result = output / (variant + ".xcresult")
            command = ["xcodebuild", "-project", str(project), "-scheme", "G2CControl", "-destination",
                       "platform=iOS Simulator,id=" + args.simulator, "-derivedDataPath", str(build_directory),
                       "-resultBundlePath", str(result), "-scmProvider", "system", "-skipPackageUpdates",
                       "-onlyUsePackageVersionsFromResolvedFile", "-parallel-testing-enabled", "NO",
                       "-collect-test-diagnostics", "never",
                       "ARCHS=arm64", "ONLY_ACTIVE_ARCH=YES", "CODE_SIGNING_ALLOWED=YES", "CODE_SIGN_IDENTITY=-"]
            command += ["-only-testing:G2CControl/" + test_class + "/" + test for test in tests]
            with (output / (variant + ".log")).open("w") as log:
                subprocess.run(command + ["test"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=900)
            summary = json.loads(subprocess.check_output(["xcrun", "xcresulttool", "get", "test-results", "summary", "--path", str(result)], env=env))
            (output / (variant + "-summary.json")).write_text(json.dumps(summary, indent=2))
            assert summary["passedTests"] == len(tests) and summary["failedTests"] == 0 and summary["skippedTests"] == 0, summary
            report["cases"][variant] = {"status": "PASS", "tests": tests}
        report["status"] = "VERIFYING_CLEANUP"
    except BaseException as error:
        report["status"] = "FAIL"; report["error"] = type(error).__name__
        raise
    finally:
        report_path.write_text(json.dumps(report, indent=2))
        with lock:
            for released in releases.values(): released.set()
        server.shutdown(); server.server_close()
        if tls:
            for bootstrap in device_project_root.glob("*/M4ControlBootstrap.plist"): bootstrap.unlink()
            for path in output.rglob("*"):
                if path.is_file() and not path.is_symlink() and control_token.encode() in path.read_bytes():
                    report["status"] = "FAIL"; report_path.write_text(json.dumps(report, indent=2)); raise AssertionError("control credential in evidence export")
            if report["status"] != "FAIL":
                try:
                    assert report["head"] == subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(), "head changed during execution"
                    assert all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == digest for p, digest in report["source_hashes"].items()), "source changed during execution"
                except BaseException as error:
                    report.update(status="FAIL", error=type(error).__name__); report_path.write_text(json.dumps(report, indent=2)); raise
            report["credential_scan"] = "PASS"
        else:
            subprocess.run(["xcrun", "simctl", "terminate", args.simulator, BUNDLE], env=env, capture_output=True)
        if report["status"] != "FAIL": report["status"] = "PREPARED_EXECUTION_UNRUN" if args.prepare_only else "PASS"
        report_path.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
