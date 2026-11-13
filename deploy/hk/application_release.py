"""B-issued exact-source application cutover; no data/credential/budget reset."""
import fcntl,json,os,re,subprocess,sys,time,hashlib
from urllib.request import urlopen,Request
from datetime import datetime,timezone
from pathlib import Path

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
    gate=json.loads(Path(args[0]).read_bytes());SOURCE=gate['source'];OLD=gate['previous_source']
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
    lock=(ROOT/'probes/application-deploy.lock').open('a');os.chmod(lock.name,0o600);fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    now=datetime.now(timezone.utc)
    assert gate['source']==SOURCE and gate['ci_all_green']is True and gate['review_approved_head']==SOURCE
    assert gate['source_bytes_equal'] and gate['imported_source_bytes_equal']
    def github(path):
     with urlopen(Request('https://api.github.com/repos/JTCAO515/G2C/'+path,headers={'Accept':'application/vnd.github+json'}),timeout=20) as r:return json.load(r)
    pr=github('pulls/'+str(gate['pr_number']));assert pr['merged'] and pr['head']['sha']==SOURCE
    checks=github('commits/'+SOURCE+'/check-runs')['check_runs'];assert checks and all(x['status']=='completed' and x['conclusion']=='success' for x in checks)
    assert github('commits/'+SOURCE+'/status')['state']=='success'
    assert len({x['name'] for x in gate['checks']})>=13 and all(x['state']=='SUCCESS' for x in gate['checks'])
    require_release_window(gate['starts_at'],gate['ends_at'],now)
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
    backup=ROOT/'probes'/('compose.before-app-'+SOURCE+'.env')
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
