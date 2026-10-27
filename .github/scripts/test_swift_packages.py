"""Exercise inventory/partition/failure behavior with a disposable Git repository.

The fake swift command tests orchestration only; CI shards run the real Swift tests.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class SwiftGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="g2c-swift-gate-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.packages = ["ios", "ios/App", "ios/Modules/A", "ios/Modules/B/Tests/Harness"]
        (self.root / ".github/scripts").mkdir(parents=True)
        self.script = self.root / ".github/scripts/swift_packages.py"
        shutil.copy(Path(__file__).with_name("swift_packages.py"), self.script)
        for package in self.packages:
            (self.root / package).mkdir(parents=True, exist_ok=True)
            (self.root / package / "Package.swift").touch()
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "add", "ios"], cwd=self.root, check=True)
        self.inventory(self.packages)
        binary = self.root / "bin"
        binary.mkdir()
        swift = binary / "swift"
        swift.write_text('''#!/usr/bin/env python3
import json, os, sys
with open(os.environ["CALLS"], "a") as f:
    f.write(json.dumps(sys.argv[1:]) + "\\n")
sys.exit(17 if os.environ.get("FAIL_SWIFT") else 0)
''')
        swift.chmod(0o700)
        self.calls = self.root / "calls.jsonl"
        self.env = {**os.environ, "PATH": str(binary) + os.pathsep + os.environ["PATH"],
                    "RUNNER_TEMP": str(self.root), "CALLS": str(self.calls)}

    def inventory(self, value):
        (self.root / ".github/swift-packages.json").write_text(json.dumps(value))

    def run_gate(self, *args, **env):
        return subprocess.run(["python3", "-B", str(self.script), *args],
                              env={**self.env, **env}, capture_output=True, text=True)

    def test_missing_stale_duplicate_and_malformed_inventory_fail(self):
        for value in [self.packages[:-1], self.packages + ["ios/Removed"],
                      self.packages + ["ios"], {}, [1]]:
            with self.subTest(value=value):
                self.inventory(value)
                self.assertNotEqual(self.run_gate().returncode, 0)

    def test_emitted_matrix_runs_every_package_once_and_app_release(self):
        inventory = self.run_gate()
        self.assertEqual(inventory.returncode, 0, inventory.stderr)
        shards = json.loads(inventory.stdout.removeprefix("shards="))
        for shard in shards:
            result = self.run_gate("--shard", str(shard))
            self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()]
        observed = [(c[c.index("--package-path") + 1], c[c.index("-c") + 1]) for c in calls]
        self.assertCountEqual(observed, [(p, "debug") for p in self.packages] + [("ios/App", "release")])

    def test_swift_failure_blocks_shard_without_running_later_packages(self):
        result = self.run_gate("--shard", "0", FAIL_SWIFT="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.calls.read_text().splitlines()), 1)

    def test_invalid_shard_fails(self):
        self.assertNotEqual(self.run_gate("--shard", "99").returncode, 0)


if __name__ == "__main__":
    unittest.main()
