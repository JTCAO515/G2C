"""#1761: the optional post-release evaluation step; off by default, never changes the release."""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from deploy.hk import application_release

SOURCE='a'*40;PREVIOUS='b'*40


def stamp(value):return value.isoformat(timespec='microseconds')


def successful_release(tmp_path,monkeypatch):
    """A complete --apply cutover against fakes; returns the commands and stdout of main()."""
    now=datetime.now(timezone.utc)
    (tmp_path/'probes').mkdir();(tmp_path/'control/budget').mkdir(parents=True)
    (tmp_path/'quota-self-service-20261112').mkdir()
    (tmp_path/'control/budget/adoption.json').write_text(json.dumps({'state':'ADOPTED_SUBLIMITS_1'}))
    policy={'required_source_hashes':{'backend/usage/cj_usage/sublimits.py':'c'*64}}
    (tmp_path/'quota-self-service-20261112/app-release-policy.json').write_text(json.dumps(policy))
    (tmp_path/'compose.env').write_text('CJ_BETA_IMAGE=g2c-beta:'+PREVIOUS+'\n')
    gate=tmp_path/'gate.json';gate.write_text(json.dumps(dict(source=SOURCE,previous_source=PREVIOUS,
        image_id='new-image',previous_image_id='old-image',pr_number=1,review_approved_head=SOURCE,
        source_bytes_equal=True,imported_source_bytes_equal=True,
        starts_at=stamp(now-timedelta(minutes=1)),ends_at=stamp(now+timedelta(minutes=30)))))
    monkeypatch.setattr(application_release,'Path',lambda value:tmp_path if value=='/srv/g2c-beta'else Path(value))
    for name in ('verify_release_ci','verify_release_review','verify_release_range'):
        monkeypatch.setattr(application_release,name,lambda *unused:None)
    commands=[];state={'cut':False}
    def run(args,**unused):
        commands.append(args)
        if args[:2]==['docker','inspect']:
            name=args[-1]
            if name=='g2c-beta:'+SOURCE:
                result=dict(Id='new-image',Architecture='amd64',Config={'Labels':{'org.opencontainers.image.revision':SOURCE}})
            else:
                new=state['cut'];revision=SOURCE if new else PREVIOUS
                result=dict(Id='container',Image='new-image'if new else 'old-image',
                    Config={'Labels':{'org.opencontainers.image.revision':revision},'Cmd':['worker']},
                    State={'Running':True,'Health':{'Status':'healthy'}})
            result=[result]
        elif args[:2]==['docker','run']:result=policy['required_source_hashes']
        elif '/export.py'in args:
            result=dict(global_pending=0,global_active=0,background_states={},memory_states={},
                ledger={'count':10,'sha256':'d'*64})
        elif args[-4:-1]==['stop','-t','20']:result={}
        elif args[-5:]==['up','-d','--no-deps','api','worker']:state['cut']=True;result={}
        else:raise AssertionError('unexpected operation '+repr(args))
        return SimpleNamespace(stdout=json.dumps(result).encode())
    monkeypatch.setattr(application_release.subprocess,'run',run)
    return gate,commands


def stages(out):
    return [json.loads(line)['stage']for line in out.splitlines()if line.startswith('{')]


def test_default_release_is_unchanged_and_writes_no_eval_record(tmp_path,monkeypatch,capsys):
    monkeypatch.delenv('G2C_RELEASE_EVAL',raising=False)
    gate,commands=successful_release(tmp_path,monkeypatch)
    application_release.main([str(gate),'--apply'])
    assert stages(capsys.readouterr().out)==['PREFLIGHT_PASS','CUTOVER_PASS']
    assert not (tmp_path/application_release.RELEASE_EVAL_DIR).exists()
    assert (tmp_path/'compose.env').read_text()=='CJ_BETA_IMAGE=g2c-beta:'+SOURCE+'\n'


@pytest.mark.parametrize('value',['0','','true','yes','1 '])
def test_only_the_exact_switch_value_turns_the_step_on(tmp_path,monkeypatch,capsys,value):
    monkeypatch.setenv('G2C_RELEASE_EVAL',value)
    gate,_=successful_release(tmp_path,monkeypatch)
    application_release.main([str(gate),'--apply'])
    assert stages(capsys.readouterr().out)==['PREFLIGHT_PASS','CUTOVER_PASS']
    assert not (tmp_path/application_release.RELEASE_EVAL_DIR).exists()


def test_switch_on_records_unrun_after_the_cutover_with_the_same_commands(tmp_path,monkeypatch,capsys):
    monkeypatch.delenv('G2C_RELEASE_EVAL',raising=False)
    off_root=tmp_path/'off';off_root.mkdir()
    gate,off_commands=successful_release(off_root,monkeypatch)
    application_release.main([str(gate),'--apply'])
    capsys.readouterr()
    on_root=tmp_path/'on';on_root.mkdir()
    monkeypatch.setenv('G2C_RELEASE_EVAL','1')
    gate,on_commands=successful_release(on_root,monkeypatch)
    application_release.main([str(gate),'--apply'])
    lines=[json.loads(line)for line in capsys.readouterr().out.splitlines()if line.startswith('{')]
    assert [line['stage']for line in lines]==['PREFLIGHT_PASS','CUTOVER_PASS','RELEASE_EVAL']
    normalize=lambda commands:[[str(arg).replace(str(root),'<root>')for arg in command]
                               for command,root in commands]
    assert normalize([(c,off_root)for c in off_commands])==normalize([(c,on_root)for c in on_commands])
    record=json.loads((on_root/application_release.RELEASE_EVAL_DIR/(SOURCE+'.json')).read_text())
    assert record['status']=='UNRUN' and record['reason']=='EVAL_SENDER_NOT_CONNECTED'
    assert (record['source'],record['previous_source'])==(SOURCE,PREVIOUS)
    assert lines[-1]['status']=='UNRUN'


def test_a_record_problem_is_reported_not_raised(tmp_path,capsys):
    now=datetime(2026,11,26,tzinfo=timezone.utc)
    application_release.release_eval(tmp_path,SOURCE,PREVIOUS,now)
    application_release.release_eval(tmp_path,SOURCE,PREVIOUS,now)  # same source again: record exists
    first,second=[json.loads(line)for line in capsys.readouterr().out.splitlines()]
    assert first['status']=='UNRUN'
    assert second['status']=='UNKNOWN' and second['reason']=='EVAL_RECORD_NOT_WRITTEN:FileExistsError'
    blocked=tmp_path/'file';blocked.write_text('')
    application_release.release_eval(blocked,SOURCE,PREVIOUS,now)  # cannot create the folder
    assert json.loads(capsys.readouterr().out)['status']=='UNKNOWN'
