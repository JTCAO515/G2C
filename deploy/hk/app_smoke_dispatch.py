"""Host-side B dispatcher: exact live pins, serialized original reads only.

Compatible with the existing host Python. No token in argv/diagnostics, no
arbitrary uploaded program, dispatch, retry, allocation or account mutation.
The original inflight marker stays on timeout/nonzero until B reconciles it.
"""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
import uuid


ROOT=Path('/srv/g2c-beta')


def private(path,bound):
    fd=os.open(str(path),os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb')as source:
        info=os.fstat(source.fileno())
        if(not stat.S_ISREG(info.st_mode)or info.st_uid!=os.geteuid()or stat.S_IMODE(info.st_mode)!=0o600):
            raise ValueError('owned private live qualification required')
        raw=source.read(bound+1)
    if len(raw)>bound:raise ValueError('bounded live qualification required')
    return raw


def inspect(role):
    value=json.loads(subprocess.check_output(['docker','inspect','g2c-beta-'+role+'-1'],timeout=10))[0]
    return dict(id=value['Id'],source=value['Config']['Labels']['org.opencontainers.image.revision'],
        image=value['Image'],running=value['State']['Running'],health=value['State'].get('Health',{}).get('Status'),
        command=value['Config']['Cmd'],mounts={m['Destination']:dict(source=m['Source'],rw=m['RW'])for m in value['Mounts']})


def probe(q):
    result={role:inspect(role)for role in('api','worker')}
    for role,value in result.items():
        if (value['source'],value['image'],value['running'])!=(q['source'],q['image'],True):
            raise ValueError('actual App smoke source/image changed')
        expected=['api','--app-smoke-api-manifest',q['api_manifest']]if role=='api'else[
            'worker','--app-smoke-manifest',q['worker_manifest']]
        if value['command']!=expected:raise ValueError('actual App smoke composition changed')
        if value['mounts']!=q['mounts'][role]:raise ValueError('complete qualified mount set changed')
    worker_only=('/app-smoke-evidence','/rejected-intakes','/tool-evidence',
                 '/run/secrets/worker.env','/home/cj/.local/share/g2c/m4-real-services')
    api_mounts=result['api']['mounts'];worker_mounts=result['worker']['mounts']
    private_sources={worker_mounts[target]['source']for target in worker_only if target in worker_mounts}
    if any(target in api_mounts for target in worker_only)or any(
            mount['source']in private_sources for mount in api_mounts.values()):
        raise ValueError('worker-only originals cannot be mounted in API')
    if result['api']['health']!='healthy':raise ValueError('actual API is not ready')
    return result


def run(path,envelope):
    raw=private(path,131072);q=json.loads(raw)
    if (q.get('version')!='G2C-App-smoke-live.1'or q.get('state')not in('ACTIVE','STOP_NEW')or
            hashlib.sha256(raw).hexdigest()!=envelope['qualification_sha256']):
        raise ValueError('fixed active App smoke qualification required')
    request=envelope['request']
    if(request['expected_source']!=q['source']or request['plan_sha256']!=q['plan_sha256']):
        raise ValueError('original App smoke request pins changed')
    if q['state']!='ACTIVE'and request['kind']=='checkpoint':raise ValueError('no new App action after stop-new')
    deployment=(ROOT/'probes/application-deploy.lock').open('r')
    fcntl.flock(deployment,fcntl.LOCK_SH|fcntl.LOCK_NB)
    lock_path=ROOT/'probes/qualified-reader.lock'
    lock_fd=os.open(str(lock_path),os.O_RDONLY|os.O_NOFOLLOW)
    try:
        info=os.fstat(lock_fd)
        if(not stat.S_ISREG(info.st_mode)or info.st_uid!=os.geteuid()or stat.S_IMODE(info.st_mode)!=0o600):
            raise ValueError('owned serial reader lock required')
        deadline=time.monotonic()+10
        while True:
            try:fcntl.flock(lock_fd,fcntl.LOCK_EX|fcntl.LOCK_NB);break
            except BlockingIOError:
                if time.monotonic()>=deadline:raise ValueError('native reader queue deadline reached')
                time.sleep(.1)
        if private(path,131072)!=raw:raise ValueError('qualification changed while waiting')
        before=probe(q);worker=before['worker']
        code="from pathlib import Path;import hashlib;print(hashlib.sha256(Path('/app/deploy/hk/app_smoke_read.py').read_bytes()).hexdigest())"
        actual=subprocess.check_output(['docker','exec',worker['id'],'python','-B','-c',code],timeout=10).decode().strip()
        if actual!=q['reader_sha256']:raise ValueError('actual native reader code changed')
        pending=ROOT/'probes/qualified-reader.inflight.json'
        if pending.exists()or pending.is_symlink():raise ValueError('previous native reader outcome pending; B reconciliation required')
        nonce='g2c-reader-'+uuid.uuid4().hex
        marker=json.dumps(dict(version='G2C-App-smoke-native-read.1',nonce=nonce,worker_id=worker['id'],
            source=q['source'],image=q['image'],window_id=q['window_id'],kind=request['kind']),sort_keys=True).encode()
        fd=os.open(str(pending),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'wb')as output:output.write(marker);output.flush();os.fsync(output.fileno())
        # The nonce remains in the real child argv for bounded B-only process
        # reconciliation. The module receives only its fixed manifest argument.
        boot="import runpy,sys;sys.argv=['app_smoke_read',"+repr(q['api_manifest'])+"];runpy.run_module('deploy.hk.app_smoke_read',run_name='__main__')"
        try:
            result=subprocess.run(['docker','exec','-i',worker['id'],'python','-B','-c',boot,nonce],
                input=json.dumps(request).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60)
        except subprocess.TimeoutExpired:
            raise ValueError('native read timeout; original inflight marker retained')from None
        if result.returncode:
            failure=dict(version='G2C-App-smoke-read-failure.1',phase='native_read',return_code=result.returncode,
                stderr_sha256=hashlib.sha256(result.stderr).hexdigest(),nonce=nonce)
            sys.stderr.write(json.dumps(failure)+'\n')
            raise ValueError('native read failed; original inflight marker retained')
        after=probe(q)
        if any((after[r]['id'],after[r]['source'],after[r]['image'])!=(before[r]['id'],q['source'],q['image'])for r in before):
            raise ValueError('actual source changed during native read')
        if private(path,131072)!=raw or private(pending,16384)!=marker:
            raise ValueError('original read authority changed')
        value=json.loads(result.stdout.decode())
        if value.get('version')!='G2C-App-smoke-read.1':raise ValueError('native reader response changed')
        pending.unlink()
        return dict(version='G2C-App-smoke-host-read.1',qualification_sha256=hashlib.sha256(raw).hexdigest(),
            actual_roles=after,original=value)
    finally:os.close(lock_fd);deployment.close()


def main():
    if len(sys.argv)!=2:raise ValueError('fixed B live qualification path required')
    raw=sys.stdin.buffer.read(524289)
    if len(raw)>524288:raise ValueError('bounded host read request required')
    envelope=json.loads(raw.decode())
    if type(envelope)is not dict or set(envelope)!={'qualification_sha256','request'}:
        raise ValueError('exact host read envelope required')
    print(json.dumps(run(Path(sys.argv[1]),envelope)))


if __name__=='__main__':main()
