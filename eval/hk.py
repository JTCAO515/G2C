"""Source-pinned C runner for B's existing HK operator image; no remote dispatch.

Packaging uses committed public source only. The operator supplies the reviewed
base image, two private service keys, persistent evidence and original HK ledger.
No operator, cloud database, cleanup or OSS identity belongs in this process.
"""
import argparse
from functools import lru_cache
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import runpy
import stat
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
MANIFEST='c-eval-source.json'
SECRET=Path('/run/secrets/c-eval.env')
KEYS=frozenset(('CJ_MODEL_API_KEY','CJ_AMAP_WEB_KEY'))


def active():return os.environ.get('CJ_DEPLOY_TARGET')=='hk-beta'


def _allowed(path):
    p=Path(path)
    return (not p.is_absolute() and '..' not in p.parts and
            (path in ('pyproject.toml','uv.lock') or path.startswith(
                ('backend/','scripts/','deploy/','eval/','evaluation/cj028/'))))


@lru_cache(maxsize=1)
def source_manifest():
    raw=(ROOT/MANIFEST).read_bytes()
    expected=os.environ.get('CJ_C_EVAL_SOURCE_SHA256','')
    if re.fullmatch('[0-9a-f]{64}',expected) is None or sha256(raw).hexdigest()!=expected:
        raise ValueError('independently_pinned_C_source_manifest_required')
    value=json.loads(raw)
    if (not isinstance(value,dict) or set(value)!={'version','commit','backend_commit','hashes'} or value['version']!=1 or
            not isinstance(value['commit'],str) or re.fullmatch('[0-9a-f]{40}',value['commit']) is None or
            not isinstance(value['backend_commit'],str) or re.fullmatch('[0-9a-f]{40}',value['backend_commit']) is None or
            not isinstance(value['hashes'],dict) or not value['hashes']):
        raise ValueError('committed_C_source_pin_required')
    for name,digest in value['hashes'].items():
        if not _allowed(name) or not isinstance(digest,str) or re.fullmatch('[0-9a-f]{64}',digest) is None:
            raise ValueError('bounded_C_source_paths_required')
        path=ROOT/name
        if (path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()) or
                sha256(path.read_bytes()).hexdigest()!=digest):
            raise ValueError('reviewed_B_and_C_source_bytes_required')
    return value


def source_candidate():
    if active():return source_manifest()['commit']
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()


def source_info():
    if not active():return dict(runner_commit=source_candidate(),backend_commit='UNKNOWN')
    value=source_manifest()
    return dict(runner_commit=value['commit'],backend_commit=value['backend_commit'],
                manifest_sha256=os.environ['CJ_C_EVAL_SOURCE_SHA256'])


def require_output(path):
    if active() and not path.resolve().is_relative_to(Path('/evidence')):
        raise ValueError('persistent_C_evidence_volume_required')


def services(subjects):
    """Reuse B's real factory; keys are removed before any PG child starts."""
    from deploy.hk.configuration import authorization
    from cj_api.real_services import RealServices
    from cj_usage.authorization_budget import HK_PRODUCER
    authorization()
    if os.environ.get('CJ_M4_BUDGET_PRODUCER')!=HK_PRODUCER:
        raise ValueError('original_HK_producer_required')
    if any(name.startswith(('CJ_SUPABASE_','CJ_BETA_','OSS_')) or
           name in KEYS or name in {k+'_FILE' for k in KEYS} for name in os.environ):
        raise ValueError('minimal_C_service_identity_required')
    fd=os.open(SECRET,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as source:
        metadata=os.fstat(source.fileno())
        if (not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode)!=0o600
                or metadata.st_uid!=os.getuid()):
            raise ValueError('owned_0600_C_service_subset_required')
        raw=source.read(16385)
    if len(raw)>16384:raise ValueError('bounded_C_service_subset_required')
    values={}
    for line in raw.decode('utf8').splitlines():
        name,separator,value=line.partition('=')
        if not separator or name not in KEYS or name in values or not value or '\0' in value:
            raise ValueError('exact_two_C_service_keys_required')
        values[name]=value
    if set(values)!=KEYS:raise ValueError('complete_C_service_subset_required')
    try:
        os.environ.update(values)
        with tempfile.TemporaryDirectory(prefix='g2c-c-invited-') as folder:
            auth=Path(folder)
            (auth/'invited.json').write_text(json.dumps(sorted(subjects)))
            return RealServices.from_environment(auth,authorization_guard=authorization)
    finally:
        for name in values:os.environ.pop(name,None)


def package(output,backend_commit):
    """Create a reproducible, secret-free overlay; do not build or launch it."""
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT):
        raise ValueError('clean_committed_C_source_required')
    if output.exists():raise ValueError('new_source_context_required')
    if re.fullmatch('[0-9a-f]{40}',backend_commit) is None:
        raise ValueError('explicit_reviewed_backend_commit_required')
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
    from deploy.build import source_context
    with tempfile.TemporaryDirectory(prefix='g2c-c-source-') as folder:
        base=Path(folder)
        source_context(ROOT,base,backend_commit)
        hashes={p.relative_to(base).as_posix():sha256(p.read_bytes()).hexdigest()
                for p in sorted(base.rglob('*')) if p.is_file()}
        comparison=base/'C-source';comparison.mkdir()
        source_context(ROOT,comparison,commit)
        current={p.relative_to(comparison).as_posix():sha256(p.read_bytes()).hexdigest()
                 for p in sorted(comparison.rglob('*')) if p.is_file()}
        if current!=hashes:raise ValueError('C_commit_must_contain_exact_reviewed_B_source')
    output.mkdir(parents=True,mode=0o700)
    entries=subprocess.check_output(['git','ls-tree','-rz',commit,'--','eval',
        'evaluation/cj028/evaluate.py'],cwd=ROOT).split(b'\0')
    for entry in entries:
        if not entry:continue
        metadata,raw_path=entry.split(b'\t',1);mode,kind,oid=metadata.split()
        name=raw_path.decode();path=Path(name)
        if ('tests' in path.parts or 'reports' in path.parts or
                mode not in (b'100644',b'100755') or kind!=b'blob' or
                any(part.startswith('.') for part in path.parts) or
                path.suffix not in ('.py','.json','.Dockerfile')):continue
        raw=subprocess.check_output(['git','cat-file','blob',oid.decode()],cwd=ROOT)
        target=output/path;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(raw);hashes[name]=sha256(raw).hexdigest()
    raw=json.dumps(dict(version=1,commit=commit,backend_commit=backend_commit,hashes=hashes),sort_keys=True,separators=(',',':')).encode()
    (output/MANIFEST).write_bytes(raw)
    return commit,sha256(raw).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    pack=commands.add_parser('package');pack.add_argument('--output',type=Path,required=True)
    pack.add_argument('--backend-commit',required=True)
    run=commands.add_parser('run');run.add_argument('phase',choices=('smoke','full'))
    run.add_argument('arguments',nargs=argparse.REMAINDER)
    args=parser.parse_args()
    if args.command=='package':
        commit,digest=package(args.output,args.backend_commit)
        print('C_SOURCE='+commit+' MANIFEST_SHA256='+digest)
    else:
        if not active():raise ValueError('explicit_HK_execution_context_required')
        script=ROOT/'eval'/('smoke.py' if args.phase=='smoke' else 'real.py')
        sys.argv=[str(script),*args.arguments]
        runpy.run_path(str(script),run_name='__main__')


if __name__=='__main__':main()
