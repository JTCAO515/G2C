"""Default-entry orchestration only; the entry separately runs the real suites.

Other children are substituted here so every new child can be made to fail
without changing domain tests or replaying all legacy suites five extra times.
"""
from contextlib import redirect_stdout
import io
import subprocess
import sys
import unittest
from unittest.mock import patch

from scripts import test as entry


OFFLINE_CASES = (
    ('eval/optimization', ('eval.optimization.test_score',)),
    ('tooling/datasets', ('tooling.datasets.test_convert',)),
    ('tooling/optimization', ('tooling.optimization.test_optimization',)),
    ('tooling/training preflight', ('tooling/training', 'test_*.py')),
    ('tooling/training F schema', ('tooling/training/check_f_dataset.py',)),
)


class EntryTests(unittest.TestCase):
    def test_registration_and_existing_python_launch_are_preserved(self):
        calls = []

        def succeed(argv, **kwargs):
            calls.append((argv, kwargs))
            return subprocess.CompletedProcess(argv, 0)

        with patch.object(entry.subprocess, 'run', side_effect=succeed), redirect_stdout(io.StringIO()):
            self.assertEqual(entry.main(), 0)
        for label, tokens in OFFLINE_CASES:
            with self.subTest(suite=label):
                matching = [(argv, kwargs) for argv, kwargs in calls if all(token in argv for token in tokens)]
                self.assertEqual(len(matching), 1)
                argv, kwargs = matching[0]
                self.assertEqual(kwargs['cwd'], entry.ROOT)
                if label == 'tooling/optimization':
                    self.assertEqual(argv[:4], ['uv', 'run', '--project', 'tooling/optimization'])
                    self.assertIn('--locked', argv)
                    self.assertEqual(kwargs['env']['PYTHONPATH'], str(entry.ROOT))
                else:
                    self.assertEqual(argv[0], sys.executable)
        # Representative original groups and their interpreter remain intact;
        # the complete real default-entry run supplies full legacy-suite evidence.
        commands = [argv for argv, _ in calls]
        self.assertTrue(any(argv[0] == sys.executable and 'backend/tests' in argv for argv in commands))
        self.assertTrue(any('scripts.test_test_entry' in argv for argv in commands))
        self.assertIn('openapi_spec_validator', commands[-1])

    def test_every_new_child_nonzero_reaches_the_default_entry(self):
        actual_run = subprocess.run
        for label, tokens in OFFLINE_CASES:
            with self.subTest(suite=label):
                failures = []

                def inject(argv, **kwargs):
                    if all(token in argv for token in tokens):
                        # A real process fails; both entry.run and entry.main
                        # must retain that result. No domain assertion is edited.
                        result = actual_run([sys.executable, '-B', '-c', 'raise SystemExit(17)'], **kwargs)
                        failures.append(result.returncode)
                        return result
                    return subprocess.CompletedProcess(argv, 0)

                output = io.StringIO()
                with patch.object(entry.subprocess, 'run', side_effect=inject), redirect_stdout(output):
                    self.assertEqual(entry.main(), 1)
                self.assertEqual(failures, [17])
                self.assertIn('FAILED: ' + label, output.getvalue())
                print(f'orchestration injection: {label}: child=17 -> default entry=1')


if __name__ == '__main__':
    unittest.main()
