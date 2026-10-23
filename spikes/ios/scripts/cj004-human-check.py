#!/usr/bin/env python3
"""Read-only preflight and human-observation receipts for the fixed CJ004 fixture."""
import argparse
import datetime
import hashlib
import json
import pathlib
import plistlib
import shlex
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CURRENT_ID = "B80AD40D-F779-4FE3-A36D-CFD4C4A19D83"
BUNDLE_ID = "space.go2china.cj004.spike"
SOURCE_HASH = "eb1b4fab47051d0322e7ff419da49dba1569fa010b1070374d66affb8f1f0cd0"
BINARY_HASH = "532860895903c76afe6e482197655885ef3ff5d42788f0085c7a91579f6966ab"
APP = ROOT / ".cache/performance-post-p2/CJIOSSpike.app"


def command(*args):
    return subprocess.check_output(args, text=True).strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory():
    runtimes = json.loads(command("xcrun", "simctl", "list", "runtimes", "--json"))["runtimes"]
    devices = json.loads(command("xcrun", "simctl", "list", "devices", "--json"))["devices"]
    return runtimes, [(runtime, device) for runtime, items in devices.items() for device in items]


def preflight(mode, minimum_id):
    runtimes, devices = inventory()
    available18 = [r for r in runtimes if r.get("isAvailable") and r.get("version", "").split(".")[0] == "18"]
    record = {
        "checked_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source_head": command("git", "-C", str(ROOT), "rev-parse", "HEAD"),
        "mode": mode,
        "bundle_id": BUNDLE_ID,
        "app": str(APP),
        "runtimes": [{k: r.get(k) for k in ("identifier", "version", "isAvailable")} for r in runtimes],
        "minimum18_available": bool(available18),
        "targets": [],
        "blockers": [],
        "side_effects": [],
    }
    try:
        record["source_sha256"] = digest(ROOT / "Sources/SpikeUI/ProbeView.swift")
        record["binary_sha256"] = digest(APP / "CJIOSSpike")
        with (APP / "Info.plist").open("rb") as stream:
            identifier = plistlib.load(stream).get("CFBundleIdentifier")
        if record["source_sha256"] != SOURCE_HASH or record["binary_sha256"] != BINARY_HASH or identifier != BUNDLE_ID:
            record["blockers"].append("FIXED_FIXTURE_IDENTITY_MISMATCH: original owner must supply the fixed build; do not rebuild/overwrite blindly")
    except (OSError, ValueError) as error:
        record["blockers"].append(f"FIXED_BUILD_MISSING: {error}")
    requested = [("CURRENT", CURRENT_ID)]
    if mode == "all":
        if not available18:
            record["blockers"].append("MISSING_IOS18_RUNTIME: no download or device creation will be attempted")
        if not minimum_id:
            record["blockers"].append("MISSING_APPROVED_IOS18_DEVICE_ID: Main must supply an existing authorized CJ004 target")
        else:
            requested.insert(0, ("MINIMUM", minimum_id))
    for role, udid in requested:
        matches = [(runtime, dev) for runtime, dev in devices if dev.get("udid") == udid]
        if len(matches) != 1:
            record["blockers"].append(f"{role}_DEVICE_NOT_FOUND: {udid}")
            continue
        runtime, dev = matches[0]
        valid = dev.get("isAvailable") and dev.get("name", "").startswith("CJ004-")
        valid = valid and (runtime.startswith("com.apple.CoreSimulator.SimRuntime.iOS-18-") if role == "MINIMUM" else runtime == "com.apple.CoreSimulator.SimRuntime.iOS-26-5" and dev.get("name") == "CJ004-iOS26-20261021")
        if not valid:
            record["blockers"].append(f"{role}_TARGET_IDENTITY_MISMATCH: {udid}")
            continue
        target = {"role": role, "udid": udid, "name": dev["name"], "runtime": runtime, "state": dev["state"], "needs_install": False}
        if dev["state"] != "Shutdown":
            record["blockers"].append(f"{role}_DEVICE_BUSY: coordinate its owner; this runner does not take over a running device")
        # simctl get_app_container returns SimError405 for Shutdown targets.
        # Inspect only this validated target's bundle metadata without booting it.
        containers = pathlib.Path.home() / "Library/Developer/CoreSimulator/Devices" / udid / "data/Containers/Bundle/Application"
        installed = []
        try:
            for bundle in containers.glob("*/*.app"):
                with (bundle / "Info.plist").open("rb") as stream:
                    if plistlib.load(stream).get("CFBundleIdentifier") == BUNDLE_ID:
                        installed.append(bundle)
            if len(installed) == 1:
                target["installed_binary_sha256"] = digest(installed[0] / "CJIOSSpike")
                if target["installed_binary_sha256"] != BINARY_HASH:
                    record["blockers"].append(f"{role}_INSTALLED_BUILD_MISMATCH: no overwrite will be attempted")
            elif installed:
                record["blockers"].append(f"{role}_INSTALLED_BUILD_AMBIGUOUS: original owner must inspect")
            elif role == "MINIMUM":
                target["needs_install"] = True
            else:
                record["blockers"].append("CURRENT_INSTALLED_BUILD_UNAVAILABLE: original owner must inspect, not silently reinstall")
        except (OSError, ValueError, plistlib.InvalidFileException) as error:
            record["blockers"].append(f"{role}_INSTALLED_BUILD_UNREADABLE: {error}")
        record["targets"].append(target)
    print(json.dumps(record, indent=2, ensure_ascii=False))
    return 4 if record["blockers"] else 0


def receipt(run_dir, exit_code):
    path = pathlib.Path(run_dir)
    snapshot = json.loads((path / "inputs.json").read_text())
    fields = {}
    if (path / "observations.fields").exists():
        for line in (path / "observations.fields").read_text().splitlines():
            key, value = line.split("=", 1)
            decoded = shlex.split(value)
            fields[key] = decoded[0] if decoded else ""
    all_pass = exit_code == 0
    observed_targets = []
    for target in snapshot["targets"]:
        role = target["role"]
        names = ["SPEECH_RESULT", "FOCUS_RESULT", "ACTIVATION_RESULT", "RESTORE_OFF_RESULT"]
        if role == "MINIMUM":
            names += ["DYNAMIC_TYPE_RESULT", "SELECTION_RESULT"]
        results = {name: fields.get(f"{role}_{name}", "UNKNOWN") for name in names}
        all_pass = all_pass and all(value == "PASS" for value in results.values())
        observed_targets.append({**target, "human_results": results, "human_notes": {key[len(role) + 1:]: value for key, value in fields.items() if key.startswith(role + "_") and key.endswith("_NOTES")}})
    states = []
    try:
        _, devices = inventory()
        allowed = {t["udid"] for t in snapshot["targets"]}
        states = [{k: dev.get(k) for k in ("name", "udid", "state")} for _, dev in devices if dev.get("udid") in allowed]
        all_pass = all_pass and len(states) == len(allowed) and all(dev["state"] == "Shutdown" for dev in states)
    except (OSError, subprocess.SubprocessError, ValueError):
        all_pass = False
    result = {
        "receipt_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "preflight_at_utc": snapshot.get("checked_at_utc"),
        "evidence_kind": "human-entered listening/focus/activation observations, not automatic speech recognition or AX-derived PASS",
        "observer_code": fields.get("OBSERVER", "UNKNOWN"),
        "mode": snapshot["mode"],
        "source_head": snapshot["source_head"],
        "source_sha256": snapshot.get("source_sha256"),
        "binary_sha256": snapshot.get("binary_sha256"),
        "runner_exit_code": exit_code,
        "targets": observed_targets,
        "device_states_at_close": states,
        "remaining_checklist": "OBSERVER_PASS_REVIEW_REQUIRED" if all_pass and snapshot["mode"] == "all" else "INCOMPLETE_OR_CURRENT_ONLY",
        "minimum_runtime18_row": "recorded above" if snapshot["mode"] == "all" else "UNRUN in current-only mode",
        "ticket_close_authority": "Main routes fixed facts through original Review/Testing; unique Publish closes only after original scope is satisfied",
    }
    (path / "receipt.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(f"Receipt: {path / 'receipt.json'}; {result['remaining_checklist']}")


parser = argparse.ArgumentParser()
commands = parser.add_subparsers(dest="command", required=True)
p = commands.add_parser("preflight")
p.add_argument("--mode", choices=["all", "current"], required=True)
p.add_argument("--minimum-device", default="")
p = commands.add_parser("target")
p.add_argument("snapshot")
p.add_argument("role")
p.add_argument("field")
p = commands.add_parser("receipt")
p.add_argument("run_dir")
p.add_argument("exit_code", type=int)
args = parser.parse_args()
if args.command == "preflight":
    sys.exit(preflight(args.mode, args.minimum_device))
elif args.command == "target":
    snapshot = json.loads(pathlib.Path(args.snapshot).read_text())
    target = next(t for t in snapshot["targets"] if t["role"] == args.role)
    print(str(target[args.field]).lower() if isinstance(target[args.field], bool) else target[args.field])
else:
    receipt(args.run_dir, args.exit_code)
