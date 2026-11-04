import base64
from datetime import datetime,timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from cj_usage.authorization_budget import AuthorizationBudget,BudgetUnknown,HK_PRODUCER
from deploy.hk import configuration,checkpoint,oss_backup
from scripts.m4_budget_transfer import seal,adopt


class Clock(datetime):
    @classmethod
    def now(cls,tz=None):return datetime(2026,11,4,tzinfo=timezone.utc)


def activate(monkeypatch):
    monkeypatch.setattr(configuration,'datetime',Clock)
    for k,v in dict(CJ_ENV='local',CJ_DEPLOY_TARGET='hk-beta',CJ_M4_SYNTHETIC_ONLY='1',CJ_TRIAL_VALID_UNTIL='2026-11-20T00:00:00+00:00').items():monkeypatch.setenv(k,v)


def test_trial_and_explicit_environment_fail_closed(monkeypatch):
    activate(monkeypatch);configuration.authorization()
    monkeypatch.setenv('CJ_TRIAL_VALID_UNTIL','2026-11-03T00:00:00+00:00')
    with pytest.raises(ValueError):configuration.authorization()
    monkeypatch.setenv('CJ_TRIAL_VALID_UNTIL','2026-11-20T00:00:00+00:00');monkeypatch.setenv('CJ_ENV','production')
    with pytest.raises(ValueError):configuration.authorization()


def test_shared_budget_transfer_keeps_unknown_and_fences_stale_instances(tmp_path,monkeypatch):
    clock=lambda:Clock.now(timezone.utc)
    original=AuthorizationBudget(tmp_path/'mac',clock=clock)
    stale=AuthorizationBudget(tmp_path/'mac',clock=clock)
    original.begin('unknown-original','model',b'synthetic')
    original.begin('weather-original','weather',b'synthetic');original.finish('weather-original',{'status':'RECEIVED'})
    before=original.inspect();destination=tmp_path/'transferred.sqlite'
    sha=seal(original.path,destination)
    for budget in (original,stale,AuthorizationBudget(tmp_path/'mac',clock=clock)):
        with pytest.raises(BudgetUnknown):budget.begin('new-mac','model',b'synthetic')
        with pytest.raises(BudgetUnknown):budget.finish('unknown-original',{'status':'RECEIVED'})
        assert budget.inspect()==before
    activate(monkeypatch);monkeypatch.setenv('CJ_M4_BUDGET_PRODUCER',HK_PRODUCER)
    with pytest.raises(ValueError):adopt(destination,'0'*64)
    adopt(destination,sha)
    root=tmp_path/'hk';root.mkdir();destination.rename(root/'m4-outflows.sqlite')
    moved=AuthorizationBudget(root,clock=clock);assert moved.inspect()==before
    with pytest.raises(BudgetUnknown):moved.begin('unknown-original','model',b'synthetic')
    moved.begin('new-hk','model',b'synthetic')
    assert len(moved.inspect())==3 and original.inspect()==before


class Objects:
    def __init__(self,*,lose_ack=False):self.objects={};self.puts=0;self.lose_ack=lose_ack
    def head_object(self,request):
        if request.key not in self.objects:
            raise oss_backup.oss.exceptions.ServiceError(status_code=404,code='NoSuchKey',request_id='synthetic',message='missing',ec='',timestamp='',request_target='synthetic')
        return self.objects[request.key]
    def put_object(self,request):
        self.puts+=1
        assert request.bucket==oss_backup.BUCKET and request.acl=='private' and request.forbid_overwrite
        assert request.server_side_encryption=='AES256'
        data=request.body.read();assert len(data)==request.content_length
        self.objects[request.key]=SimpleNamespace(content_length=len(data),metadata=request.metadata,server_side_encryption='AES256')
        if self.lose_ack:raise TimeoutError('synthetic response lost after write')


def test_unknown_put_checks_original_head_and_never_reissues(tmp_path,monkeypatch):
    activate(monkeypatch);path=tmp_path/'database.dump';path.write_bytes(b'synthetic checkpoint')
    key='backups/20261104T000000Z-'+'a'*64+'/database.dump';journal=tmp_path/'intent.json';objects=Objects(lose_ack=True)
    with pytest.raises(TimeoutError):oss_backup.upload_file(objects,path,key,journal)
    assert json.loads(journal.read_bytes())['state']=='INTENT'
    assert oss_backup.upload_file(objects,path,key,journal)=='HEAD_CONFIRMED' and objects.puts==1
    objects.objects.clear()
    with pytest.raises(ValueError,match='unknown_no_resend'):oss_backup.upload_file(objects,path,key,journal)
    assert objects.puts==1


def test_backup_existing_object_mismatch_or_prefix_is_rejected(tmp_path,monkeypatch):
    activate(monkeypatch);path=tmp_path/'manifest.json';path.write_bytes(b'synthetic')
    objects=Objects();key='backups/20261104T000000Z-'+'a'*64+'/manifest.json'
    objects.objects[key]=SimpleNamespace(content_length=9,metadata={'sha256':'wrong'},server_side_encryption='AES256')
    with pytest.raises(ValueError):oss_backup.upload_file(objects,path,key,tmp_path/'journal.json')
    with pytest.raises(ValueError):oss_backup.upload_file(objects,path,'other-prefix/file',tmp_path/'journal.json')
    assert objects.puts==0


def test_checkpoint_signature_tamper_wrong_key_and_public_release(tmp_path,monkeypatch):
    activate(monkeypatch);key=Ed25519PrivateKey.generate()
    private=key.private_bytes(serialization.Encoding.Raw,serialization.PrivateFormat.Raw,serialization.NoEncryption())
    public=key.public_key().public_bytes(serialization.Encoding.Raw,serialization.PublicFormat.Raw)
    monkeypatch.setenv('CJ_BETA_RECOVERY_PRIVATE_B64',base64.b64encode(private).decode())
    monkeypatch.setenv('CJ_BETA_RECOVERY_PUBLIC_B64',base64.b64encode(public).decode())
    path=tmp_path/'release.json';checkpoint.atomic(path,{'version':'synthetic'},public=True)
    assert path.stat().st_mode&0o777==0o644 and checkpoint.verified(path)=={'version':'synthetic'}
    value=json.loads(path.read_bytes());value['value']['version']='tampered';path.write_text(json.dumps(value))
    with pytest.raises(ValueError):checkpoint.verified(path)
    checkpoint.atomic(path,{'version':'synthetic'})
    monkeypatch.setenv('CJ_BETA_RECOVERY_PUBLIC_B64',base64.b64encode(bytes(32)).decode())
    with pytest.raises(ValueError):checkpoint.verified(path)
