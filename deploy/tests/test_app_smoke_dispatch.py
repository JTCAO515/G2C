"""Live-host dispatcher fixtures: metadata only, no SSH or native dispatch."""
import hashlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from deploy.hk import app_smoke_dispatch as host


def fixture(tmp_path,monkeypatch):
    root=tmp_path/'srv';probes=root/'probes';probes.mkdir(parents=True,mode=0o700)
    for name in('application-deploy.lock','qualified-reader.lock'):
        p=probes/name;p.touch(mode=0o600)
    monkeypatch.setattr(host,'ROOT',root)
    q=dict(version='G2C-App-smoke-live.1',state='ACTIVE',source='a'*40,image='sha256:'+'b'*64,
        schema=55,plan_sha256='c'*64,reader_sha256='d'*64,window_id='synthetic-window',
        api_manifest='/run/app-smoke/api.json',worker_manifest='/run/app-smoke/policy.json',
        mounts={'api':{},'worker':{}})
    path=root/'qualification.json';path.write_text(json.dumps(q));path.chmod(0o600)
    envelope=dict(qualification_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),request=dict(
        expected_source=q['source'],plan_sha256=q['plan_sha256'],kind='checkpoint',token='synthetic-secret-not-log'))
    calls=[]
    def output(args,**kwargs):
        calls.append(args)
        if args[:2]==['docker','inspect']:
            role='api'if args[-1].endswith('api-1')else'worker'
            command=['api','--app-smoke-api-manifest',q['api_manifest']]if role=='api'else[
                'worker','--app-smoke-manifest',q['worker_manifest']]
            return json.dumps([dict(Id=role+'-id',Image=q['image'],Config=dict(Cmd=command,
                Labels={'org.opencontainers.image.revision':q['source']}),State=dict(Running=True,Health=dict(Status='healthy')),
                Mounts=[])]).encode()
        return(q['reader_sha256']+'\n').encode()
    monkeypatch.setattr(host.subprocess,'check_output',output)
    def run(args,**kwargs):
        calls.append(args)
        assert b'synthetic-secret-not-log'in kwargs['input']
        assert all('synthetic-secret'not in str(x)for x in args)
        return SimpleNamespace(returncode=0,stdout=json.dumps(dict(version='G2C-App-smoke-read.1',status='READ')).encode(),stderr=b'')
    monkeypatch.setattr(host.subprocess,'run',run)
    return root,path,envelope,calls


def test_success_checks_live_roles_serializes_and_clears_only_own_intent(tmp_path,monkeypatch):
    root,path,envelope,calls=fixture(tmp_path,monkeypatch)
    result=host.run(path,envelope)
    assert result['original']['status']=='READ'
    assert result['actual_roles']['api']['command']==['api','--app-smoke-api-manifest','/run/app-smoke/api.json']
    assert not(root/'probes/qualified-reader.inflight.json').exists()
    assert 'synthetic-secret-not-log'not in json.dumps(result)


def test_changed_qualification_does_not_start_a_native_reader(tmp_path,monkeypatch):
    root,path,envelope,calls=fixture(tmp_path,monkeypatch)
    path.write_text(path.read_text()+'\n')
    with pytest.raises(ValueError,match='qualification'):host.run(path,envelope)
    assert calls==[]


def test_prior_unknown_marker_never_starts_replacement_or_resets_marker(tmp_path,monkeypatch):
    root,path,envelope,calls=fixture(tmp_path,monkeypatch)
    p=root/'probes/qualified-reader.inflight.json';p.write_bytes(b'prior uncertain reader');p.chmod(0o600)
    with pytest.raises(ValueError,match='previous native reader'):host.run(path,envelope)
    assert p.read_bytes()==b'prior uncertain reader'
    assert not any(len(x)>4 and x[1:3]==['exec','-i']for x in calls)


@pytest.mark.parametrize('failure',['timeout','nonzero'])
def test_native_failure_retains_original_marker_and_sanitized_diagnostic(tmp_path,monkeypatch,failure,capsys):
    root,path,envelope,calls=fixture(tmp_path,monkeypatch)
    def fail(args,**kwargs):
        if failure=='timeout':raise subprocess.TimeoutExpired(args,60)
        return SimpleNamespace(returncode=1,stdout=b'',stderr=b'synthetic-secret-not-log')
    monkeypatch.setattr(host.subprocess,'run',fail)
    with pytest.raises(ValueError,match='retained'):host.run(path,envelope)
    assert(root/'probes/qualified-reader.inflight.json').exists()
    assert 'synthetic-secret-not-log'not in capsys.readouterr().err
