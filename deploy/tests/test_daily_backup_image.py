from pathlib import Path
import os
import shutil
import subprocess
import sys
from types import SimpleNamespace

import pytest

from deploy.hk.daily_backup_image import read_selection


SOURCE = 'a' * 40
TAG = 'g2c-beta-operator:' + SOURCE
IMAGE = 'sha256:' + 'b' * 64
SCRIPT = Path(__file__).resolve().parents[1] / 'hk' / 'daily-backup.sh'


@pytest.mark.parametrize('selected,expected,config_exit,upload_exit,status', [
    (False, True, 0, 0, 0),
    (True, True, 0, 0, 0),
    (True, False, 0, 0, 1),
    (True, True, 0, 37, 37),
    (True, True, 38, 0, 38),
])
def test_backup_image_selection_scopes_changes_to_backup(tmp_path, selected, expected, config_exit, upload_exit, status):
    unit = tmp_path / 'daily-backup.sh'
    unit.write_text(SCRIPT.read_text().replace('/srv/g2c-beta', str(tmp_path)))
    (tmp_path / 'common.env').write_text('CJ_BETA_DB_TARGET=hk-local\n')
    if selected:
        (tmp_path / 'backup.image').write_text(f'{TAG} {IMAGE}\n')
    reader = tmp_path / 'python3'
    reader.write_text('''#!/bin/sh
if [ -f backup.image ]; then cat backup.image; fi
''')
    reader.chmod(0o700)
    docker = tmp_path / 'docker'
    docker.write_text('''#!/bin/sh
printf '%s|%s\n' "${CJ_BETA_OPERATOR_IMAGE-unset}" "$*" >> "$BACKUP_TEST_CALLS"
case "$*" in
    'image inspect '*) printf '%s\n' "$BACKUP_TEST_IMAGE" ;;
    *'ps -q --status running api') printf 'api\n' ;;
    *'ps -q --status running worker') printf 'worker\n' ;;
    *'stop api worker') touch "$BACKUP_TEST_TAG_CHANGED" ;;
esac
case "$*" in
    *'run --pull '*) printf 'unknown flag: --pull\n' >&2; exit 125 ;;
    *'config --quiet') exit "$BACKUP_TEST_CONFIG_EXIT" ;;
    *'run '* )
        if [ -f "$BACKUP_TEST_TAG_CHANGED" ] && [ "${CJ_BETA_OPERATOR_IMAGE-unset}" = "$BACKUP_TEST_MUTABLE_TAG" ]; then
            exit 42
        fi
        ;;
esac
case "$*" in
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
        'BACKUP_TEST_CONFIG_EXIT': str(config_exit),
        'BACKUP_TEST_UPLOAD_EXIT': str(upload_exit),
        'BACKUP_TEST_TAG_CHANGED': str(tmp_path / 'tag-changed'),
        'BACKUP_TEST_MUTABLE_TAG': TAG,
    })
    assert run.returncode == status, run.stderr
    invocations = [tuple(line.split('|', 1)) for line in calls.read_text().splitlines()]
    if not expected:
        (environment, command), = invocations
        assert environment == 'unset' and command.startswith('image inspect ')
        return
    overlay = '-f deploy/hk/compose.backup-image.yaml --profile operator'
    config = [row for row in invocations if row[1].endswith('config --quiet')]
    if selected:
        (environment, command), = config
        assert environment == IMAGE and overlay in command
    else:
        assert not config
    if config_exit:
        assert len(invocations) == 2
        return
    backup, = [row for row in invocations if row[1].endswith('--rm --no-deps backup')]
    assert backup[0] == (IMAGE if selected else 'unset')
    assert (overlay in backup[1]) is selected
    recovery = [row for row in invocations if row[1].endswith('--check-release')]
    if upload_exit:
        (environment, command), = recovery
        assert environment == IMAGE and overlay in command
    else:
        assert not recovery
    for row in invocations:
        if row != backup and row not in config + recovery:
            assert row[0] == 'unset' and overlay not in row[1]
    assert any(row[1].endswith('stop api worker') for row in invocations)
    assert any(row[1].endswith('up -d --no-deps api worker') for row in invocations)


@pytest.mark.parametrize('uid,mode', [(10001, 0o600), (0, 0o620), (0, 0o602)])
def test_pin_rejects_non_root_owner_or_other_writers(tmp_path, monkeypatch, uid, mode):
    selector = tmp_path / 'backup.image'
    selector.write_text(f'{TAG} {IMAGE}\n')
    selector.chmod(mode)
    real_fstat = os.fstat

    def fstat(fd):
        return SimpleNamespace(st_uid=uid, st_mode=real_fstat(fd).st_mode)

    with monkeypatch.context() as env:
        env.setattr(os, 'fstat', fstat)
        with pytest.raises(ValueError, match='root-owned'):
            read_selection(selector)


def test_pin_checks_and_reads_the_same_opened_file(tmp_path, monkeypatch):
    selector = tmp_path / 'backup.image'
    selector.write_text(f'{TAG} {IMAGE}\n')
    selector.chmod(0o600)
    replacement = tmp_path / 'alternate'
    different_id = 'sha256:' + 'c' * 64
    replacement.write_text(f'{TAG} {different_id}\n')
    real_fstat = os.fstat

    def fstat(fd):
        checked = real_fstat(fd)
        replacement.replace(selector)
        return SimpleNamespace(st_uid=0, st_mode=checked.st_mode)

    with monkeypatch.context() as env:
        env.setattr(os, 'fstat', fstat)
        assert read_selection(selector) == (TAG, IMAGE)
    assert selector.read_text() == f'{TAG} {different_id}\n'


def test_pin_rejects_a_dangling_symlink_and_recognizes_absence(tmp_path):
    selector = tmp_path / 'backup.image'
    assert read_selection(selector) is None
    selector.symlink_to(tmp_path / 'absent')
    with pytest.raises(OSError):
        read_selection(selector)


@pytest.mark.parametrize('pin_state', ['untrusted', 'removed_before_open'])
def test_invalid_pin_fails_before_docker(tmp_path, pin_state):
    unit = tmp_path / 'daily-backup.sh'
    unit.write_text(SCRIPT.read_text().replace('/srv/g2c-beta', str(tmp_path)))
    helper = tmp_path / 'deploy/hk/daily_backup_image.py'
    helper.parent.mkdir(parents=True)
    shutil.copyfile(SCRIPT.with_name(helper.name), helper)
    selector = tmp_path / 'backup.image'
    selector.write_text(f'{TAG} {IMAGE}\n')
    selector.chmod(0o622)
    reader = tmp_path / 'python3'
    if pin_state == 'untrusted':
        reader.symlink_to(sys.executable)
    else:
        reader.write_text('#!/bin/sh\nexit 0\n')
        reader.chmod(0o700)
    docker = tmp_path / 'docker'
    docker.write_text('#!/bin/sh\nprintf docker-called\n')
    docker.chmod(0o700)
    run = subprocess.run(['/bin/sh', str(unit)], text=True, capture_output=True, check=False,
                         env={'PATH': str(tmp_path) + os.pathsep + os.defpath})
    assert run.returncode == 1
    assert run.stdout == ''
    assert run.stderr.strip() == 'ALERT beta_backup_image_selection_invalid'
