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


def test_switch_on_without_apply_records_nothing(tmp_path,monkeypatch,capsys):
    monkeypatch.setenv('G2C_RELEASE_EVAL','1')
    gate,_=successful_release(tmp_path,monkeypatch)
    assert application_release.main([str(gate)])==0
    assert stages(capsys.readouterr().out)==['PREFLIGHT_PASS']
    assert not (tmp_path/application_release.RELEASE_EVAL_DIR).exists()


def test_record_is_private_and_never_left_half_written(tmp_path,monkeypatch,capsys):
    import stat
    now=datetime(2026,11,26,tzinfo=timezone.utc)
    folder=tmp_path/application_release.RELEASE_EVAL_DIR;folder.mkdir(mode=0o755)
    application_release.release_eval(tmp_path,SOURCE,PREVIOUS,now)
    assert stat.S_IMODE(folder.stat().st_mode)==0o700
    assert stat.S_IMODE((folder/(SOURCE+'.json')).stat().st_mode)==0o600
    capsys.readouterr()
    def broken(*args,**kwargs):raise OSError('disk full')
    monkeypatch.setattr(application_release.json,'dump',broken)
    application_release.release_eval(tmp_path,'c'*40,PREVIOUS,now)
    assert json.loads(capsys.readouterr().out)['reason']=='EVAL_RECORD_NOT_WRITTEN:OSError'
    assert not (folder/('c'*40+'.json')).exists()


def test_the_current_release_entry_calls_it_only_after_the_cutover_and_only_when_switched_on():
    """application_release_host.main (deploy/hk/README.md §3) is the entry releases use today."""
    import ast
    from deploy.hk import application_release_host as host
    assert host.release_eval is application_release.release_eval
    tree=ast.parse(Path(host.__file__).read_text(encoding='utf-8'))
    main=next(node for node in tree.body if isinstance(node,ast.FunctionDef)and node.name=='main')
    calls=[node for node in ast.walk(main)if isinstance(node,ast.Call)
           and getattr(node.func,'id',None)=='release_eval']
    assert len(calls)==1
    last,before=main.body[-1],main.body[-2]
    assert isinstance(before,ast.Try),'the switch must follow the cutover try/except, not sit inside it'
    assert all(isinstance(handler.body[-1],ast.Raise)for handler in before.handlers)
    assert isinstance(last,ast.If)and not last.orelse
    assert ast.unparse(last.test)=="os.environ.get('G2C_RELEASE_EVAL') == '1'"
    assert len(last.body)==1 and last.body[0].value is calls[0]
    assert ast.unparse(calls[0])=='release_eval(ROOT, source, previous_source, datetime.now(timezone.utc))'
    returns=[node for stmt in main.body[:-2] for node in ast.walk(stmt)if isinstance(node,ast.Return)]
    assert returns,'PREFLIGHT (no --apply) returns before the cutover and never reaches the switch'
