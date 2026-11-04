"""Signed local allowance + locked SDK over fake HTTP; no cloud or real keys."""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib

import alibabacloud_oss_v2 as oss
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from deploy.hk import checkpoint,oss_backup
from deploy.hk.oss_quota import Client,GIB
from test_hk_boundaries import activate,Objects
from test_oss_sdk_contract import Session,service


def allowance(root,monkeypatch,*,mode='paid_capped',requests=0,size=0):
    activate(monkeypatch);key=Ed25519PrivateKey.generate();root.mkdir(mode=0o700)
    monkeypatch.setenv('CJ_BETA_RECOVERY_PRIVATE_B64',base64.b64encode(key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption())).decode())
    monkeypatch.setenv('CJ_BETA_RECOVERY_PUBLIC_B64',base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode())
    policy=dict(version='g2c-beta-oss-authorization.1',mode=mode,source='synthetic offline fixture; not JT approval',request_limit=300,byte_limit=2*GIB,
        hold_limit_fen=1000 if mode=='paid_capped' else 0,expires_at='2026-11-30T16:00:00+00:00')
    checkpoint.atomic(root/'authorization.json',policy)
    checkpoint.atomic(root/'usage.json',dict(version='g2c-beta-oss-usage.1',authorization_sha256=hashlib.sha256(checkpoint.canonical(policy)).hexdigest(),requests=requests,reserved_bytes=size))


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
    original=root/'authorization.json';saved=root/'original-authorization.json';original.rename(saved);original.symlink_to(saved)
    with pytest.raises(ValueError,match='private_original'):
        client.head_object(oss.HeadObjectRequest(bucket=oss_backup.BUCKET,key='backups/20261104T000000Z-'+'a'*64+'/database.dump'))
    assert session.calls==[] and checkpoint.verified(root/'usage.json')['requests']==0


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
