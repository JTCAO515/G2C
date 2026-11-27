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
    *" run --rm --no-deps backup")
        echo backup >> "$TRACE"
        if [ "$BACKUP" = term ]; then kill -TERM "$PPID"; sleep 1; exit 1; fi
        exit "$BACKUP" ;;
    *" up -d --no-deps api worker") echo resume >> "$TRACE"; exit "$RESUME" ;;
    *" up -d --no-deps api") echo resume-api >> "$TRACE"; exit "$RESUME" ;;
    *" up -d --no-deps worker") echo resume-worker >> "$TRACE"; exit "$RESUME" ;;
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
                       ACTIVE_BACKUP='no', STOP='0', BACKUP='0', VERIFY='0', RESUME='0',
                       CJ_BACKUP_ACTIVE_WAIT_SECONDS='0')
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

    def test_failed_backup_resumes_even_without_current_release_and_alerts(self):
        # 2026-11-28 03:00: the release check failed with the same stale image and the source stayed down.
        result, calls = self.run_controller(BACKUP='42', VERIFY='1')
        self.assertEqual(result.returncode, 42)
        self.assertEqual(calls, ['api-status', 'worker-status', 'stop', 'backup', 'backup-status', 'verify', 'resume'])
        self.assertIn('ALERT beta_backup_source_release_unverified_resuming_source', result.stderr)

    def test_failed_backup_reopens_only_the_service_that_was_running(self):
        result, calls = self.run_controller(BACKUP='42', WORKER_RUNNING='no')
        self.assertEqual(result.returncode, 42)
        self.assertEqual(calls, ['api-status', 'worker-status', 'stop', 'backup', 'backup-status', 'verify', 'resume-api'])

    def test_failed_backup_never_reopens_a_pair_that_was_already_stopped(self):
        result, calls = self.run_controller(BACKUP='42', API_RUNNING='no', WORKER_RUNNING='no')
        self.assertEqual(result.returncode, 42)
        self.assertNotIn('resume', calls)
        self.assertNotIn('resume-api', calls)
        self.assertNotIn('resume-worker', calls)

    def test_still_active_original_backup_is_waited_for_then_source_resumes_with_alert(self):
        result, calls = self.run_controller(BACKUP='42', ACTIVE_BACKUP='yes')
        self.assertEqual(result.returncode, 42)
        self.assertEqual(calls, ['api-status', 'worker-status', 'stop', 'backup', 'backup-status', 'verify', 'resume'])
        self.assertIn('ALERT beta_backup_still_active_resuming_source', result.stderr)

    def test_partial_stop_failure_checks_release_and_resumes_without_attempting_backup(self):
        result, calls = self.run_controller(STOP='43')
        self.assertEqual(result.returncode, 43)
        self.assertEqual(calls, ['api-status', 'worker-status', 'stop', 'backup-status', 'verify', 'resume'])

    def test_restart_failure_reports_alert_and_retains_backup_failure(self):
        result, calls = self.run_controller(BACKUP='42', RESUME='44')
        self.assertEqual(result.returncode, 42)
        # One attempt in the failure branch and one retry from the exit trap; the backup failure is kept.
        self.assertEqual(calls.count('resume'), 2)
        self.assertIn('ALERT beta_backup_source_resume_failed', result.stderr)

    def test_success_with_failed_restart_alerts_retries_once_and_fails(self):
        result, calls = self.run_controller(RESUME='44')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls.count('resume'), 2)
        self.assertIn('ALERT beta_backup_source_resume_failed', result.stderr)

    def test_terminated_run_still_resumes_the_source(self):
        # systemd TimeoutStartSec sends TERM to the controller while the backup is running.
        result, calls = self.run_controller(BACKUP='term')
        self.assertEqual(result.returncode, 143)
        self.assertEqual(calls[-1], 'resume')
        self.assertIn('ALERT beta_backup_interrupted_resuming_source', result.stderr)

if __name__ == '__main__':
    unittest.main()
