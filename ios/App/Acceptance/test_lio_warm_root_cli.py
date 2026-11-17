"""Reject unsupported proof scopes before invoking any simulator command."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class WarmRootScopeTests(unittest.TestCase):
    def test_unsupported_native_proof_scopes_never_create_evidence(self):
        cases = [
            (['--scenario', 'lock-screen', '--cold-restart'], 'cannot claim'),
            (['--scenario', 'lock-screen', '--baseline-root'], 'cannot claim'),
            (['--scenario', 'lock-screen', '--deny-after-cold'], 'cannot claim'),
            (['--scenario', 'session', '--lock-fault', 'denied'], 'requires the native'),
            (['--scenario', 'lock-screen', '--lock-fault', 'denied', '--read-fault', 'connection-lost'], 'one native fault'),
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            actuator = root / 'unused-actuator'
            actuator.write_text('This file must never be executed.')
            for index, (options, reason) in enumerate(cases):
                with self.subTest(options=options):
                    evidence = root / str(index)
                    command = [sys.executable, '-B', str(Path(__file__).with_name('check_lio_warm_root.py')),
                        '--output', str(evidence), '--build-dir', str(root / 'build'),
                        '--simulator-control', str(actuator), *options]
                    # If validation regresses, no xcrun/actuator can be dispatched.
                    result = subprocess.run(command, env={**os.environ, 'PATH': ''},
                        capture_output=True, text=True, timeout=10)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn(reason, result.stderr)
                    self.assertFalse(evidence.exists())


if __name__ == '__main__':
    unittest.main()
