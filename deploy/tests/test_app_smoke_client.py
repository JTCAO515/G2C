"""Private client transports credentials only over stdin to a fixed reader."""
from hashlib import sha256
import json
from types import SimpleNamespace

import pytest

from deploy.hk import app_smoke_client as client


def test_fixed_client_uses_issued_file_and_never_puts_token_in_argv_or_output(tmp_path,monkeypatch):
    q=dict(source='a'*40,image='sha256:'+'b'*64,plan_sha256='c'*64)
    path=tmp_path/'qualification.json';path.write_text(json.dumps(q));path.chmod(0o600)
    token=tmp_path/'token.jwt';token.write_text('fixture-secret-not-an-actual-token');token.chmod(0o600)
    config=dict(local_qualification=str(path),qualification_sha256=sha256(path.read_bytes()).hexdigest(),
        request_locale='zh',token_files={'zh':str(token)},token_format='jwt',
        remote_dispatcher='/srv/g2c-beta/probes/fixed-reader.py',server_qualification='/srv/g2c-beta/window/q.json',
        ssh_key_file='/private/issued-key-path',host='issued-test-host')
    calls=[]
    def run(args,**kwargs):
        calls.append(args);request=json.loads(kwargs['input'])
        assert request['request']['token']=='fixture-secret-not-an-actual-token'
        assert all('fixture-secret'not in a for a in args)
        value=dict(version='G2C-App-smoke-host-read.1',qualification_sha256=config['qualification_sha256'],
            actual_roles={r:dict(source=q['source'],image=q['image'])for r in('api','worker')},
            original=dict(version='G2C-App-smoke-read.1',status='READ'))
        return SimpleNamespace(returncode=0,stdout=json.dumps(value).encode(),stderr=b'')
    monkeypatch.setattr(client.subprocess,'run',run)
    value=client.call(config,dict(expected_source=q['source'],plan_sha256=q['plan_sha256'],kind='checkpoint'))
    assert len(calls)==1 and 'fixture-secret'not in json.dumps(value)
    path.write_text(path.read_text()+'\n')
    with pytest.raises(ValueError,match='qualification changed'):
        client.call(config,dict(expected_source=q['source'],plan_sha256=q['plan_sha256']))
    assert len(calls)==1
