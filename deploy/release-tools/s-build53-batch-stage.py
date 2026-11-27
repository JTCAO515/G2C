"""Bind the original host deployer to a reviewed Build 53 batch and its actual predecessor."""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import re
import runpy
import subprocess
import sys

HERE=Path(__file__).resolve().parent
OPERATOR=HERE/'hk-operator.py'
OPERATOR_SHA='012cf79e0f552a8cb9d7c90eaaa08c177246c19265419c6a13632c0e1efee5b4'


def evidence(source):
    prefix=HERE/('release-20261119-'+source[:8])
    local=json.loads(prefix.with_name(prefix.name+'-evidence.json').read_bytes())
    remote=json.loads(prefix.with_name(prefix.name+'-hk-identity.json').read_bytes())
    proof=prefix.with_name(prefix.name+'-image-proof.stdout').read_bytes()
    assert local['source']==remote['source']==source and remote['local_image']==local['image']
    assert remote['config_equal'] and remote['layers_equal'] and json.loads(proof)==local['local']
    return local,remote['image'],sha256(proof).hexdigest()


def main():
    phase,source,previous,run=sys.argv[1:]
    assert phase in ('stage-permanent','write-gate','readback')
    assert all(re.fullmatch('[a-f0-9]{40}',value) for value in (source,previous)) and source!=previous
    assert re.fullmatch(r'b-smoke-20261118-[2-9][0-9]',run)
    assert sha256(OPERATOR.read_bytes()).hexdigest()==OPERATOR_SHA
    assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()==source
    local,image,digest=evidence(source)
    _,previous_image,_=evidence(previous)
    ops=runpy.run_path(str(OPERATOR))
    if phase=='write-gate':
        now=datetime.now(timezone.utc)
        raw=json.dumps(dict(local['primary'],image_id=image,previous_source=previous,previous_image_id=previous_image,
           starts_at=now.isoformat(timespec='microseconds'),ends_at=(now+timedelta(minutes=29)).isoformat(timespec='microseconds'),
           authority='JT Build 53 and #495/7096832261',reason='Apply the reviewed Build 53 batch under the original guards',
           source_bytes_equal=True,imported_source_bytes_equal=True,hk_image_proof_sha256=digest,
           related_reviews=local['related']),sort_keys=True).encode()
        ops['save'](HERE/(run+'-forward-gate.json'),raw)
        ops['safe_upload'](ops['ROOT']+'/probes/'+run+'/forward-gate.json',raw)
        print(json.dumps({k:json.loads(raw)[k] for k in ('starts_at','ends_at','source','previous_source')}))
        return 0
    driver=ops['main']
    driver.__globals__.update(OLD=previous,OLD_IMAGE=previous_image,NEW=source,NEW_IMAGE=image,
                               WORKTREE=Path.cwd(),GATE_WORKTREE=Path.cwd())
    sys.argv=[sys.argv[0],run,phase]
    if phase=='stage-permanent':
        sys.argv+=['--release-head',source]
    return driver()

if __name__=='__main__':
    raise SystemExit(main())
