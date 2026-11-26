"""Long-code batches per channel and attribution (#1749)."""
from datetime import datetime,timezone
import hashlib
import json

import pytest

from deploy.hk import demo_accounts,demo_batches,demo_login

NOW=datetime(2026,11,27,tzinfo=timezone.utc)
EXPIRY='2026-12-31T23:00:00+08:00'


def private(tmp_path,name='out'):
    path=tmp_path/name;path.mkdir(mode=0o700);path.chmod(0o700);return path


def test_registered_channels_only_internal_test_issues_codes():
    channels=demo_batches.load_channels()
    assert list(channels)==['internal-test','ext-travel-content','ext-host-invite','ext-sourcing','ext-hotel']
    assert [c for c,v in channels.items() if v['issuing']]==['internal-test']
    assert {v['category'] for c,v in channels.items() if c!='internal-test'}=={'external'}


def test_generate_writes_private_codes_and_a_code_free_manifest(tmp_path):
    out=private(tmp_path)
    manifest=demo_batches.generate('internal-test',5,EXPIRY,out,now=NOW)
    codes=(out/('codes-'+manifest['batch']+'.txt')).read_text().split()
    stored=json.loads((out/('batch-'+manifest['batch']+'.json')).read_text())
    assert stored==manifest and manifest['channel']=='internal-test' and manifest['category']=='internal'
    assert len(codes)==5==len({demo_login.invitation_subject(c) for c in codes})
    for path in out.iterdir():assert oct(path.stat().st_mode&0o777)=='0o600'
    assert not any(code in json.dumps(manifest) for code in codes)
    for code,member in zip(codes,manifest['members']):
        assert demo_login.CODE.fullmatch(code) and demo_login.invitation_subject(code)==member['subject']
        assert hashlib.sha256(code.encode()).hexdigest()==member['digest']
        # Each member bootstraps as an external-safe long code (no --internal-short-code).
        demo_accounts.invitation_class(member['subject'],member['digest'],False)


@pytest.mark.parametrize('kwargs,error',[
    (dict(channel='ext-hotel'),'channel_not_issuing_codes'),
    (dict(channel='wechat-ads'),'registered_channel_required'),
    (dict(count=0),'bounded_batch_size_required'),(dict(count=51),'bounded_batch_size_required'),
    (dict(expires_at='2027-01-01T00:00:01+08:00'),'bounded_invitation_expiry_required'),
    (dict(expires_at='2026-11-26T00:00:00+00:00'),'bounded_invitation_expiry_required'),
    (dict(expires_at='2026-12-31T23:00:00'),'bounded_invitation_expiry_required'),
])
def test_generate_fails_closed(tmp_path,kwargs,error):
    values=dict(channel='internal-test',count=2,expires_at=EXPIRY,out=private(tmp_path));values.update(kwargs)
    with pytest.raises(ValueError,match=error):demo_batches.generate(now=NOW,**values)
    assert list(values['out'].iterdir())==[]


def test_short_or_malformed_codes_are_never_issued(tmp_path):
    for bad in ('G2C@07','D1-short.x'):
        with pytest.raises(ValueError,match='long_invite_code_required'):
            demo_batches.generate('internal-test',1,EXPIRY,private(tmp_path,bad.replace('@','-').replace('.','-')),now=NOW,code=lambda:bad)


def test_output_directory_must_be_private(tmp_path):
    out=tmp_path/'open';out.mkdir();out.chmod(0o755)
    with pytest.raises(ValueError,match='private_batch_directory_required'):demo_batches.generate('internal-test',1,EXPIRY,out,now=NOW)


def test_attribution_maps_subject_to_batch_and_channel(tmp_path):
    out=private(tmp_path);manifest=demo_batches.generate('internal-test',3,EXPIRY,out,now=NOW)
    subject=manifest['members'][1]['subject']
    assert demo_batches.attribute(out,subject)==(manifest['batch'],'internal-test','internal')
    assert demo_batches.attribute(out,demo_login.invitation_subject('G2C@07'))==(None,'internal-short-code','internal')
    assert demo_batches.attribute(out,'m4-synthetic-demo-000000000000') is None
    assert sorted(demo_batches.manifests(out))==sorted(m['subject'] for m in manifest['members'])


def test_tampered_or_duplicate_manifests_fail_closed(tmp_path):
    out=private(tmp_path);manifest=demo_batches.generate('internal-test',2,EXPIRY,out,now=NOW)
    path=out/('batch-'+manifest['batch']+'.json');path.chmod(0o600)
    data=json.loads(path.read_text());data['category']='external';path.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='demo_batch_manifest_invalid'):demo_batches.manifests(out)
    data['category']='internal';data['members'][0]['subject']=demo_login.invitation_subject('CJ_Tester@01')
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='demo_batch_manifest_invalid'):demo_batches.manifests(out)
    data['members'][0]['subject']=manifest['members'][0]['subject'];data['members'][1]['digest']=data['members'][0]['digest']
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='demo_batch_manifest_invalid'):demo_batches.manifests(out)
    data['members'][1]['digest']=manifest['members'][1]['digest'];data['channel']=['internal-test']
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='demo_batch_manifest_invalid'):demo_batches.manifests(out)


def test_release_host_role_check_uses_the_same_demo_bound():
    # The host release script runs outside the app image, so the bound is a literal kept equal here.
    from pathlib import Path
    import re
    from deploy.hk import configuration
    text=(Path(__file__).resolve().parents[1]/'hk/application_release_host.py').read_text()
    assert re.findall(r'not 1 <= reply\["demo_subjects"\] <= (\d+)',text)==[str(configuration.MAX_DEMO_SUBJECTS)]
