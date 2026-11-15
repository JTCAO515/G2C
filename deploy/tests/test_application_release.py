"""Idle deployment bounds and original API recovery; no cloud action."""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from deploy.hk.application_release import require_release_window
from deploy.hk import application_release


def stamp(value):return value.isoformat(timespec='microseconds')


@pytest.mark.parametrize('hour',[0,3,8,9,11,14,17,21,23])
def test_idle_release_has_no_fixed_hour_but_keeps_its_exact_lease(hour):
    start=datetime(2026,11,13,hour,tzinfo=timezone.utc);end=start+timedelta(minutes=30)
    require_release_window(stamp(start),stamp(end),start)
    require_release_window(stamp(start),stamp(end),end-timedelta(microseconds=1))
    for now in (start-timedelta(microseconds=1),end):
        with pytest.raises(ValueError):require_release_window(stamp(start),stamp(end),now)


def test_expired_naive_reversed_or_unbounded_lease_is_refused():
    start=datetime(2026,11,13,tzinfo=timezone.utc)
    for end in (start,start-timedelta(seconds=1),start+timedelta(seconds=7201)):
        with pytest.raises(ValueError):require_release_window(stamp(start),stamp(end),start)
    with pytest.raises(ValueError):require_release_window(stamp(start),stamp(start+timedelta(hours=1)),start.replace(tzinfo=None))


def test_arrival_after_ingress_close_recovers_only_api_without_old_dependencies(tmp_path,monkeypatch):
    source='a'*40;previous='b'*40;now=datetime.now(timezone.utc)
    (tmp_path/'probes').mkdir();(tmp_path/'control/budget').mkdir(parents=True)
    (tmp_path/'quota-self-service-20261112').mkdir()
    control=tmp_path/'control/budget/adoption.json'
    control.write_text(json.dumps({'state':'ADOPTED_SUBLIMITS_1'}))
    policy={'required_source_hashes':{'backend/usage/cj_usage/sublimits.py':'c'*64}}
    (tmp_path/'quota-self-service-20261112/app-release-policy.json').write_text(json.dumps(policy))
    environment=tmp_path/'compose.env';environment.write_text('CJ_BETA_IMAGE=g2c-beta:'+previous+'\n')
    original_environment=environment.read_bytes();original_control=control.read_bytes()
    gate=tmp_path/'gate.json';gate.write_text(json.dumps(dict(source=source,previous_source=previous,
        image_id='new-image',previous_image_id='old-image',pr_number=1,ci_all_green=True,
        review_approved_head=source,source_bytes_equal=True,imported_source_bytes_equal=True,
        checks=[dict(name=str(i),state='SUCCESS')for i in range(13)],
        starts_at=stamp(now-timedelta(minutes=1)),ends_at=stamp(now+timedelta(minutes=30)))))
    monkeypatch.setattr(application_release,'Path',lambda value:tmp_path if value=='/srv/g2c-beta'else Path(value))
    class Reply:
        def __init__(self,value):self.value=value
        def __enter__(self):return self
        def __exit__(self,*unused):pass
        def read(self):return json.dumps(self.value).encode()
    def github(request,timeout):
        if '/pulls/'in request.full_url:return Reply({'merged':True,'head':{'sha':source}})
        if request.full_url.endswith('/check-runs'):return Reply({'check_runs':[{'status':'completed','conclusion':'success'}]})
        return Reply({'state':'success'})
    monkeypatch.setattr(application_release,'urlopen',github)
    commands=[];proofs=0;api_running=True
    def run(args,**unused):
        nonlocal proofs,api_running
        commands.append(args)
        if args[:2]==['docker','inspect']:
            name=args[-1];candidate=name=='g2c-beta:'+source
            result=[dict(Id='new-image'if candidate else 'container',Architecture='amd64',
                Image='old-image',Config={'Labels':{'org.opencontainers.image.revision':source if candidate else previous}},
                State={'Running':api_running if name=='g2c-beta-api-1'else True})]
        elif args[:2]==['docker','run']:result=policy['required_source_hashes']
        elif '/export.py'in args:
            proofs+=1
            result=dict(global_pending=0 if proofs==1 else 1,global_active=0,
                background_states={},memory_states={},ledger={'count':10,'sha256':'d'*64})
        elif args[-4:]==['stop','-t','20','api']:
            api_running=False;result={}
        elif args[-4:]==['up','-d','--no-deps','api']:
            api_running=True;result={}
        else:raise AssertionError('unexpected operation '+repr(args))
        return SimpleNamespace(stdout=json.dumps(result).encode())
    monkeypatch.setattr(application_release.subprocess,'run',run)
    with pytest.raises(AssertionError,match='original arrived during ingress close'):
        application_release.main([str(gate),'--apply'])
    assert api_running and proofs==2
    assert commands[-1][-4:]==['up','-d','--no-deps','api']
    assert all('migrate'not in command or '/export.py'in command for command in commands)
    assert environment.read_bytes()==original_environment and control.read_bytes()==original_control
