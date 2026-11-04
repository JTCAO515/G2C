import os
from pathlib import Path

import pytest

from deploy import recovery
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization


def configure(tmp_path, monkeypatch):
    path=tmp_path/'key'
    path.write_bytes(b'k'*32)  # Explicit synthetic fixture, never a runtime key.
    path.chmod(0o600)
    monkeypatch.setenv('CJ_DEPLOY_RECOVERY_KEY_FILE',str(path))
    public=tmp_path/'recovery.pub'
    public.write_bytes(Ed25519PrivateKey.from_private_bytes(path.read_bytes()).public_key().public_bytes(
        serialization.Encoding.Raw,serialization.PublicFormat.Raw))
    monkeypatch.setenv('CJ_DEPLOY_RECOVERY_PUBLIC_KEY_FILE',str(public))
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


def test_wrong_public_key_cannot_verify_release(tmp_path,monkeypatch):
    configure(tmp_path,monkeypatch)
    recovery.atomic(tmp_path/'manifest.json',{'checkpoint':'synthetic'})
    (tmp_path/'recovery.pub').write_bytes(b'0'*32)
    with pytest.raises(ValueError,match='signature'):recovery.verified(tmp_path/'manifest.json')


def test_nonlocal_migration_is_rejected_before_connection(tmp_path,monkeypatch):
    import json
    monkeypatch.setenv('CJ_ENV','local')
    from deploy import entrypoint
    from cj_api.composition import CompositionUnavailable
    path=tmp_path/'migration.json';path.write_text(json.dumps({'host':'nonlocal.invalid','dbname':'synthetic','user':'synthetic'}))
    monkeypatch.setenv('CJ_DEPLOY_MIGRATION_CONNINFO',str(path))
    monkeypatch.setattr(entrypoint,'require_configuration',lambda:None)
    def forbidden(*args,**kwargs):raise AssertionError('must not reach connection driver')
    monkeypatch.setattr(entrypoint.psycopg,'connect',forbidden)
    with pytest.raises(CompositionUnavailable):entrypoint.initialize()


@pytest.mark.parametrize('extra',[{'conninfo':'hostaddr=127.0.0.1'},
    {'hostaddr':'127.0.0.1'},{'dbname':'hostaddr=127.0.0.1 dbname=warehouse'},
    {'dbname':'postgresql://synthetic.invalid/warehouse'},{'port':'5432,6543'}])
def test_local_connection_aliases_and_native_tool_dsn_are_rejected(extra,monkeypatch):
    monkeypatch.setenv('CJ_ENV','local')
    from cj_api.local_app import local_connection
    from cj_api.composition import CompositionUnavailable
    config=dict(host='/synthetic/socket',dbname='postgres',user='cj_deploy_admin')
    config.update(extra)
    with pytest.raises(CompositionUnavailable):local_connection(config)


def test_local_connection_preserves_private_harness_options_once(monkeypatch):
    monkeypatch.setenv('CJ_ENV','local')
    from cj_api.local_app import local_connection
    options=dict(host='/synthetic/socket',port=55865,dbname='postgres',user='operator',
                 passfile='/synthetic/empty.pgpass',connect_timeout=5,options='-c statement_timeout=10000 -c search_path=public',
                 application_name='synthetic-controlled-worker')
    config=local_connection(options)
    assert dict(config)==options and local_connection(config) is config
    with pytest.raises(TypeError):config['dbname']='other'


def test_invalid_runtime_options_produce_unavailable_before_driver(tmp_path,monkeypatch):
    import json
    monkeypatch.setenv('CJ_ENV','local')
    from deploy import entrypoint
    path=tmp_path/'runtime.json';path.write_text(json.dumps(dict(host='/synthetic/socket',dbname='postgres',conninfo='hostaddr=127.0.0.1')))
    monkeypatch.setenv('CJ_LOCAL_CONNINFO',str(path));monkeypatch.setenv('CJ_DEPLOY_CONTROL',str(tmp_path))
    monkeypatch.setattr(entrypoint,'require_configuration',lambda:None)
    def forbidden(*args,**kwargs):raise AssertionError('must not connect')
    monkeypatch.setattr(entrypoint.psycopg,'connect',forbidden)
    assert entrypoint.ready()=='deployment_gate_unavailable'


def test_build_context_uses_committed_allowed_blobs_only(tmp_path):
    import subprocess
    from deploy.build import source_context
    repo=tmp_path/'repo';repo.mkdir();(repo/'scripts').mkdir()
    subprocess.run(['git','init','-q',str(repo)],check=True)
    (repo/'scripts/module.py').write_text('COMMITTED=True\n')
    (repo/'scripts/approved-name.pem').write_text('synthetic-secret')
    subprocess.run(['git','add','.'],cwd=repo,check=True)
    subprocess.run(['git','-c','user.name=Synthetic','-c','user.email=synthetic@example.invalid','commit','-qm','fixture'],cwd=repo,check=True)
    (repo/'scripts/module.py').write_text('DIRTY=True\n')
    (repo/'scripts/operator-key.pem').write_text('synthetic-untracked-secret')
    (repo/'scripts/untracked-note.log').write_text('synthetic-log')
    destination=tmp_path/'context';destination.mkdir();source_context(repo,destination)
    assert (destination/'scripts/module.py').read_text()=='COMMITTED=True\n'
    assert sorted(p.name for p in (destination/'scripts').iterdir())==['module.py']
