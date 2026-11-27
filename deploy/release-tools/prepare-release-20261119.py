"""Check exact release reviews and copied runtime bytes for the HK app image."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import re
import runpy
import subprocess
import sys
import tarfile
import tempfile

from deploy.build import ROOT, source_context
from deploy.hk.application_release import verify_release_ci, verify_release_review
from deploy.hk.application_release_host import require_source_abi

DIR=Path(__file__).resolve().parent
OPS=runpy.run_path(str(DIR/'hk-operator.py'))
RELATED=(1170,1174,1177,1178,1181,1184,1201,1207,1211,1213,1214,1215,1216,1221,1222,1223,1226)

def github(path):
    for _ in range(3):
        try:
            result=subprocess.run(['gh','api','repos/JTCAO515/G2C/'+path],check=True,
                                  capture_output=True,timeout=20)
            return json.loads(result.stdout)
        except (subprocess.SubprocessError,ValueError):
            pass
    raise RuntimeError('GitHub read unavailable')

def review(number):
    pr=github(f'pulls/{number}')
    assert pr['merged']
    head=pr['head']['sha']
    query='query{repository(owner:"JTCAO515",name:"G2C"){pullRequest(number:%d){comments(last:10){nodes{databaseId body}}}}}' % number
    data=json.loads(subprocess.check_output(['gh','api','graphql','-f','query='+query],timeout=30))
    rows=data['data']['repository']['pullRequest']['comments']['nodes']
    decision=re.compile(r'Review: (APPROVE|REQUEST CHANGES) '+head)
    exact=[row for row in rows if decision.fullmatch(row['body'].splitlines()[0] if row['body'] else '')]
    assert exact and exact[-1]['body'].splitlines()[0]=='Review: APPROVE '+head,number
    record=dict(source=pr['merge_commit_sha'],pr_number=number,review_approved_head=head,
                review_comment=exact[-1]['databaseId'])
    verify_release_review(github,record['source'],record)
    return record

def image_inputs(source):
    with tempfile.TemporaryDirectory(prefix='g2c-release-context-') as temporary:
        dest=Path(temporary)
        source_context(ROOT,dest,source)
        return {str(path.relative_to(dest)):hashlib.sha256(path.read_bytes()).hexdigest()
                for path in dest.rglob('*') if path.is_file()}

CHECK = '''
import hashlib,json,os,sys
from pathlib import Path
from cj_agent import provider,worker
from cj_api import real_services
from cj_usage import metered_exit
from deploy.hk import schema, server_smoke
from runtime_adapter.configuration import source_c0
root=Path('/app')
expected=json.load(sys.stdin)
assert os.getuid()==10001
assert all(hashlib.sha256((root/p).read_bytes()).hexdigest()==h for p,h in expected.items())
assert all(Path(module.__file__).is_relative_to(root) for module in
           (provider,worker,real_services,metered_exit,schema,server_smoke))
# Migration count comes from the image's own manifest (hash-checked above as a source input),
# not a constant: 47c89be1 carries 55, later sources 58+.
assert 'backend/migrations/manifest.json' in expected
count=len(json.loads((root/'backend/migrations/manifest.json').read_text())['migrations'])
assert count>=55 and len(schema.load(root/'deploy/hk/schema')['migrations'])==count
assert source_c0()==json.loads((root/'backend/runtime_adapter/c0.source.json').read_text())
print(json.dumps(dict(files=len(expected),uid=os.getuid(),schema=count,c0='exact',imports=6)))
'''

def main():
    phase, source, primary=sys.argv[1:4]
    primary=int(primary)
    additional=tuple(int(number) for number in sys.argv[4:])
    assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()==source
    assert re.fullmatch('[a-f0-9]{40}',source)
    proof=DIR/('release-20261119-'+source[:8]+'-evidence.json')
    tag='g2c-beta:'+source
    image,arch,rev=subprocess.check_output(['docker','image','inspect',tag,'--format',
        '{{.Id}} {{.Architecture}} {{index .Config.Labels "org.opencontainers.image.revision"}}'],
         text=True).strip().split()
    assert (arch,rev)==('amd64',source)
    inputs=image_inputs(source)
    policy=json.loads((DIR/'policy-58547d31-dccaf289-20261125.json').read_text())  # b994-gc-20261115 dir gone locally (2026-11-25); s54 overrides the policy anyway
    require_source_abi({name:inputs[name] for name in policy['required_source_hashes']},policy)
    if phase=='local':
        verify_release_ci(github,source)
        with ThreadPoolExecutor(max_workers=5) as concurrent:
            records=list(concurrent.map(review,dict.fromkeys((primary,*RELATED,*additional))))
        assert records[0]['source']==source
        for row in records[1:]:
            subprocess.run(['git','merge-base','--is-ancestor',row['source'],source],check=True)
        result=subprocess.run(['docker','run','--rm','--pull=never','--platform=linux/amd64',
                               '--network','none','--read-only','-i','--entrypoint','python',image,'-B','-c',CHECK],
                              text=True,input=json.dumps(inputs),capture_output=True,timeout=100,check=True)
        values=dict(source=source,image=image,primary=records[0],related=records[1:],local=json.loads(result.stdout))
        OPS['save'](proof,json.dumps(values,sort_keys=True).encode())
        print(json.dumps(dict(source=source,image=image,verified=values['local'],reviews=len(records))))
    elif phase=='hk-verify':
        values=json.loads(proof.read_bytes())
        assert (values['source'],values['image'])==(source,image)
        fmt='{{.Id}} {{.Architecture}} {{index .Config.Labels "org.opencontainers.image.revision"}} {{json .RootFS.Layers}}'
        meta=OPS['remote'](['docker','image','inspect',tag,'--format',fmt],timeout=25)
        assert meta.returncode==0
        hk_id,hk_arch,hk_source,hk_layers=meta.stdout.decode().strip().split(maxsplit=3)
        local_layers=subprocess.check_output(['docker','image','inspect',tag,'--format','{{json .RootFS.Layers}}'],
                                             text=True)
        assert (hk_arch,hk_source)==(arch,source) and json.loads(hk_layers)==json.loads(local_layers)
        with subprocess.Popen(['docker','save',tag],stdout=subprocess.PIPE) as exporting:
            manifest=None
            with tarfile.open(fileobj=exporting.stdout,mode='r|*') as archive:
                for member in archive:
                    if member.name.removeprefix('./')=='manifest.json':
                        manifest=json.load(archive.extractfile(member))
            assert exporting.wait()==0 and len(manifest)==1
        config=re.search(r'([0-9a-f]{64})(?:\.json)?$',manifest[0]['Config'])
        assert config and hk_id=='sha256:'+config[1]
        check=OPS['captured'](['docker','run','--rm','--network','none','--read-only','-i',
            '--entrypoint','python',hk_id,'-B','-c',CHECK],json.dumps(inputs).encode(),
            name='release-20261119-'+source[:8]+'-image-proof',timeout=80)
        assert check.returncode==0 and json.loads(check.stdout)==values['local']
        identity=dict(source=source,image=hk_id,local_image=image,config_equal=True,layers_equal=True)
        OPS['save'](DIR/('release-20261119-'+source[:8]+'-hk-identity.json'),json.dumps(identity).encode())
        print(json.dumps(dict(identity,verified=json.loads(check.stdout))))
    else:
        raise ValueError('unknown phase')

if __name__=='__main__':
    main()
