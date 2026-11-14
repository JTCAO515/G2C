"""Exercise the actual shell controller without touching the running stack."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[3] / 'deploy/hk/daily-backup.sh'
DOCKER = """#!/bin/sh
case "$*" in
    *" ps -q --status running api")
        echo api-status >> "$TRACE"
        if [ "$API_RUNNING" = yes ]; then echo api-id; fi ;;
    *" ps -q --status running worker")
        echo worker-status >> "$TRACE"
        if [ "$WORKER_RUNNING" = yes ]; then echo worker-id; fi ;;
    *" ps --all -q --status running --status restarting --status paused backup")
        echo backup-status >> "$TRACE"
        if [ "$ACTIVE_BACKUP" = yes ]; then echo original-backup-id; fi ;;
    *" stop api worker") echo stop >> "$TRACE"; exit "$STOP" ;;
    *" --check-release") echo verify >> "$TRACE"; exit "$VERIFY" ;;
    *" run --rm --no-deps backup") echo backup >> "$TRACE"; exit "$BACKUP" ;;
    *" up -d --no-deps api worker") echo resume >> "$TRACE"; exit "$RESUME" ;;
    *) exit 99 ;;
esac
"""


class DailyBackupRestartTests(unittest.TestCase):
    def run_controller(self, **settings):
        source = SCRIPT.read_text()
        self.assertEqual(source.count('cd /srv/g2c-beta\n'), 1)
        source = source.replace('cd /srv/g2c-beta\n', 'cd "$TEST_ROOT"\n', 1)
        with tempfile.TemporaryDirectory(prefix='g2c-daily-backup-') as directory:
            root = Path(directory)
            docker = root / 'docker'
            docker.write_text(DOCKER)
            docker.chmod(0o700)
            trace = root / 'trace'
            env = dict(os.environ, PATH=str(root)+':/usr/bin:/bin', TEST_ROOT=str(root),
                       TRACE=str(trace), API_RUNNING='yes', WORKER_RUNNING='yes',
                       ACTIVE_BACKUP='no', STOP='0', BACKUP='0', VERIFY='0', RESUME='0')
            env.update(settings)
            result = subprocess.run(['/bin/sh', '-c', source], env=env, capture_output=True,
                                    text=True, timeout=10)
            return result, trace.read_text().splitlines()

    def test_success_resumes_without_rechecking_release(self):
        result, calls = self.run_controller()
        self.assertEqual(result.returncode, 0)
        self.assertEqual(calls, ['api-status', 'worker-status', 'stop', 'backup', 'resume'])

    def test_failed_backup_recovers_once_with_current_release_and_retains_failure(self):
        result, calls = self.run_controller(BACKUP='42')
        self.assertEqual(result.returncode, 42)
        self.assertEqual(calls, ['api-status', 'worker-status', 'stop', 'backup', 'backup-status', 'verify', 'resume'])

    def test_failed_backup_stays_stopped_without_current_release(self):
        result, calls = self.run_controller(BACKUP='42', VERIFY='1')
        self.assertEqual(result.returncode, 42)
        self.assertEqual(calls, ['api-status', 'worker-status', 'stop', 'backup', 'backup-status', 'verify'])

    def test_failed_backup_does_not_reopen_an_already_stopped_pair(self):
        result, calls = self.run_controller(BACKUP='42', WORKER_RUNNING='no')
        self.assertEqual(result.returncode, 42)
        self.assertEqual(calls, ['api-status', 'worker-status', 'stop', 'backup'])

    def test_failed_command_keeps_source_stopped_if_original_backup_is_active(self):
        result, calls = self.run_controller(BACKUP='42', ACTIVE_BACKUP='yes')
        self.assertEqual(result.returncode, 42)
        self.assertEqual(calls, ['api-status', 'worker-status', 'stop', 'backup', 'backup-status'])

    def test_partial_stop_failure_checks_release_without_attempting_backup(self):
        result, calls = self.run_controller(STOP='43')
        self.assertEqual(result.returncode, 43)
        self.assertEqual(calls, ['api-status', 'worker-status', 'stop', 'backup-status', 'verify', 'resume'])

    def test_restart_failure_reports_alert_and_retains_backup_failure(self):
        result, calls = self.run_controller(BACKUP='42', RESUME='44')
        self.assertEqual(result.returncode, 42)
        self.assertEqual(calls.count('resume'), 1)
        self.assertIn('ALERT beta_backup_source_resume_failed', result.stderr)


if __name__ == '__main__':
    unittest.main()
