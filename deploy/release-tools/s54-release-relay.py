"""Read the original release gate's exact GitHub GETs over the current operator SSH."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import shlex
import subprocess
import sys
import time
from urllib.parse import urlsplit

CODE = Path(__file__).resolve().parent
# Private state (gates, evidence, logs, tokens) stays outside the repository; see README.md.
STATE = Path(os.environ.get('G2C_RELEASE_STATE', '~/.local/share/g2c/b-server-smoke-20261118')).expanduser()
PREFIX=b'G2C_RELEASE_GITHUB_GET '
HOST='''import base64, hashlib, io, json, runpy, sys
from pathlib import Path
from urllib.parse import urlsplit

mode,driver,gate,driver_hash,helper_hash,gate_hash,*flags=sys.argv[1:]
driver=Path(driver).resolve()
assert flags in ([],['--apply'])
files=[(driver,driver_hash),(Path(gate),gate_hash)]
if mode=='forward':
    assert driver.name=='application_release_host.py'
    assert Path(gate).resolve()==driver.with_name('forward-gate.json')
    files.append((driver.with_name('application_release.py'),helper_hash))
else:
    assert mode=='rollback'
    assert str(driver)=='/srv/g2c-beta/quota-self-service-20261112/app-release-idle55-compat3-gatebytes-20261117.py'
    assert Path(gate).name=='rollback-gate.json' and helper_hash=='-'
for path,digest in files:
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
sys.path.insert(0,str(driver.parent))
main=runpy.run_path(str(driver))['main']
def github(request,timeout):
    url=request.full_url
    split=urlsplit(url)
    assert request.get_method()=='GET'
    assert split.scheme=='https' and split.netloc=='api.github.com'
    assert split.path.startswith('/repos/JTCAO515/G2C/') and not split.fragment
    print('G2C_RELEASE_GITHUB_GET '+json.dumps(url),flush=True)
    line=sys.stdin.buffer.readline(23000000)
    if len(line)>=23000000 or not line.endswith(b'\\n'):
        raise ValueError('Authenticated GitHub read unavailable')
    return io.BytesIO(base64.b64decode(line.strip(),validate=True))
main.__globals__['urlopen']=github
sys.argv=[str(driver),gate,*flags]
raise SystemExit(main())
'''

def endpoint(url):
    p=urlsplit(url)
    assert p.scheme=='https' and p.netloc=='api.github.com' and not p.fragment
    prefix='/repos/JTCAO515/G2C/'
    assert p.path.startswith(prefix)
    relative=p.path.removeprefix(prefix)
    assert re.fullmatch(r'(?:actions/runs(?:/[0-9]+(?:/jobs)?)?|commits/[a-f0-9]{40}(?:/(?:check-runs|status))?|pulls(?:/[0-9]+)?|issues/[0-9]+/comments|compare/[a-f0-9]{40}\.\.\.[a-f0-9]{40})',relative)
    assert re.fullmatch(r'(?:[a-zA-Z0-9_=&.-]|%[a-fA-F0-9]{2})*',p.query)
    return p.path[1:]+('?' + p.query if p.query else '')

class GitHubTransportUnavailable(RuntimeError):
    pass


def github_read(path):
    command=['gh','api','--method','GET',path]
    hard_http=re.compile(rb'\bHTTP [45][0-9]{2}\b')
    for attempt in range(12):  # Build 54/55: flaky GitHub egress from this Mac
        try:
            reply=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20)
        except subprocess.TimeoutExpired as error:
            if hard_http.search(error.stderr or b''):
                raise RuntimeError('Authenticated GitHub GET rejected') from None
        else:
            if reply.returncode==0:
                if 0<len(reply.stdout)<=16*1024*1024:
                    return reply.stdout
                raise RuntimeError('Authenticated GitHub GET returned an invalid body')
            transient=re.search(rb'(?i): EOF(?:\r?\n|$)|TLS handshake timeout|connection reset by peer',
                                reply.stderr)
            if not transient or hard_http.search(reply.stderr):
                raise RuntimeError('Authenticated GitHub GET rejected')
        if attempt<11:
            time.sleep(min(attempt+1,4))
    raise GitHubTransportUnavailable('Authenticated GitHub GET transport unavailable')


def public_github_read(ssh,path):
    command=['curl','--disable','-4','--proto','=https','--fail','--silent','--show-error','--connect-timeout','5',
             '--max-time','12','--max-filesize',str(16*1024*1024),'https://api.github.com/'+path]
    reply=subprocess.run([*ssh,shlex.join(command)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=18)
    if reply.returncode or not 0<len(reply.stdout)<=16*1024*1024:
        raise RuntimeError('Public GitHub GET failed')
    return reply.stdout


def main():
    if sys.flags.optimize:
        raise SystemExit('Run the transport without Python optimization')
    ops=runpy.run_path(str(CODE / 'hk-operator.py'))
    phase,source,reviewed_hash,run=sys.argv[1:]
    assert phase in ('preflight','apply','rollback-preflight','rollback-apply')
    assert sys.flags.isolated and os.environ.get('GH_HOST')=='github.com'
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==reviewed_hash
    assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()==source
    assert re.fullmatch(r'b-smoke-20261118-(?:0[5-9]|[1-9][0-9])',run)
    remote_dir=ops['ROOT']+'/probes/'+run
    rollback=phase.startswith('rollback-')
    gate_name='rollback-gate.json' if rollback else 'forward-gate.json'
    gate_bytes=(STATE/(run+'-'+gate_name)).read_bytes()
    local_gate=json.loads(gate_bytes)
    if rollback:
        verdict=json.loads((STATE/(run+'-smoke-verdict.json')).read_bytes())
        assert verdict['source']==source and verdict['status'] in ('FAIL','UNKNOWN')
        assert (local_gate['source'],local_gate['previous_source'])==(ops['OLD'],source)
        script='app-release-idle55-compat3-gatebytes-20261117.py'
        driver=ops['ROOT']+'/quota-self-service-20261112/'+script
        hashes=[hashlib.sha256((ops['PREVIOUS']/script).read_bytes()).hexdigest(),'-']
    else:
        assert local_gate['source']==source
        driver=remote_dir+'/application_release_host.py'
        hashes=[hashlib.sha256(subprocess.check_output(['git','show',source+':deploy/hk/'+name])).hexdigest()
                for name in ('application_release_host.py','application_release.py')]
    command=['python3','-I','-B','-c',HOST,'rollback' if rollback else 'forward',driver,
             remote_dir+'/'+gate_name,*hashes,hashlib.sha256(gate_bytes).hexdigest()]
    if phase.endswith('apply'):
        command.append('--apply')
    name=run+'-authenticated-'+phase
    requests=[]
    public_reads=0
    with (STATE/(name+'.stdout')).open('xb') as output, (STATE/(name+'.stderr')).open('xb') as errors:
        with subprocess.Popen([*ops['SSH'],shlex.join(command)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                              stderr=errors) as remote:
            for line in remote.stdout:
                if line.startswith(PREFIX):
                    path=endpoint(json.loads(line[len(PREFIX):]))
                    assert len(requests)<512  # Build 54: 45 exact reviews exceeded 128; run -49 (57 reviews) exceeded 256
                    transport='authenticated'
                    try:
                        data=github_read(path)
                    except GitHubTransportUnavailable:
                        if public_reads>=24:
                            raise
                        public_reads+=1
                        data=public_github_read(ops['SSH'],path)
                        transport='public'
                    requests.append(dict(path=path,sha256=hashlib.sha256(data).hexdigest(),transport=transport))
                    remote.stdin.write(base64.b64encode(data)+b'\n')
                    remote.stdin.flush()
                else:
                    output.write(line)
                    output.flush()
                    sys.stdout.buffer.write(line)
                    sys.stdout.buffer.flush()
            result=remote.wait()
    ops['save'](STATE/(name+'-github-evidence.json'),json.dumps(requests).encode())
    return result

if __name__=='__main__':
    raise SystemExit(main())
