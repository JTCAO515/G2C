"""Readiness observation failures persist safe metadata and never permit sends."""
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import sys
import pytest
from deploy.hk import capture_status as client,status_remote as host


@pytest.fixture
def issued(tmp_path,monkeypatch):
    program=b'trusted status fixture'
    (tmp_path/'status_remote.py').write_bytes(program);(tmp_path/'status_remote.py').chmod(0o600)
    q=dict(version='G2C-HK-synthetic-qualification.1',line='L',state='ACTIVE',
        source='a'*40,image='sha256:'+'b'*64,schema=55,lease_id='local-fixture',incident_hold=False,
        status_remote_sha256=sha256(program).hexdigest(),server_qualification='/fixture/qualification.json',
        ssh_key_file='/fixture/no-key',host='fixture.invalid')
    path=tmp_path/'qualification.json';path.write_text(json.dumps(q));path.chmod(0o600)
    monkeypatch.setattr(client,'__file__',str(tmp_path/'capture-status.py'))
    monkeypatch.setattr(sys,'argv',['capture-status','L','--purpose','query'])
    return tmp_path,q


@pytest.mark.parametrize('kind',['nonzero','timeout','malformed_native','extra_private'])
def test_failed_observation_saves_exact_bound_metadata_without_raw_bytes(issued,monkeypatch,kind):
    root,q=issued
    data=dict(phase='proof',return_code=137,error_kind='native_exit',
        stdout_bytes=8,stdout_sha256=sha256(b'raw-body').hexdigest(),
        stderr_bytes=14,stderr_sha256=sha256(b'private-stderr').hexdigest())
    if kind=='extra_private':data['secret']='must-not-publish'
    if kind=='malformed_native':data['return_code']=False
    stderr=('G2C_STATUS_FAILURE '+json.dumps(data)+'\nprivate-stderr').encode()
    def failed(*args,**kwargs):
        assert kwargs['timeout']==90
        if kind=='timeout':raise subprocess.TimeoutExpired(args,90,output=b'raw-body',stderr=stderr)
        return SimpleNamespace(returncode=1,stdout=b'raw-body',stderr=stderr)
    monkeypatch.setattr(client.subprocess,'run',failed)
    with pytest.raises(SystemExit)as error:client.main()
    records=list((root/'readiness-failures').glob('*.json'));assert len(records)==1
    path,=records;raw=path.read_text();value=json.loads(raw)
    assert path.stat().st_mode&0o777==0o600
    assert (root/'readiness-failures').stat().st_mode&0o777==0o700
    assert value['business_dispatch_allowed_by_observed_conditions']is False
    assert value['expected_source']==q['source']and value['purpose']=='query'
    assert value['stderr_bytes']==len(stderr)and value['stderr_sha256']==sha256(stderr).hexdigest()
    assert value['return_code']is None if kind=='timeout'else value['return_code']==1
    assert 'raw-body'not in raw and'private-stderr'not in raw and'must-not-publish'not in raw
    assert 'raw-body'not in str(error.value)
    assert (value['native']is not None)is(kind=='nonzero')


@pytest.mark.parametrize('phase',['inspect_api_before','inspect_worker_before','proof','financial','inspect_api_after','inspect_worker_after'])
def test_native_command_retains_actual_nonzero_and_phase(monkeypatch,phase):
    monkeypatch.setattr(host.subprocess,'run',lambda*a,**k:SimpleNamespace(returncode=137,stdout=b'output',stderr=b'private'))
    with pytest.raises(host.StatusCommandError)as error:host.command(['fixture-command'],phase)
    value=error.value.data
    assert value['phase']==phase and value['return_code']==137
    assert value['stderr_sha256']==sha256(b'private').hexdigest()
    assert 'private'not in str(error.value)


def test_native_wait_timeout_does_not_invent_return_code(monkeypatch):
    def timeout(*args,**kwargs):raise subprocess.TimeoutExpired(args,45,output=b'partial',stderr=b'private')
    monkeypatch.setattr(host.subprocess,'run',timeout)
    with pytest.raises(host.StatusCommandError)as error:host.command(['fixture'],'financial')
    assert error.value.data['return_code']is None
    assert error.value.data['error_kind']=='native_wait_timeout'


def test_positive_query_still_never_authorizes_business(issued,monkeypatch,capsys):
    root,q=issued
    value=dict(version='G2C-HK-capture-status.1',purpose='query',status='READY_FOR_FIXED_WINDOW',
        source=q['source'],image=q['image'],schema=55,lease_id=q['lease_id'],
        observed_at=datetime.now(timezone.utc).isoformat(),business_dispatch_allowed_by_observed_conditions=False)
    monkeypatch.setattr(client.subprocess,'run',lambda*a,**k:SimpleNamespace(returncode=0,stdout=json.dumps(value).encode(),stderr=b''))
    client.main();assert json.loads(capsys.readouterr().out)==value
    assert not(root/'readiness-failures').exists()
