"""cleanup_worker.main keeps serving later subjects when one subject fails, then still fails."""
from contextlib import redirect_stdout
import io
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]


class Decision:
    def __init__(self, subject, allowed=True):
        from cj_auth.interfaces import AdmissionStatus
        self.status = AdmissionStatus.ALLOWED if allowed else AdmissionStatus.DENIED
        self.principal = subject


class Checker:
    def __init__(self, denied=()):
        self.denied = set(denied)

    def check(self, token):
        return Decision(token, token not in self.denied)


@unittest.skipUnless(os.environ.get('CJ_ENV') == 'local', 'cleanup_worker requires CJ_ENV=local')
class CleanupWorkerIsolationTests(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        import cleanup_worker
        self.worker = cleanup_worker
        self.argv = ['cleanup_worker.py', '--conninfo-json', 'c.json', '--auth-dir', 'auth',
                     '--cleanup-config', 'cleanup.json', '--once']

    def run_main(self, checker, step):
        output = io.StringIO()
        with mock.patch.object(sys, 'argv', self.argv), \
                mock.patch.object(self.worker, 'LocalDatabase'), \
                mock.patch.object(self.worker, 'load_configuration'), \
                mock.patch.object(self.worker, 'Runtime'), \
                mock.patch.object(self.worker, 'checker_for', return_value=checker), \
                mock.patch.object(self.worker, 'invited_subjects', return_value={'c', 'a', 'b'}), \
                mock.patch.object(self.worker.dev_auth, 'token', side_effect=lambda auth, subject, minutes: subject), \
                mock.patch.object(self.worker, 'step', side_effect=step), \
                redirect_stdout(output):
            try:
                self.worker.main()
            finally:
                self.output = output.getvalue()

    def test_failing_subject_does_not_stop_later_subjects(self):
        served = []
        def step(runtime, checker, principal):
            served.append(principal)
            if principal == 'a':
                raise RuntimeError('original operation unavailable')
            return {'operation_id': 'op-' + principal, 'status': 'complete'}
        with self.assertRaisesRegex(RuntimeError, 'original operation unavailable'):
            self.run_main(Checker(), step)
        self.assertEqual(served, ['a', 'b', 'c'])
        self.assertIn('op-b', self.output)
        self.assertIn('op-c', self.output)

    def test_unavailable_identity_does_not_stop_later_subjects(self):
        served = []
        def step(runtime, checker, principal):
            served.append(principal)
            return {'operation_id': 'op-' + principal, 'status': 'complete'}
        with self.assertRaisesRegex(SystemExit, 'local maintenance identity unavailable'):
            self.run_main(Checker(denied={'a'}), step)
        self.assertEqual(served, ['b', 'c'])


if __name__ == '__main__':
    unittest.main()
