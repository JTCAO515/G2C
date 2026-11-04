"""Throwaway synthetic inputs, no Keychain, network, host file or real key use."""
import base64
from datetime import datetime,timezone
from pathlib import Path

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
