import os
from pathlib import Path

import pytest

from deploy import recovery


def configure(tmp_path, monkeypatch):
    path=tmp_path/'key'
    path.write_bytes(b'k'*32)  # Explicit synthetic fixture, never a runtime key.
    path.chmod(0o600)
    monkeypatch.setenv('CJ_DEPLOY_RECOVERY_KEY_FILE',str(path))
    return path


def test_signed_checkpoint_tampering_is_rejected(tmp_path,monkeypatch):
    configure(tmp_path,monkeypatch)
    path=tmp_path/'manifest.json'
    recovery.atomic(path,{'dump_sha256':'original'})
    assert recovery.verified(path)=={'dump_sha256':'original'}
    path.write_text(path.read_text().replace('original','modified'))
    with pytest.raises(ValueError,match='signature'):recovery.verified(path)


@pytest.mark.parametrize('kind',['missing','wide-mode','short','oversize','symlink','fifo'])
def test_recovery_key_boundary_refuses_unsafe_inputs(tmp_path,monkeypatch,kind):
    path=configure(tmp_path,monkeypatch)
    if kind=='missing':path.unlink()
    elif kind=='wide-mode':path.chmod(0o644)
    elif kind=='short':path.write_bytes(b'short')
    elif kind=='oversize':path.write_bytes(b'x'*33)
    elif kind=='symlink':
        link=tmp_path/'link';link.symlink_to(path);monkeypatch.setenv('CJ_DEPLOY_RECOVERY_KEY_FILE',str(link))
    else:
        path.unlink();os.mkfifo(path,0o600)
    with pytest.raises((OSError,ValueError)):recovery.key()


def test_missing_configuration_cannot_enable_deployment(monkeypatch):
    monkeypatch.setenv('CJ_ENV','local')
    from deploy.entrypoint import require_configuration
    monkeypatch.delenv('CJ_DEPLOY_PROVIDER',raising=False)
    with pytest.raises(ValueError):require_configuration()


def test_wrong_database_target_cannot_use_release(tmp_path,monkeypatch):
    configure(tmp_path,monkeypatch)
    recovery.atomic(tmp_path/'latest.json',{'dump_sha256':'checkpoint'})
    recovery.atomic(tmp_path/'release.json',{'checkpoint':'checkpoint','target':'different','database_oid':1})
    with pytest.raises(ValueError,match='not_released'):
        recovery.require_release({'host':'/synthetic/socket','dbname':'target'},tmp_path)
