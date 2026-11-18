"""B-issued exact-source application cutover; no data/credential/budget reset."""
import fcntl,json,os,re,subprocess,sys,time,hashlib
from urllib.request import urlopen,Request
from datetime import datetime,timezone
from pathlib import Path

REPOSITORY = 'JTCAO515/G2C'
CI_PATH = '.github/workflows/ci.yml'
CI_JOBS = frozenset({
    'changes', 'python', 'postgres', 'swift-packages', 'ios-app', 'swift',
    *(f'postgres-shard ({shard})' for shard in range(4)),
})
BLOCKING_CONCLUSIONS = frozenset({
    'failure', 'cancelled', 'timed_out', 'startup_failure', 'action_required', 'stale',
})


def _inventory(github, path, key):
    rows = []
    seen = set()
    separator = '&' if '?' in path else '?'
    for page in range(1, 11):
        response = github(f'{path}{separator}per_page=100&page={page}')
        batch = response[key]
        for row in batch:
            if row['id'] in seen:
                raise ValueError('duplicate GitHub inventory item')
            seen.add(row['id'])
        rows.extend(batch)
        if len(rows) == response['total_count']:
            return rows
        if len(batch) != 100:
            break
    raise ValueError('complete GitHub inventory required')


def verify_release_ci(github, source):
    workflows = _inventory(github, f'actions/runs?head_sha={source}', 'workflow_runs')
    checks = _inventory(github, f'commits/{source}/check-runs?filter=all', 'check_runs')
    if any(row['head_sha'] != source or row['conclusion'] in BLOCKING_CONCLUSIONS
           for row in [*workflows, *checks]):
        raise ValueError('GitHub recorded a failed or cancelled check on the release source')
    if github(f'commits/{source}/status')['state'] in {'failure', 'error'}:
        raise ValueError('GitHub recorded a failed commit status on the release source')
    runs = [run for run in workflows if run['path'] == CI_PATH
            and run['event'] == 'push' and run['head_branch'] == 'main'
            and run['repository']['full_name'] == REPOSITORY
            and run['head_repository']['full_name'] == REPOSITORY]
    if len(runs) != 1 or runs[0]['status'] != 'completed' or runs[0]['conclusion'] != 'success':
        raise ValueError('successful exact-source main ci.yml run required')
    run_id = runs[0]['id']
    jobs = _inventory(github, f'actions/runs/{run_id}/jobs', 'jobs')
    if (len(jobs) != len(CI_JOBS) or {job['name'] for job in jobs} != CI_JOBS
            or any(job['head_sha'] != source or job['run_id'] != run_id
                   or job['status'] != 'completed' or job['conclusion'] != 'success' or not job['steps']
                   for job in jobs)):
        raise ValueError('ten successful ci.yml jobs on the exact release source required')


def verify_release_review(github, source, gate):
    number = gate['pr_number']
    comment_id = gate['review_comment']
    head = gate['review_approved_head']
    if (type(number) is not int or number < 1 or type(comment_id) is not int or comment_id < 1
            or re.fullmatch('[a-f0-9]{40}', head) is None):
        raise ValueError('exact reviewed PR and approval comment required')
    pr = github(f'pulls/{number}')
    if (not pr['merged'] or pr['head']['sha'] != head
            or (source != head and pr['merge_commit_sha'] != source)):
        raise ValueError('release source does not match the reviewed PR')
    decision = re.compile(r'Review: (APPROVE|REQUEST CHANGES) ' + head)
    latest = None
    for page in range(1, 11):
        comments = github(f'issues/{number}/comments?per_page=100&page={page}')
        for comment in comments:
            first_line = comment['body'].partition('\n')[0]
            if (comment['author_association'] in {'OWNER', 'MEMBER', 'COLLABORATOR'}
                    and decision.fullmatch(first_line)
                    and (latest is None or comment['id'] > latest['id'])):
                latest = comment
        if len(comments) < 100:
            break
    else:
        raise ValueError('complete PR review inventory required')
    if (latest is None or latest['id'] != comment_id
            or latest['body'].partition('\n')[0] != f'Review: APPROVE {head}'):
        raise ValueError('current exact-head R approval on the release PR required')


def require_release_window(starts_at,ends_at,now):
    """A bounded idle-deployment lease, without a time-of-day restriction.

    The operator checks announced occupancy before issuing the gate; the
    existing application lock/global drain/ingress-close recheck remain the
    actual mutual-exclusion and original-operation boundaries.
    """
    start=datetime.strptime(starts_at,'%Y-%m-%dT%H:%M:%S.%f+00:00').replace(tzinfo=timezone.utc)
    end=datetime.strptime(ends_at,'%Y-%m-%dT%H:%M:%S.%f+00:00').replace(tzinfo=timezone.utc)
    if now.tzinfo is None or not start<=now<end or not 0<(end-start).total_seconds()<=7200:
        raise ValueError('current bounded idle-deployment window required')


def main(argv=None):
    args=sys.argv[1:] if argv is None else argv
    ROOT=Path('/srv/g2c-beta')
    gate_raw=Path(args[0]).read_bytes()
    gate=json.loads(gate_raw);SOURCE=gate['source'];OLD=gate['previous_source']
    assert re.fullmatch('[a-f0-9]{40}',SOURCE) and re.fullmatch('[a-f0-9]{40}',OLD)
    BASE=['docker','compose','--env-file',str(ROOT/'compose.env'),'-f',str(ROOT/'deploy/hk/compose.yaml'),'-f',str(ROOT/'deploy/hk/compose.local-pg.yaml')]
    def command(args):return subprocess.run(args,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    def inspect(name):return json.loads(command(['docker','inspect',name]).stdout)[0]
    def proof():
     return json.loads(command([*BASE,'run','--rm','--no-deps','-T','--entrypoint','python',
      '-v',str(ROOT/'probes/836-platform-release-proof-plan.json')+':/plan.json:ro',
      '-v',str(ROOT/'probes/836-release-export.py')+':/export.py:ro',
      '-v',str(ROOT/'budget')+':/budget:ro',
      '-v',str(ROOT/'836-platform-release-evidence')+':/evidence:ro','migrate','-B','/export.py']).stdout)
    def instant(value):return datetime.strptime(value,'%Y-%m-%dT%H:%M:%S.%f+00:00').replace(tzinfo=timezone.utc)
    def empty(p):
     return (p['global_pending']==p['global_active']==0 and
      not any(p['background_states'].get(k,0)for k in ('queued','running','publishing'))and
      not any(p['memory_states'].get(k,0)for k in ('pending','inflight')))
    assert gate['source_bytes_equal'] and gate['imported_source_bytes_equal']
    def github(path):
     with urlopen(Request(f'https://api.github.com/repos/{REPOSITORY}/'+path,headers={'Accept':'application/vnd.github+json'}),timeout=20) as r:return json.load(r)
    verify_release_ci(github,SOURCE)
    verify_release_review(github,SOURCE,gate)
    lock=(ROOT/'probes/application-deploy.lock').open('a');os.chmod(lock.name,0o600);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    require_release_window(gate['starts_at'],gate['ends_at'],datetime.now(timezone.utc))
    new=inspect('g2c-beta:'+SOURCE);assert new['Id']==gate['image_id']and new['Architecture']=='amd64'
    assert new['Config']['Labels']['org.opencontainers.image.revision']==SOURCE
    policy=json.loads((ROOT/'quota-self-service-20261112/app-release-policy.json').read_bytes())
    assert json.loads((ROOT/'control/budget/adoption.json').read_bytes())['state']=='ADOPTED_SUBLIMITS_1'
    program="from pathlib import Path;import hashlib,json;names="+repr(list(policy['required_source_hashes']))+";print(json.dumps({n:hashlib.sha256((Path('/app')/n).read_bytes()).hexdigest() for n in names}))"
    actual=json.loads(command(['docker','run','--rm','--network=none','--entrypoint','python','g2c-beta:'+SOURCE,'-B','-c',program]).stdout)
    assert actual==policy['required_source_hashes'],'budget/schema ABI differs; B must handle this temporary change'
    control_before=(ROOT/'control/budget/adoption.json').read_bytes()

    for name in ('api','worker'):
     current=inspect('g2c-beta-'+name+'-1');assert current['Image']==gate['previous_image_id']and current['State']['Running']
     assert current['Config']['Labels']['org.opencontainers.image.revision']==OLD
    before=proof();assert empty(before)
    print(json.dumps(dict(stage='PREFLIGHT_PASS',source=SOURCE,image=gate['image_id'],ledger=before['ledger'],pending=0,active=0,background_states=before['background_states'],memory_states=before['memory_states'])),flush=True)
    if '--apply'not in args:return 0
    p=ROOT/'compose.env';raw=p.read_text();metadata=p.stat();pattern=r'(?m)^CJ_BETA_IMAGE=g2c-beta:'+OLD+r'$'
    assert len(re.findall(pattern,raw))==1
    backup=ROOT/'probes'/('compose.before-app-'+SOURCE+'-'+hashlib.sha256(gate_raw).hexdigest()+'.env')
    with backup.open('x')as f:f.write(raw)
    backup.chmod(0o600)
    updated=re.sub(pattern,'CJ_BETA_IMAGE=g2c-beta:'+SOURCE,raw)
    temporary=ROOT/'compose.app.pending.env'
    with temporary.open('x')as f:f.write(updated);f.flush();os.fsync(f.fileno())
    os.chmod(temporary,metadata.st_mode&0o777);os.chown(temporary,metadata.st_uid,metadata.st_gid)
    worker_stopped=False;changed=False
    try:
     command([*BASE,'stop','-t','20','api'])
     drained=proof();assert empty(drained),'original arrived during ingress close; restore old API and reconcile'
     assert datetime.now(timezone.utc)<instant(gate['ends_at'])
     command([*BASE,'stop','-t','20','worker']);worker_stopped=True
     temporary.replace(p);changed=True
     # The previous capture window is closed/expired. Start the same authorized
     # default worker without its ended capture parameter; keep every raw artifact.
     command([*BASE,'up','-d','--no-deps','api','worker'])
     deadline=time.monotonic()+100
     while True:
      api=inspect('g2c-beta-api-1');worker=inspect('g2c-beta-worker-1')
      assert api['Image']==worker['Image']==gate['image_id']
      assert api['Config']['Labels']['org.opencontainers.image.revision']==worker['Config']['Labels']['org.opencontainers.image.revision']==SOURCE
      assert worker['Config']['Cmd']==['worker']
      if api['State'].get('Health',{}).get('Status')=='healthy'and worker['State']['Running']:break
      if time.monotonic()>=deadline:raise RuntimeError('application readiness deadline exceeded')
      time.sleep(3)
    except BaseException:
     if changed:
      rollback=p.with_name('compose.app.rollback.env')
      with rollback.open('x')as f:f.write(raw);f.flush();os.fsync(f.fileno())
      os.chmod(rollback,metadata.st_mode&0o777);os.chown(rollback,metadata.st_uid,metadata.st_gid);rollback.replace(p)
     if worker_stopped or changed or not inspect('g2c-beta-worker-1')['State']['Running']:
      command([*BASE,'up','-d','--no-deps','api','worker'])
     else:command([*BASE,'up','-d','--no-deps','api'])
     raise
    post=proof();assert empty(post) and post['ledger']==before['ledger'] and (ROOT/'control/budget/adoption.json').read_bytes()==control_before
    print(json.dumps(dict(stage='CUTOVER_PASS',source=SOURCE,image=gate['image_id'],api_health='healthy',worker_running=True,collector='disabled; previous window closed',ledger_before=before['ledger'],ledger_after=post['ledger'],ledger_unchanged=before['ledger']==post['ledger'],pending=post['global_pending'],active=post['global_active'],background_states=post['background_states'],memory_states=post['memory_states'],rollback_source=OLD)),flush=True)


if __name__=='__main__':
    raise SystemExit(main())
