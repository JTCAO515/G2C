"""Idle deployment bounds and original API recovery; no cloud action."""
from datetime import datetime,timedelta,timezone
from hashlib import sha256
import json
from pathlib import Path
import re
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
    evidence_order=[]
    flock=application_release.fcntl.flock
    def record_flock(fd, operation):
        evidence_order.append('lock')
        return flock(fd, operation)
    monkeypatch.setattr(application_release.fcntl, 'flock', record_flock)
    monkeypatch.setattr(application_release, 'verify_release_ci', lambda github, sha: evidence_order.append('ci'))
    monkeypatch.setattr(application_release, 'verify_release_review',
                        lambda github, sha, supplied: evidence_order.append('review'))
    monkeypatch.setattr(application_release, 'verify_release_range',
                        lambda github, live, sha, verified: evidence_order.append(
                            ('range', live, sha, frozenset(verified))))
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
    assert evidence_order==['ci', 'review', ('range', previous, source, frozenset({(1, source)})), 'lock']
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
                   conclusion='skipped', check_suite_id=502)
    lint = dict(ci, id=4, path='.github/workflows/pr-lint.yml', event='push', conclusion='success',
                check_suite_id=504)
    jobs = [dict(id=i + 10, name=name, run_id=1, head_sha=SOURCE, status='completed',
                 conclusion='success', steps=[{'conclusion': 'success'}])
            for i, name in enumerate(sorted(application_release.CI_JOBS))]
    return dict(workflow_runs=[ci, monitor, lint],
                check_runs=[*jobs, dict(id=3, name='observe', head_sha=SOURCE, conclusion='skipped', check_suite={'id': 502}),
                            dict(id=5, name='lint', head_sha=SOURCE, conclusion='success', check_suite={'id': 504})],
                jobs=jobs, state='success')


def github_fixture(evidence):
    def fetch(path):
        if path.endswith('/status'):
            return {'state': evidence['state']}
        if '/attempts/' in path:
            rows = evidence['attempts'][int(path.split('/attempts/')[1].split('/')[0])]
            return {'total_count': len(rows), 'jobs': rows}
        key = 'workflow_runs' if path.startswith('actions/runs?') else (
            'check_runs' if '/check-runs?' in path else 'jobs')
        rows = evidence[key]
        return {'total_count': len(rows), key: rows}
    return fetch


def rerun_after(workflow_evidence, **earlier):
    # Attempt 1 left one job record (check run id 99); attempt 2 is the green inventory.
    ci = workflow_evidence['workflow_runs'][0]
    ci['run_attempt'] = 2
    job = dict(id=99, name='swift', run_id=1, run_attempt=1, head_sha=SOURCE, status='completed',
               conclusion='cancelled', runner_name='', steps=[])
    job.update(earlier)
    workflow_evidence['attempts'] = {1: [job]}
    workflow_evidence['check_runs'].append(dict(id=99, name='swift', head_sha=SOURCE,
                                                conclusion=job['conclusion']))
    return workflow_evidence


@pytest.mark.parametrize('conclusion', ['cancelled', 'failure'])
def test_release_ci_accepts_an_earlier_attempt_that_never_got_a_runner(workflow_evidence, conclusion):
    evidence = rerun_after(workflow_evidence, conclusion=conclusion)
    application_release.verify_release_ci(github_fixture(evidence), SOURCE)


@pytest.mark.parametrize('earlier', [
    dict(conclusion='failure', runner_name='GitHub Actions 7', steps=[{'conclusion': 'failure'}]),
    dict(conclusion='failure', runner_name='', steps=[{'conclusion': 'failure'}]),
    dict(conclusion='cancelled', runner_name='GitHub Actions 7', steps=[]),
])
def test_release_ci_rejects_an_earlier_attempt_whose_job_ran(workflow_evidence, earlier):
    evidence = rerun_after(workflow_evidence, **earlier)
    with pytest.raises(ValueError):
        application_release.verify_release_ci(github_fixture(evidence), SOURCE)


@pytest.mark.parametrize('earlier', [
    dict(run_id=2),             # a job of another run
    dict(run_attempt=2),        # listed under attempt 1 but recorded for another attempt
    dict(name='swift-old'),     # no same-name job succeeded in the latest attempt
])
def test_release_ci_exempts_only_misses_of_this_run_rerun_successfully(workflow_evidence, earlier):
    evidence = rerun_after(workflow_evidence, **earlier)
    with pytest.raises(ValueError):
        application_release.verify_release_ci(github_fixture(evidence), SOURCE)


def test_release_ci_exemption_comes_from_attempts_not_check_run_names(workflow_evidence):
    # A cancelled check run named like the exempted job, but not listed by the attempts API.
    evidence = rerun_after(workflow_evidence)
    evidence['check_runs'].append(dict(id=101, name='swift', head_sha=SOURCE, conclusion='cancelled'))
    with pytest.raises(ValueError):
        application_release.verify_release_ci(github_fixture(evidence), SOURCE)


def test_release_ci_still_rejects_unrelated_cancelled_checks_after_a_runner_miss(workflow_evidence):
    evidence = rerun_after(workflow_evidence)
    evidence['check_runs'].append(dict(id=100, name='python', head_sha=SOURCE, conclusion='cancelled'))
    with pytest.raises(ValueError):
        application_release.verify_release_ci(github_fixture(evidence), SOURCE)


def test_release_ci_rejects_a_runner_miss_left_in_the_final_attempt(workflow_evidence):
    evidence = rerun_after(workflow_evidence)
    evidence['workflow_runs'][0]['conclusion'] = 'failure'
    with pytest.raises(ValueError):
        application_release.verify_release_ci(github_fixture(evidence), SOURCE)


def test_release_ci_accepts_a_successful_check_no_longer_in_ci_jobs(workflow_evidence):
    # ios-app was folded into swift (#1670). A successful check run that the current CI_JOBS no
    # longer lists, left on the source, must not stop the source from being released; the job
    # set is judged on the source's own main-push ci.yml run only.
    assert 'ios-app' not in application_release.CI_JOBS
    workflow_evidence['check_runs'].append(dict(id=98, name='ios-app', head_sha=SOURCE, conclusion='success'))
    application_release.verify_release_ci(github_fixture(workflow_evidence), SOURCE)


@pytest.mark.parametrize('conclusion', ['failure', 'cancelled'])
def test_release_ci_rejects_a_failed_or_cancelled_check_no_longer_in_ci_jobs(workflow_evidence, conclusion):
    workflow_evidence['check_runs'].append(dict(id=98, name='ios-app', head_sha=SOURCE, conclusion=conclusion))
    with pytest.raises(ValueError):
        application_release.verify_release_ci(github_fixture(workflow_evidence), SOURCE)


def test_release_ci_rejects_a_run_that_still_has_the_old_job_set(workflow_evidence):
    # A main run built from the old ci.yml (14 jobs, ios-app included) does not satisfy the new
    # 13-job list; such a source is released with its own, older gate file.
    old = dict(workflow_evidence['jobs'][0], id=97, name='ios-app')
    workflow_evidence['jobs'].append(old)
    workflow_evidence['check_runs'].append(old)
    with pytest.raises(ValueError):
        application_release.verify_release_ci(github_fixture(workflow_evidence), SOURCE)


def test_release_ci_jobs_match_the_ci_workflow():
    # The gate must expect exactly the jobs ci.yml defines, including every postgres shard.
    body = (Path(__file__).resolve().parents[2] / application_release.CI_PATH).read_text(
        encoding='utf-8').split('\njobs:\n', 1)[1]
    ids = set(re.findall(r'^  ([A-Za-z0-9_-]+):\s*$', body, re.M))
    shards = re.search(r'^ +shard: \[([0-9, ]+)\]\s*$', body, re.M).group(1).split(',')
    assert not re.search(r'^    name:', body, re.M)  # job check names are their ids
    assert [int(s) for s in shards] == list(range(application_release.POSTGRES_SHARDS))
    assert (ids - {'postgres-shard'}) | {f'postgres-shard ({int(s)})' for s in shards} \
        == application_release.CI_JOBS


def test_release_ci_accepts_skipped_monitor_with_all_required_jobs(workflow_evidence):
    application_release.verify_release_ci(github_fixture(workflow_evidence), SOURCE)


@pytest.mark.parametrize('mutation', [
    'missing_ci', 'wrong_ci_path', 'ci_wrong_event', 'missing_job', 'skipped_job',
    'empty_required_job', 'unrelated_failed_job', 'unrelated_cancelled_run', 'commit_status_failure',
])
def test_release_ci_rejects_missing_evidence_and_explicit_failures(workflow_evidence, mutation):
    evidence = workflow_evidence
    ci, monitor, lint = evidence['workflow_runs']
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
        # Retargeted from the probe's check by #1830: any non-probe check still blocks.
        evidence['check_runs'][-1]['conclusion'] = 'failure'
    elif mutation == 'unrelated_cancelled_run':
        lint['conclusion'] = 'cancelled'
    elif mutation == 'commit_status_failure':
        evidence['state'] = 'failure'
    with pytest.raises(ValueError):
        application_release.verify_release_ci(github_fixture(evidence), SOURCE)


@pytest.mark.parametrize('conclusion', sorted(application_release.BLOCKING_CONCLUSIONS))
def test_release_ci_ignores_a_failed_external_readiness_probe(workflow_evidence, conclusion):
    # #1830: a scheduled or drill probe run reports the live HK service, not the source.
    evidence = workflow_evidence
    monitor = evidence['workflow_runs'][1]
    monitor['conclusion'] = conclusion
    evidence['check_runs'][-2]['conclusion'] = conclusion
    for index in range(3):
        suite = 600 + index
        evidence['workflow_runs'].append(dict(monitor, id=700 + index, check_suite_id=suite,
                                              event='workflow_dispatch' if index else 'schedule'))
        evidence['check_runs'].append(dict(id=800 + index, name='observe', head_sha=SOURCE,
                                           conclusion=conclusion, check_suite={'id': suite}))
    application_release.verify_release_ci(github_fixture(evidence), SOURCE)


@pytest.mark.parametrize('job', sorted(application_release.CI_JOBS))
def test_release_ci_still_blocks_on_any_failed_ci_job_with_a_failed_probe(workflow_evidence, job):
    evidence = workflow_evidence
    evidence['workflow_runs'][1]['conclusion'] = 'failure'
    evidence['check_runs'][-2]['conclusion'] = 'failure'
    failed = next(row for row in evidence['check_runs'] if row['name'] == job)
    failed['conclusion'] = 'failure'
    with pytest.raises(ValueError):
        application_release.verify_release_ci(github_fixture(evidence), SOURCE)


@pytest.mark.parametrize('change', [
    dict(path='.github/workflows/hk-readiness.yml.bak'), dict(path='.github/workflows/hk-readiness-2.yml'),
    dict(path='.github/workflows/ci.yml', event='schedule'), dict(event='push'), dict(event='pull_request'),
    dict(repository={'full_name': 'someone/fork'}),
])
def test_probe_exclusion_matches_only_that_workflow(workflow_evidence, change):
    # A failing run that is not exactly this repository's scheduled/drill probe still blocks.
    evidence = workflow_evidence
    other = dict(evidence['workflow_runs'][1], id=900, check_suite_id=901, conclusion='failure', **change)
    evidence['workflow_runs'].append(other)
    evidence['check_runs'].append(dict(id=902, name='observe', head_sha=SOURCE, conclusion='failure',
                                       check_suite={'id': 901}))
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


LIVE = 'c' * 40


def range_evidence(*entries):
    """main's first-parent history LIVE -> ... -> newest entry; each entry is (number, kind, approval).

    kind: 'merge' (two parents, GitHub merge title), 'squash' (one parent, "(#n)" title) or 'push'.
    approval: list of (author_association, first line) comments on the PR head.
    """
    evidence, commits, parent = {}, [], LIVE
    for index, (number, kind, approvals) in enumerate(entries):
        sha, head = f'{index + 1:040x}', f'{index + 1:039x}f'
        title = {'merge': f'Merge pull request #{number} from JTCAO515/topic',
                 'squash': f'Topic change (#{number})', 'push': 'Direct change on main'}[kind]
        parents = [{'sha': parent}, {'sha': head}] if kind == 'merge' else [{'sha': parent}]
        commits.append(dict(sha=sha, parents=parents, commit={'message': title + '\n\nbody'}))
        if kind == 'merge':
            commits.append(dict(sha=head, parents=[{'sha': parent}], commit={'message': 'topic work'}))
        evidence[f'pulls/{number}'] = dict(merged=True, merge_commit_sha=sha, head={'sha': head})
        evidence[f'issues/{number}/comments?per_page=100&page=1'] = [
            dict(id=100 + position, author_association=association, body=line.format(head=head) + '\nDetails')
            for position, (association, line) in enumerate(approvals)]
        parent = sha
    evidence['compare'] = dict(status='ahead', merge_base_commit={'sha': LIVE},
                               total_commits=len(commits), commits=commits)
    return evidence, parent


def range_lookup(evidence, seen=None):
    def fetch(path):
        if seen is not None:
            seen.append(path)
        if path.startswith('compare/'):
            assert path.endswith('?per_page=100&page=1')
            return evidence['compare']
        return evidence[path]
    return fetch


APPROVED = [('MEMBER', 'Review: APPROVE {head}')]


def test_release_range_accepts_merge_and_squash_prs_each_approved_on_their_exact_head():
    evidence, source = range_evidence((1501, 'merge', APPROVED), (1502, 'squash', APPROVED),
                                      (1503, 'merge', [('OWNER', 'Review: APPROVE {head}')]))
    assert application_release.verify_release_range(range_lookup(evidence), LIVE, source) == [1503, 1502, 1501]


@pytest.mark.parametrize('approvals', [
    [],
    [('MEMBER', 'Review: APPROVE ' + 'e' * 40)],
    [('MEMBER', 'Review: APPROVE {head}'), ('MEMBER', 'Review: REQUEST CHANGES {head}')],
    [('NONE', 'Review: APPROVE {head}')],
    [('MEMBER', 'LGTM {head}\nReview: APPROVE {head}')],
    [('MEMBER', 'Approved {head}')],
], ids=['missing', 'other_head', 'withdrawn', 'non_member', 'not_first_line', 'no_decision'])
def test_release_range_rejects_any_pr_in_the_range_without_a_current_exact_head_approval(approvals):
    # The middle PR is the one an operator could leave off the supporting-review list.
    evidence, source = range_evidence((1501, 'merge', APPROVED), (1502, 'merge', approvals),
                                      (1503, 'merge', APPROVED))
    with pytest.raises(ValueError, match='#1502'):
        application_release.verify_release_range(range_lookup(evidence), LIVE, source)


def test_release_range_rejects_a_direct_push_or_a_title_naming_another_pr():
    evidence, source = range_evidence((1501, 'merge', APPROVED), (1502, 'push', APPROVED))
    with pytest.raises(ValueError, match='not a merged PR'):
        application_release.verify_release_range(range_lookup(evidence), LIVE, source)
    evidence, source = range_evidence((1501, 'merge', APPROVED), (1502, 'squash', APPROVED))
    evidence['pulls/1502']['merge_commit_sha'] = 'd' * 40
    with pytest.raises(ValueError, match='not the merge of PR #1502'):
        application_release.verify_release_range(range_lookup(evidence), LIVE, source)
    evidence['pulls/1502'].update(merge_commit_sha=source, merged=False)
    with pytest.raises(ValueError, match='not the merge of PR #1502'):
        application_release.verify_release_range(range_lookup(evidence), LIVE, source)


def test_release_range_reuses_only_the_exact_approvals_already_verified():
    evidence, source = range_evidence((1501, 'merge', APPROVED), (1502, 'merge', []))
    head = evidence['pulls/1502']['head']['sha']
    seen = []
    assert application_release.verify_release_range(
        range_lookup(evidence, seen), LIVE, source, {(1502, head)}) == [1502, 1501]
    assert 'issues/1502/comments?per_page=100&page=1' not in seen
    assert 'issues/1501/comments?per_page=100&page=1' in seen
    for stale in ({(1502, 'e' * 40)}, {(1503, head)}):
        with pytest.raises(ValueError, match='#1502'):
            application_release.verify_release_range(range_lookup(evidence), LIVE, source, stale)


def test_release_range_requires_a_complete_descending_first_parent_history():
    evidence, source = range_evidence((1501, 'merge', APPROVED), (1502, 'merge', APPROVED))
    evidence['compare']['total_commits'] += 1
    with pytest.raises(ValueError, match='complete release range'):
        application_release.verify_release_range(range_lookup(evidence), LIVE, source)
    evidence, source = range_evidence((1501, 'merge', APPROVED))
    for status, base in (('diverged', 'd' * 40), ('ahead', 'd' * 40), ('behind', 'd' * 40)):
        evidence['compare'].update(status=status, merge_base_commit={'sha': base})
        with pytest.raises(ValueError, match='descend from the live source'):
            application_release.verify_release_range(range_lookup(evidence), LIVE, source)
    evidence, source = range_evidence((1501, 'merge', APPROVED))
    evidence['compare']['commits'] = [row for row in evidence['compare']['commits'] if row['sha'] != source]
    evidence['compare']['total_commits'] -= 1
    with pytest.raises(ValueError, match='leaves main first-parent history'):
        application_release.verify_release_range(range_lookup(evidence), LIVE, source)


def test_release_range_is_empty_only_for_the_live_source_or_its_ancestor():
    def unexpected(path):
        pytest.fail(f'identical source needs no lookup: {path}')
    assert application_release.verify_release_range(unexpected, LIVE, LIVE) == []
    older = 'd' * 40
    behind = dict(status='behind', merge_base_commit={'sha': older}, total_commits=0, commits=[])
    assert application_release.verify_release_range(lambda path: behind, LIVE, older) == []
