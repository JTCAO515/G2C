from pathlib import Path
import os
import subprocess

import pytest


SOURCE = 'a' * 40
TAG = 'g2c-beta-operator:' + SOURCE
IMAGE = 'sha256:' + 'b' * 64
SCRIPT = Path(__file__).resolve().parents[1] / 'hk' / 'daily-backup.sh'


@pytest.mark.parametrize('selected,expected,upload_exit,status', [
    (False, True, 0, 0),
    (True, True, 0, 0),
    (True, False, 0, 1),
    (True, True, 37, 37),
])
def test_backup_image_selection_scopes_changes_to_backup(tmp_path, selected, expected, upload_exit, status):
    unit = tmp_path / 'daily-backup.sh'
    unit.write_text(SCRIPT.read_text().replace('/srv/g2c-beta', str(tmp_path)))
    (tmp_path / 'common.env').write_text('CJ_BETA_DB_TARGET=hk-local\n')
    if selected:
        (tmp_path / 'backup.image').write_text(f'{TAG} {IMAGE}\n')
    docker = tmp_path / 'docker'
    docker.write_text('''#!/bin/sh
printf '%s|%s\n' "${CJ_BETA_OPERATOR_IMAGE-unset}" "$*" >> "$BACKUP_TEST_CALLS"
case "$*" in
    'image inspect '*) printf '%s\n' "$BACKUP_TEST_IMAGE" ;;
    *'ps -q --status running api') printf 'api\n' ;;
    *'ps -q --status running worker') printf 'worker\n' ;;
    *'--rm --no-deps backup') exit "$BACKUP_TEST_UPLOAD_EXIT" ;;
esac
''')
    docker.chmod(0o700)
    calls = tmp_path / 'calls'
    runtime_image = IMAGE if expected else 'sha256:' + 'c' * 64
    run = subprocess.run(['/bin/sh', str(unit)], text=True, capture_output=True, check=False, env={
        'PATH': str(tmp_path) + os.pathsep + os.defpath,
        'BACKUP_TEST_CALLS': str(calls),
        'BACKUP_TEST_IMAGE': f'{runtime_image} amd64 {SOURCE}',
        'BACKUP_TEST_UPLOAD_EXIT': str(upload_exit),
    })
    assert run.returncode == status, run.stderr
    invocations = [tuple(line.split('|', 1)) for line in calls.read_text().splitlines()]
    if not expected:
        (environment, command), = invocations
        assert environment == 'unset' and command.startswith('image inspect ')
        return
    backup, = [row for row in invocations if row[1].endswith('--rm --no-deps backup')]
    assert backup[0] == (TAG if selected else 'unset')
    assert ('--pull never' in backup[1]) is selected
    recovery = [row for row in invocations if row[1].endswith('--check-release')]
    if upload_exit:
        (environment, command), = recovery
        assert environment == TAG and 'run --pull never' in command
    else:
        assert not recovery
    assert all(row[0] == 'unset' for row in invocations if row != backup and row not in recovery)
    assert any(row[1].endswith('stop api worker') for row in invocations)
    assert any(row[1].endswith('up -d --no-deps api worker') for row in invocations)
