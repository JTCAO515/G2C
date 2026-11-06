"""Canonical once-per-adapter C round2 claims, not a new spending ledger."""
from hashlib import sha256
import json
import os
from pathlib import Path

from real_budget import STATE

ROOT=Path(__file__).resolve().parents[1]
PHASES=STATE/'c-round2-phases'
CORE_SOURCES=('backend/agent/cj_agent/provider.py','backend/cj_api/real_services.py')
FACT_SOURCES=('backend/fact/cj_fact/live_source.py','backend/fact/cj_fact/https_transport.py')
# Every FACT source pair present before this identity expansion (through PR566).
# Preserve the original two-file key for those deployed adapters, including936
# and8a. Merely upgrading C cannot grant them another phase. Future production
# FACT changes participate in the identity; this list is not a dispatch allowlist.
LEGACY_FACT_SOURCES=frozenset((
    ('13ae82988ffeb4697d0ca65639aa29dd6c9686578439f3cf859865dd4c9eb81e',
     '66888f6ab5f7d2ceaad76a4588c644839744ced960211ab5c62a40d9baa93e54'),  # e1f1e8a1
    ('404f8e16d74607d60168e1a81a6a991603e545c6e232c66433a537ca0e113441',
     '038ba5177456c8544ecd063aaf1ee4cce509ceefda3d7012f3695bf5702aff2d'),  # f9cf2823/936
    ('e25b98a34debb3e59fb7bb4802b01406fa139e18fcb388ba3fb2b4c1cf09c0ae',
     '038ba5177456c8544ecd063aaf1ee4cce509ceefda3d7012f3695bf5702aff2d'),  # 8a887140
))


def _identity(core_pin, hashes):
    version=1 if tuple(hashes[p] for p in FACT_SOURCES) in LEGACY_FACT_SOURCES else 2
    pin=core_pin if version==1 else sha256(b'G2C-C-REAL-ADAPTER.2\0'+
        json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return dict(version=version,pin=pin,source_sha256=hashes)


def adapter_identity():
    # Read only production bytes. No C commit, output, environment nonce, test,
    # report or runner file can produce a new identity. Missing source fails.
    raw={p:(ROOT/p).read_bytes() for p in (*CORE_SOURCES,*FACT_SOURCES)}
    return _identity(sha256(b''.join(raw[p] for p in CORE_SOURCES)).hexdigest(),
                     {p:sha256(value).hexdigest() for p,value in raw.items()})


def adapter_pin():
    return adapter_identity()['pin']


def _path_for(phase, pin):
    if phase not in ('smoke','full'):raise ValueError('known_round2_phase_required')
    return PHASES/(pin+'-'+phase+'.json')


def path_for(phase):return _path_for(phase,adapter_pin())


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
    identity=adapter_identity()
    path=_path_for(phase,identity['pin'])
    PHASES.mkdir(parents=True,exist_ok=True,mode=0o700)
    try:exclusive(path,dict(phase=phase,adapter_pin=identity['pin'],adapter_identity=identity,
                           candidate_id=candidate,output=str(output.resolve())))
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
