"""Idle deployment bounds and original API recovery; no cloud action."""
from datetime import datetime,timedelta,timezone
from hashlib import sha256
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


@pytest.mark.parametrize('returning_to_previous_source',[False,True])
def test_arrival_after_ingress_close_recovers_only_api_without_old_dependencies(tmp_path,monkeypatch,returning_to_previous_source):
    source='a'*40;previous='b'*40;now=datetime.now(timezone.utc)
    (tmp_path/'probes').mkdir();(tmp_path/'control/budget').mkdir(parents=True)
    (tmp_path/'quota-self-service-20261112').mkdir()
    control=tmp_path/'control/budget/adoption.json'
    control.write_text(json.dumps({'state':'ADOPTED_SUBLIMITS_1'}))
    policy={'required_source_hashes':{'backend/usage/cj_usage/sublimits.py':'c'*64}}
    (tmp_path/'quota-self-service-20261112/app-release-policy.json').write_text(json.dumps(policy))
    environment=tmp_path/'compose.env';environment.write_text('CJ_BETA_IMAGE=g2c-beta:'+previous+'\n')
    original_environment=environment.read_bytes();original_control=control.read_bytes()
    legacy_backup=tmp_path/'probes'/('compose.before-app-'+source+'.env')
    if returning_to_previous_source:legacy_backup.write_bytes(b'original prior deployment backup\n')
    gate=tmp_path/'gate.json';gate.write_text(json.dumps(dict(source=source,previous_source=previous,
        image_id='new-image',previous_image_id='old-image',pr_number=1,ci_all_green=True,
        review_approved_head=source,review_comment=1,source_bytes_equal=True,imported_source_bytes_equal=True,
        checks=[dict(name=str(i),state='SUCCESS')for i in range(13)],
        starts_at=stamp(now-timedelta(minutes=1)),ends_at=stamp(now+timedelta(minutes=30)))))
    monkeypatch.setattr(application_release,'Path',lambda value:tmp_path if value=='/srv/g2c-beta'else Path(value))
    monkeypatch.setattr(application_release, 'verify_release_ci', lambda github, sha: None)
    monkeypatch.setattr(application_release, 'verify_release_review', lambda github, sha, supplied: None)
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
    backup=tmp_path/'probes'/('compose.before-app-'+source+'-'+sha256(gate.read_bytes()).hexdigest()+'.env')
    assert backup.read_bytes()==original_environment
    if returning_to_previous_source:assert legacy_backup.read_bytes()==b'original prior deployment backup\n'
    # A new lease can return to an old source, but the identical lease cannot
    # replay its cutover after an uncertain or failed first execution.
    proofs=0
    stops=sum(command[-4:]==['stop','-t','20','api']for command in commands)
    with pytest.raises(FileExistsError):application_release.main([str(gate),'--apply'])
    assert sum(command[-4:]==['stop','-t','20','api']for command in commands)==stops

SOURCE = 'a' * 40
REVIEWED = 'b' * 40


@pytest.fixture
def workflow_evidence():
    repo = {'full_name': application_release.REPOSITORY}
    ci = dict(id=1, path=application_release.CI_PATH, event='push', head_branch='main',
              head_sha=SOURCE, status='completed', conclusion='success',
              repository=repo, head_repository=repo)
    monitor = dict(ci, id=2, path='.github/workflows/hk-readiness.yml', event='schedule',
                   conclusion='skipped')
    jobs = [dict(id=i + 10, name=name, run_id=1, head_sha=SOURCE, status='completed',
                 conclusion='success', steps=[{'conclusion': 'success'}])
            for i, name in enumerate(sorted(application_release.CI_JOBS))]
    return dict(workflow_runs=[ci, monitor],
                check_runs=[*jobs, dict(id=3, name='observe', head_sha=SOURCE, conclusion='skipped')],
                jobs=jobs, state='success')


def github_fixture(evidence):
    def fetch(path):
        if path.endswith('/status'):
            return {'state': evidence['state']}
        key = 'workflow_runs' if path.startswith('actions/runs?') else (
            'check_runs' if '/check-runs?' in path else 'jobs')
        rows = evidence[key]
        return {'total_count': len(rows), key: rows}
    return fetch


def test_release_ci_accepts_skipped_monitor_with_all_required_jobs(workflow_evidence):
    application_release.verify_release_ci(github_fixture(workflow_evidence), SOURCE)


@pytest.mark.parametrize('mutation', [
    'missing_ci', 'wrong_ci_path', 'ci_wrong_event', 'missing_job', 'skipped_job',
    'empty_required_job', 'unrelated_failed_job', 'unrelated_cancelled_run', 'commit_status_failure',
])
def test_release_ci_rejects_missing_evidence_and_explicit_failures(workflow_evidence, mutation):
    evidence = workflow_evidence
    ci, monitor = evidence['workflow_runs']
    jobs = evidence['jobs']
    if mutation == 'missing_ci':
        evidence['workflow_runs'].remove(ci)
    elif mutation == 'wrong_ci_path':
        ci['path'] = monitor['path']
    elif mutation == 'ci_wrong_event':
        ci['event'] = 'pull_request'
    elif mutation == 'missing_job':
        jobs.pop()
    elif mutation == 'skipped_job':
        jobs[0]['conclusion'] = 'skipped'
    elif mutation == 'empty_required_job':
        jobs[0]['steps'] = []
    elif mutation == 'unrelated_failed_job':
        evidence['check_runs'][-1]['conclusion'] = 'failure'
    elif mutation == 'unrelated_cancelled_run':
        monitor['conclusion'] = 'cancelled'
    elif mutation == 'commit_status_failure':
        evidence['state'] = 'failure'
    with pytest.raises(ValueError):
        application_release.verify_release_ci(github_fixture(evidence), SOURCE)


@pytest.mark.parametrize('approval, withdrawn', [(REVIEWED, False), (SOURCE, False), (REVIEWED, True)])
def test_release_review_requires_current_approval_on_reviewed_head(approval, withdrawn):
    gate = dict(pr_number=1174, review_comment=42, review_approved_head=REVIEWED)
    comments = [dict(id=42, author_association='OWNER', body=f'Review: APPROVE {approval}\nDetails')]
    if withdrawn:
        comments.append(dict(id=43, author_association='OWNER', body=f'Review: REQUEST CHANGES {REVIEWED}'))
    evidence = {
        'pulls/1174': dict(merged=True, head={'sha': REVIEWED}, merge_commit_sha=SOURCE),
        'issues/1174/comments?per_page=100&page=1': comments,
    }
    if approval == REVIEWED and not withdrawn:
        application_release.verify_release_review(evidence.__getitem__, SOURCE, gate)
    else:
        with pytest.raises(ValueError, match='R approval'):
            application_release.verify_release_review(evidence.__getitem__, SOURCE, gate)
