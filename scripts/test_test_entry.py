"""Default-entry orchestration only; the entry separately runs the real suites.

Other children are substituted here so every new child can be made to fail
without changing domain tests or replaying all legacy suites five extra times.
"""
from contextlib import redirect_stdout
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts import test as entry


OFFLINE_CASES = (
    ('eval/lio_calendar_transitions', ('eval/tests/test_lio_calendar_transitions.py',)),
    ('eval/optimization', ('eval.optimization.test_score',)),
    ('tooling/datasets', ('tooling/datasets', 'test_*.py')),
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
                if label == 'tooling/datasets':
                    self.assertEqual(argv[1:], ['-B', '-m', 'unittest', 'discover', '-s',
                                               'tooling/datasets', '-t', '.', '-p', 'test_*.py', '-v'])
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

    def test_teacher_failure_is_discovered_and_reaches_the_default_entry(self):
        actual_run = subprocess.run
        with tempfile.TemporaryDirectory(prefix='g2c-teacher-gate-') as directory:
            root = Path(directory)
            datasets = root / 'tooling/datasets'
            datasets.mkdir(parents=True)
            (root / 'tooling/__init__.py').touch()
            (datasets / '__init__.py').touch()
            (datasets / 'test_convert.py').write_text(
                'import unittest\nclass Convert(unittest.TestCase):\n'
                '    def test_convert_still_runs(self): pass\n')
            (datasets / 'test_teacher.py').write_text(
                'import unittest\nclass Teacher(unittest.TestCase):\n'
                '    def test_teacher_gate(self): self.fail("intentional teacher failure")\n')
            children = []

            def inject(argv, **kwargs):
                if 'tooling/datasets' in argv:
                    # Use the real discovery command against a disposable package:
                    # the old conversion test passes, only the teacher test fails.
                    result = actual_run(argv, **{**kwargs, 'cwd': root},
                                        capture_output=True, text=True)
                    children.append(result)
                    return result
                return subprocess.CompletedProcess(argv, 0)

            output = io.StringIO()
            with patch.object(entry.subprocess, 'run', side_effect=inject), redirect_stdout(output):
                self.assertEqual(entry.main(), 1)
            self.assertEqual(len(children), 1)
            self.assertEqual(children[0].returncode, 1)
            self.assertIn('test_convert_still_runs', children[0].stderr)
            self.assertIn('test_teacher_gate', children[0].stderr)
            self.assertIn('Ran 2 tests', children[0].stderr)
            self.assertIn('FAILED: tooling/datasets', output.getvalue())
            print('teacher discovery injection: convert=PASS, teacher=FAIL -> child=1 -> default entry=1')


if __name__ == '__main__':
    unittest.main()
