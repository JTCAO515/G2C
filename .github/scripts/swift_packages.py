"""Validate all tracked iOS manifests, then test every package using one locked build directory."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]


def package_inventory():
    packages = json.loads((ROOT / ".github/swift-packages.json").read_text())
    tracked = subprocess.check_output(
        ["git", "ls-files", "-z", "--", "ios"], cwd=ROOT
    ).decode().split("\0")
    actual = {str(Path(name).parent) for name in tracked if Path(name).name == "Package.swift"}
    if not isinstance(packages, list) or any(not isinstance(p, str) for p in packages):
        raise SystemExit("Swift inventory must be a list of package paths")
    if len(packages) != len(set(packages)) or set(packages) != actual:
        raise SystemExit(f"Swift inventory mismatch: missing={sorted(actual - set(packages))}, "
                         f"stale={sorted(set(packages) - actual)}; duplicates are forbidden")
    return packages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true", help="Run every package in inventory order")
    args = parser.parse_args()
    packages = package_inventory()
    if not args.run:
        print("packages=" + json.dumps(packages))
        return

    # The runner owns its scratch directory. Sequential package builds reuse only
    # compiler outputs, while SwiftPM still resolves/builds/runs each package's tests.
    scratch = Path(os.environ["RUNNER_TEMP"]) / "swift-build"
    for package in packages:
        for configuration in (["debug", "release"] if package == "ios/App" else ["debug"]):
            print(f"::group::{package} ({configuration})", flush=True)
            start = time.monotonic()
            subprocess.run(
                ["swift", "test", "--force-resolved-versions", "--package-path", package, "--scratch-path", str(scratch),
                 "-c", configuration], cwd=ROOT, check=True
            )
            print(f"PASS {package} ({configuration}) {time.monotonic() - start:.1f}s", flush=True)
            print("::endgroup::", flush=True)


if __name__ == "__main__":
    main()
