"""Signed local allowance + locked SDK over fake HTTP; no cloud or real keys."""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from datetime import datetime,timezone
from contextlib import contextmanager

import alibabacloud_oss_v2 as oss
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from deploy.hk import checkpoint,oss_backup
from deploy.hk.oss_quota import Client,GIB
from deploy.hk import oss_quota
from test_hk_boundaries import activate,Objects
from test_oss_sdk_contract import Session,service

READ_AUTHORITY=oss_quota.read_authority


def allowance(root,monkeypatch,*,mode='paid_capped',requests=0,size=0,expires_at='2026-11-30T16:00:00+00:00'):
    activate(monkeypatch);key=Ed25519PrivateKey.generate();root.mkdir(mode=0o700)
    monkeypatch.setenv('CJ_BETA_RECOVERY_PRIVATE_B64',base64.b64encode(key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption())).decode())
    monkeypatch.setenv('CJ_BETA_RECOVERY_PUBLIC_B64',base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode())
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return datetime(2026,11,4,tzinfo=timezone.utc)
    monkeypatch.setattr(oss_quota,'datetime',Clock)
    policy=dict(version='g2c-beta-oss-authorization.1',mode=mode,source='synthetic offline fixture; not JT approval',request_limit=300,byte_limit=2*GIB,
        hold_limit_fen=1000 if mode=='paid_capped' else 0,expires_at=expires_at)
    # Substitute only this test's root-policy reader boundary; no real root
    # authority or cloud identity is created by an offline test.
    monkeypatch.setattr(oss_quota,'read_authority',lambda:policy)
    identity=hashlib.sha256(checkpoint.canonical(policy)).hexdigest();history=root/'intents';history.mkdir(mode=0o700)
    requests=max(requests,(size+67108863)//67108864);remaining=size;tip='0'*64
    for i in range(1,requests+1):
        chunk=min(remaining,67108864);remaining-=chunk
        value=dict(version='g2c-beta-oss-intent.1',authorization_sha256=identity,sequence=i,previous=tip,
            kind='get' if chunk else 'head',object_sha256='a'*64,bytes=chunk)
        path=history/f'{i:06d}.json';path.write_text(json.dumps(checkpoint.envelope(value)));path.chmod(0o400)
        tip=hashlib.sha256(checkpoint.canonical(value)).hexdigest()
    checkpoint.atomic(root/'usage.json',dict(version='g2c-beta-oss-usage.1',authorization_sha256=identity,requests=requests,reserved_bytes=size,tip=tip))
    return policy


def test_actual_sdk_counts_every_request_before_send_and_readonly_get_is_free_of_new_dispatch(tmp_path,monkeypatch):
    root=tmp_path/'control';allowance(root,monkeypatch);session=Session();client=Client(service(session),root=root)
    source=tmp_path/'database.dump';source.write_bytes(b'synthetic quota checkpoint');sha=hashlib.sha256(source.read_bytes()).hexdigest()
    key='backups/20261104T000000Z-'+sha+'/database.dump'
    assert oss_backup.upload_file(client,source,key,tmp_path/'put.json')=='HEAD_CONFIRMED'
    assert oss_backup.download_file(client,key,tmp_path/'download.dump',sha,limit=1024)=='GET_VERIFIED'
    state=checkpoint.verified(root/'usage.json');assert state['requests']==len(session.calls)==6
    assert state['reserved_bytes']==67108864+source.stat().st_size
    assert oss_backup.download_file(client,key,tmp_path/'download.dump',sha,limit=1024)=='READ_ONLY_ORIGINAL'
    assert checkpoint.verified(root/'usage.json')==state and len(session.calls)==6


def test_missing_or_lost_counter_and_wrong_bucket_cannot_dispatch(tmp_path,monkeypatch):
    root=tmp_path/'control';allowance(root,monkeypatch);session=Session();client=Client(service(session),root=root)
    key='backups/20261104T000000Z-'+'a'*64+'/database.dump'
    with pytest.raises(ValueError):client.head_object(oss.HeadObjectRequest(bucket='other-bucket',key=key))
    (root/'usage.json').unlink()  # this test's disposable lost-counter fault
    for _ in range(2):
        with pytest.raises(FileNotFoundError):client.head_object(oss.HeadObjectRequest(bucket=oss_backup.BUCKET,key=key))
    assert session.calls==[] and not (root/'usage.json').exists()


def test_quota_cannot_follow_a_replaced_record_symlink(tmp_path,monkeypatch):
    root=tmp_path/'control';allowance(root,monkeypatch);session=Session();client=Client(service(session),root=root)
    original=root/'usage.json';saved=root/'original-usage.json';original.rename(saved);original.symlink_to(saved)
    with pytest.raises(ValueError,match='private_original'):
        client.head_object(oss.HeadObjectRequest(bucket=oss_backup.BUCKET,key='backups/20261104T000000Z-'+'a'*64+'/database.dump'))
    assert session.calls==[] and checkpoint.verified(saved)['requests']==0


def test_last_request_is_exclusive_and_unknown_calls_are_not_refunded(tmp_path,monkeypatch):
    root=tmp_path/'control';allowance(root,monkeypatch,requests=299);session=Session();client=Client(service(session),root=root)
    request=oss.HeadObjectRequest(bucket=oss_backup.BUCKET,key='backups/20261104T000000Z-'+'a'*64+'/database.dump')
    def send(_):
        try:client.head_object(request)
        except ValueError:return 'QUOTA_HOLD'
        except oss.exceptions.OperationError:return 'ONE_ORIGINAL_HTTP_404'
        raise AssertionError('synthetic empty object unexpectedly found')
    with ThreadPoolExecutor(max_workers=2) as workers:results=list(workers.map(send,range(2)))
    assert sorted(results)==['ONE_ORIGINAL_HTTP_404','QUOTA_HOLD']
    assert len(session.calls)==1 and checkpoint.verified(root/'usage.json')['requests']==300


def test_byte_cap_stops_get_and_lost_put_only_reconciles_original_head(tmp_path,monkeypatch):
    root=tmp_path/'full';allowance(root,monkeypatch,size=2*GIB);session=Session();client=Client(service(session),root=root)
    key='backups/20261104T000000Z-'+'a'*64+'/database.dump'
    with pytest.raises(ValueError,match='exhausted'):client.get_object(oss.GetObjectRequest(bucket=oss_backup.BUCKET,key=key))
    assert session.calls==[]
    root=tmp_path/'unknown';allowance(root,monkeypatch);objects=Objects(lose_ack=True);client=Client(objects,root=root)
    source=tmp_path/'original.dump';source.write_bytes(b'synthetic original PUT')
    with pytest.raises(TimeoutError):oss_backup.upload_file(client,source,key,tmp_path/'original.json')
    assert checkpoint.verified(root/'usage.json')['requests']==2
    assert oss_backup.upload_file(client,source,key,tmp_path/'original.json')=='HEAD_CONFIRMED'
    assert objects.puts==1 and checkpoint.verified(root/'usage.json')['requests']==4


def test_valid_old_usage_snapshot_cannot_roll_back_consumed_last_request(tmp_path,monkeypatch):
    root=tmp_path/'control';allowance(root,monkeypatch,requests=299);session=Session();client=Client(service(session),root=root)
    request=oss.HeadObjectRequest(bucket=oss_backup.BUCKET,key='backups/20261104T000000Z-'+'a'*64+'/database.dump')
    old=(root/'usage.json').read_bytes()
    with pytest.raises(oss.exceptions.OperationError):client.head_object(request)
    (root/'usage.json').write_bytes(old)
    with pytest.raises(ValueError,match='HOLD_original_OSS_intents_differ'):client.head_object(request)
    assert len(session.calls)==1 and (root/'intents/000300.json').exists()


def test_expiry_after_waiting_or_after_consumption_never_reaches_sdk(tmp_path,monkeypatch):
    request=oss.HeadObjectRequest(bucket=oss_backup.BUCKET,key='backups/20261104T000000Z-'+'a'*64+'/database.dump')
    root=tmp_path/'waiting';allowance(root,monkeypatch);session=Session();client=Client(service(session),root=root)
    lock=checkpoint.lock
    @contextmanager
    def expired_lock(path):
        with lock(path):
            monkeypatch.setenv('CJ_TRIAL_VALID_UNTIL','2026-11-03T00:00:00+00:00');yield
    with monkeypatch.context() as patch:
        patch.setattr(checkpoint,'lock',expired_lock)
        with pytest.raises(ValueError):client.head_object(request)
    assert session.calls==[] and checkpoint.verified(root/'usage.json')['requests']==0
    root=tmp_path/'consumed';allowance(root,monkeypatch);client=Client(service(session),root=root);atomic=checkpoint.atomic
    def expires_after_write(path,value,**kwargs):
        atomic(path,value,**kwargs)
        if path.name=='usage.json':monkeypatch.setenv('CJ_TRIAL_VALID_UNTIL','2026-11-03T00:00:00+00:00')
    monkeypatch.setattr(checkpoint,'atomic',expires_after_write)
    with pytest.raises(ValueError):client.head_object(request)
    assert session.calls==[] and checkpoint.verified(root/'usage.json')['requests']==1
    assert (root/'intents/000001.json').exists()


def test_runtime_recovery_signature_cannot_replace_root_policy_reader(tmp_path,monkeypatch):
    root=tmp_path/'control';allowance(root,monkeypatch);session=Session();client=Client(service(session),root=root)
    checkpoint.atomic(root/'authorization.json',dict(mode='free_confirmed',source='not JT approval'))
    original=checkpoint.verified(root/'usage.json')['authorization_sha256']
    with pytest.raises(oss.exceptions.OperationError):client.head_object(oss.HeadObjectRequest(bucket=oss_backup.BUCKET,key='backups/20261104T000000Z-'+'a'*64+'/database.dump'))
    assert checkpoint.verified(root/'usage.json')['authorization_sha256']==original


def test_recovery_signed_document_is_not_platform_root_authority(tmp_path,monkeypatch):
    root=tmp_path/'control';allowance(root,monkeypatch)
    runtime_file=root/'runtime-signed-policy.json'
    checkpoint.atomic(runtime_file,dict(mode='free_confirmed',source='not JT approval'))
    monkeypatch.setattr(oss_quota,'AUTHORITY',runtime_file)
    # Restore the actual filesystem reader at this boundary; runtime owns neither
    # a UID0/0644 authority file nor a root read-only authority mount.
    monkeypatch.setattr(oss_quota,'read_authority',READ_AUTHORITY)
    with pytest.raises(ValueError):oss_quota.policy()


RENEWED='2026-12-31T16:00:00+00:00'
HEAD=oss.HeadObjectRequest(bucket=oss_backup.BUCKET,key='backups/20261104T000000Z-'+'a'*64+'/database.dump')


def renew(monkeypatch,policy,**changes):
    renewed={**policy,'expires_at':RENEWED,**changes};monkeypatch.setattr(oss_quota,'read_authority',lambda:renewed)
    return hashlib.sha256(checkpoint.canonical(renewed)).hexdigest()


def clock(monkeypatch,when):
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return when
    monkeypatch.setattr(oss_quota,'datetime',Clock)


def test_approved_expiries_come_from_the_reviewed_deadline_config():
    assert oss_quota.APPROVED_EXPIRIES==('2026-11-30T16:00:00+00:00',RENEWED)


def test_renewal_changing_only_expiry_keeps_the_original_counter(tmp_path,monkeypatch):
    root=tmp_path/'control';policy=allowance(root,monkeypatch,requests=5,size=1000)
    original=checkpoint.verified(root/'usage.json')['authorization_sha256']
    renewed=renew(monkeypatch,policy);clock(monkeypatch,datetime(2026,12,15,tzinfo=timezone.utc))
    session=Session();client=Client(service(session),root=root)
    for expected in (6,7):
        with pytest.raises(oss.exceptions.OperationError):client.head_object(HEAD)
        state=checkpoint.verified(root/'usage.json')
        assert state['requests']==expected and state['reserved_bytes']==1000 and state['authorization_sha256']==renewed!=original
    assert checkpoint.verified(root/'intents/000005.json')['authorization_sha256']==original
    assert checkpoint.verified(root/'intents/000007.json')['authorization_sha256']==renewed and len(session.calls)==2


def test_renewal_does_not_reopen_an_exhausted_allowance(tmp_path,monkeypatch):
    root=tmp_path/'control';policy=allowance(root,monkeypatch,requests=300)
    renew(monkeypatch,policy);session=Session();client=Client(service(session),root=root)
    with pytest.raises(ValueError,match='OSS_allowance_exhausted'):client.head_object(HEAD)
    assert session.calls==[] and checkpoint.verified(root/'usage.json')['requests']==300


@pytest.mark.parametrize('changes',[dict(source='a different approval text'),dict(mode='free_confirmed',hold_limit_fen=0)])
def test_renewal_that_changes_anything_but_expiry_holds(tmp_path,monkeypatch,changes):
    root=tmp_path/'control';policy=allowance(root,monkeypatch,requests=5)
    renew(monkeypatch,policy,**changes);session=Session();client=Client(service(session),root=root)
    with pytest.raises(ValueError,match='original_OSS_usage_required'):client.head_object(HEAD)
    assert session.calls==[] and checkpoint.verified(root/'usage.json')['requests']==5


def test_unapproved_expiry_is_not_an_allowance(tmp_path,monkeypatch):
    root=tmp_path/'control';policy=allowance(root,monkeypatch)
    renew(monkeypatch,policy,expires_at='2027-01-31T16:00:00+00:00')
    with pytest.raises(ValueError,match='explicit_JT_OSS_allowance_required'):oss_quota.policy()


def test_reverting_to_the_older_authority_after_renewed_use_holds(tmp_path,monkeypatch):
    root=tmp_path/'control';policy=allowance(root,monkeypatch,requests=5)
    renew(monkeypatch,policy);session=Session();client=Client(service(session),root=root)
    with pytest.raises(oss.exceptions.OperationError):client.head_object(HEAD)
    monkeypatch.setattr(oss_quota,'read_authority',lambda:policy)
    with pytest.raises(ValueError,match='original_OSS_usage_required'):client.head_object(HEAD)
    assert len(session.calls)==1 and checkpoint.verified(root/'usage.json')['requests']==6


def test_old_expiry_still_closes_at_its_own_end_until_root_renews(tmp_path,monkeypatch):
    root=tmp_path/'control';policy=allowance(root,monkeypatch,requests=5)
    clock(monkeypatch,datetime(2026,11,30,16,tzinfo=timezone.utc))
    with pytest.raises(ValueError,match='OSS_allowance_expired'):oss_quota.policy()
    renew(monkeypatch,policy);assert oss_quota.policy()[0]['expires_at']==RENEWED
    clock(monkeypatch,datetime(2026,12,31,16,tzinfo=timezone.utc))
    with pytest.raises(ValueError,match='OSS_allowance_expired'):oss_quota.policy()
