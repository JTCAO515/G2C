"""Canonical once-per-adapter C round2 claims, not a new spending ledger."""
from hashlib import sha256
import json
import os
from pathlib import Path

from real_budget import STATE

ROOT=Path(__file__).resolve().parents[1]
PHASES=STATE/'c-round2-phases'


def adapter_pin():
    # A C output path, batch alias or cosmetic commit cannot create a fresh
    # stage. Only a changed real adapter creates a separate repair candidate.
    paths=('backend/agent/cj_agent/provider.py','backend/cj_api/real_services.py')
    return sha256(b''.join((ROOT/p).read_bytes() for p in paths)).hexdigest()


def path_for(phase):
    if phase not in ('smoke','full'):raise ValueError('known_round2_phase_required')
    return PHASES/(adapter_pin()+'-'+phase+'.json')


def claimed(phase):return path_for(phase).exists()


def exclusive(path, value):
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,'w') as out:
            json.dump(value,out,sort_keys=True);out.flush();os.fsync(out.fileno())
    except BaseException:
        # Retain even an incomplete claim: uncertainty never authorizes replay.
        raise


def claim(phase, output, candidate):
    PHASES.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=path_for(phase)
    try:exclusive(path,dict(phase=phase,adapter_pin=adapter_pin(),candidate_id=candidate,output=str(output.resolve())))
    except FileExistsError:return False
    return True


def finish_smoke(output, candidate, status):
    path=path_for('smoke')
    claimed=json.loads(path.read_bytes())
    if claimed['output']!=str(output.resolve()) or claimed['candidate_id']!=candidate:
        raise ValueError('canonical_original_smoke_claim_required')
    files=['plan.json','observations.json','summary.json']
    rows=json.loads((output/'observations.json').read_bytes())
    files.extend(r['raw_evidence_ref'] for r in rows)
    exclusive(path.with_suffix('.result.json'),dict(candidate_id=candidate,status=status,
        hashes={p:sha256((output/p).read_bytes()).hexdigest() for p in files}))


def verify_smoke(output, candidate):
    claimed=json.loads(path_for('smoke').read_bytes())
    result=json.loads(path_for('smoke').with_suffix('.result.json').read_bytes())
    if (claimed['output']!=str(output.resolve()) or claimed['candidate_id']!=candidate
            or result['candidate_id']!=candidate or result['status']!='PASS'):
        raise ValueError('original_canonical_smoke_PASS_required')
    for name,digest in result['hashes'].items():
        if sha256((output/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('original_smoke_evidence_changed_no_full_dispatch')
