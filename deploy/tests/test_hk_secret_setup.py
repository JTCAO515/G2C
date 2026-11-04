"""Throwaway synthetic inputs, no Keychain, network, host file or real key use."""
import base64
import json
import sys
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from cj_api import supabase_test_database as boundary
from cj_api.composition import CompositionUnavailable
from deploy.hk import secret_setup


class Clock(datetime):
    @classmethod
    def now(cls,tz=None):return datetime(2026,11,4,tzinfo=timezone.utc)


def inputs():
    def uri(role):return 'postgresql://'+role+'.'+boundary.REF+':synthetic-only@'+boundary.HOST+':5432/postgres?sslmode=verify-full'
    return dict(operator_uri=uri('postgres'),runtime_uri=uri('cj_m1_runtime'),cleanup_uri=uri('cj_local_cleanup'),
        model_key='synthetic-model-key-000000',amap_key='synthetic-amap-key-000000',oss_id='LTAI'+'a'*20,oss_secret='b'*30,
        trial_expiry='2027-02-03T00:00:00+08:00',revision='a'*40)


def test_secret_plan_separates_roles_and_keeps_common_public(monkeypatch):
    monkeypatch.setenv('CJ_ENV','local');monkeypatch.setattr(boundary,'datetime',Clock)
    files,meta=secret_setup.plan(inputs(),now=Clock.now(),nonce='abcdef123456')
    parsed={name:dict(line.split('=',1) for line in body.decode().splitlines()) for name,body in files.items()}
    assert set(files)=={'api.env','worker.env','operator.env','backup.env','rehearsal.env','common.env','compose.env'}
    assert set(parsed['api.env'])=={'CJ_SUPABASE_RUNTIME_URI','CJ_BETA_CONFIRMATION_B64','CJ_BETA_HISTORY_B64'}
    assert set(parsed['worker.env'])=={'CJ_SUPABASE_RUNTIME_URI','CJ_BETA_SIGNING_PRIVATE_B64','CJ_MODEL_API_KEY','CJ_AMAP_WEB_KEY'}
    common=parsed['common.env'];private=parsed['worker.env']['CJ_BETA_SIGNING_PRIVATE_B64']
    assert private not in files['common.env'].decode()
    key=serialization.load_pem_private_key(base64.b64decode(private),password=None)
    public=serialization.load_pem_public_key(base64.b64decode(common['CJ_BETA_SIGNING_PUBLIC_B64']))
    assert key.key_size==2048 and key.public_key().public_numbers()==public.public_numbers()
    recovery=Ed25519PrivateKey.from_private_bytes(base64.b64decode(parsed['operator.env']['CJ_BETA_RECOVERY_PRIVATE_B64']))
    assert recovery.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)==base64.b64decode(common['CJ_BETA_RECOVERY_PUBLIC_B64'])
    assert len({parsed['api.env']['CJ_BETA_CONFIRMATION_B64'],parsed['api.env']['CJ_BETA_HISTORY_B64'],parsed['rehearsal.env']['CJ_BETA_CLEANUP_B64']})==3
    assert len(meta['recovery_subjects'])==2 and all(s.startswith('m4-synthetic-recovery-abcdef123456-') for s in meta['recovery_subjects'])
    assert json.loads(common['CJ_BETA_SUBJECTS_JSON'])==['m4-synthetic-beta-a','m4-synthetic-beta-b']
    rehearsal=parsed['rehearsal.env']
    assert json.loads(rehearsal['CJ_REHEARSAL_SUBJECTS_JSON'])==meta['recovery_subjects']
    assert 'CJ_SUPABASE_CLEANUP_URI' not in parsed['operator.env']
    other=serialization.load_pem_private_key(base64.b64decode(rehearsal['CJ_REHEARSAL_SIGNING_PRIVATE_B64']),password=None)
    assert other.public_key().public_numbers()!=key.public_key().public_numbers()
    assert other.public_key().public_numbers()==serialization.load_pem_public_key(base64.b64decode(rehearsal['CJ_REHEARSAL_SIGNING_PUBLIC_B64'])).public_numbers()
    assert 'model_key' not in str(meta) and 'synthetic-only' not in str(meta)


def test_secret_plan_refuses_role_substitution_missing_inputs_and_expiry(monkeypatch):
    monkeypatch.setenv('CJ_ENV','local');monkeypatch.setattr(boundary,'datetime',Clock)
    for field in ('runtime_uri','cleanup_uri'):
        value=inputs();value[field]=value['operator_uri']
        with pytest.raises((ValueError,CompositionUnavailable)):secret_setup.plan(value,now=Clock.now(),nonce='abcdef123456')
    value=inputs();del value['oss_secret']
    with pytest.raises((ValueError,CompositionUnavailable)):secret_setup.plan(value,now=Clock.now(),nonce='abcdef123456')
    value=inputs();value['trial_expiry']='2026-11-03T00:00:00+00:00'
    with pytest.raises((ValueError,CompositionUnavailable)):secret_setup.plan(value,now=Clock.now(),nonce='abcdef123456')


def test_real_secret_cli_rejects_wrong_or_ephemeral_mount_before_reading_credentials(monkeypatch):
    monkeypatch.setattr(secret_setup.os,'getuid',lambda:0)
    host=['iZj6c3ldt64bg18flzpr7hZ'];mount=['1 2 0:3 / /host rw - tmpfs tmpfs rw\n']
    original=Path.read_text
    def read(path,*args,**kwargs):
        if path==Path('/run/config/host-name'):return host[0]
        if path==Path('/proc/self/mountinfo'):return mount[0]
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',read)
    source=MagicMock();monkeypatch.setattr(sys,'stdin',SimpleNamespace(buffer=source))
    with pytest.raises(SystemExit):secret_setup.main()
    source.read.assert_not_called()
    mount[0]='1 2 8:1 /srv/wrong /host rw - ext4 /dev/vda1 rw\n'
    with pytest.raises(ValueError):secret_setup.require_host()
    mount[0]='1 2 8:1 /srv/g2c-beta /host rw - ext4 /dev/vda1 rw\n'
    secret_setup.require_host()
    host[0]='another-host'
    with pytest.raises(ValueError):secret_setup.require_host()


def test_deleted_terminal_requires_exact_physical_rows_and_target_fences():
    from deploy.hk.cloud_rehearsal import Host
    proof=dict(rows=dict(account_messages=0,retained_messages=1,selected_memory=0),account_access='denied',memory_owner_access='allowed',
        fence_counts=dict(cj_account_fence=1,item=1,action=1))
    Host.require_deleted(proof)
    for field in ('cj_account_fence','item','action'):
        invalid=dict(proof,fence_counts=dict(proof['fence_counts'],**{field:0}))
        with pytest.raises(ValueError):Host.require_deleted(invalid)
    with pytest.raises(ValueError):Host.require_deleted(dict(proof,rows=dict(proof['rows'],selected_memory=1)))


@pytest.mark.parametrize('reason',['expired_authorization','invalid_release'])
def test_payload_barrier_guard_rejects_before_cleanup_scope_or_reads(monkeypatch,reason):
    from psycopg.pq import TransactionStatus
    from cj_cleanup import memory_barrier
    from cj_cleanup.store import Store
    connection=MagicMock();connection.autocommit=False;connection.info.transaction_status=TransactionStatus.IDLE
    cursor=connection.cursor.return_value.__enter__.return_value
    def guard(cur):
        assert cur is cursor
        raise ValueError(reason)
    store=Store(lambda:connection,'a'*64,lambda stage:None,before_transaction=guard)
    prototype=SimpleNamespace(subject_digest='a'*64,domain_scope='synthetic-scope',selection=SimpleNamespace(kind='memory'),
        protocol='CLEANUP@1.1',target='business/message')
    monkeypatch.setattr(memory_barrier,'parse_original',lambda *args:None)
    with pytest.raises(ValueError,match=reason):
        with memory_barrier.hold_payloads(store,'synthetic-scope',b'synthetic',prototype):raise AssertionError('guard bypassed')
    cursor.execute.assert_not_called();connection.close.assert_called_once()
