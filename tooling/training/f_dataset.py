"""Consume the fixed F boundary; no copied schema, provider, export or trainer.

Run in the repository's locked environment, separate from ms-swift. F's domain
codecs remain authoritative; only input/source pins are checked here.
"""
import hashlib
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

VERSION = 'G2C-dataset.1'
F_HEAD = '8bbdf6a9291966e448a13235a2d85e1f2abf524c'
SCHEMA_SHA256 = '2b5107224be5385042812e7d41cc3203d999cba8c755dd4748482c87d8ff8052'
CONVERTER_SHA256 = '941f67a75f73f23f0f5ca3a0cc71f7fc384fe55f04c774349255d024af6d91c8'
TOOLS_SHA256 = '94856980dc1c073ce441f4c6cd1905bb7036a4cb2085d8c1280e39f58fcb435b'


def check_dataset(path, version, input_sha256):
    result = {'scope': 'F-synthetic-interface-only', 'training_readiness': 'UNRUN',
              'real_model_template': 'UNRUN', 'formal_data_quality': 'UNKNOWN'}
    if version != VERSION:
        return {**result, 'status': 'UNRUN', 'code': 'UNKNOWN_DATA_VERSION'}, 2
    if not input_sha256 or not re.fullmatch('[a-f0-9]{64}', input_sha256):
        return {**result, 'status': 'UNRUN', 'code': 'MISSING_OR_INVALID_INPUT_SHA256'}, 2
    source = ROOT / 'tooling/datasets'
    pins = ((source / 'schema.v1.json', SCHEMA_SHA256),
            (source / 'convert.py', CONVERTER_SHA256))
    # F reads schema at import time. Check bytes before executing that module,
    # so malformed or changed material is reported as UNRUN, not a traceback.
    try:
        changed = any(hashlib.sha256(p.read_bytes()).hexdigest() != expected
                      for p, expected in pins)
    except FileNotFoundError:
        return {**result, 'status': 'UNRUN', 'code': 'F_SCHEMA_UNAVAILABLE'}, 2
    if changed:
        return {**result, 'status': 'UNRUN', 'code': 'UNREVIEWED_F_REVISION'}, 2
    try:
        from tooling.datasets import convert as f
    except ModuleNotFoundError:
        return {**result, 'status': 'UNRUN', 'code': 'F_ENVIRONMENT_UNAVAILABLE',
                'reason': 'Run in the repository locked environment after F delivery.'}, 2
    if f.TOOLS_HASH != TOOLS_SHA256:
        return {**result, 'status': 'UNRUN', 'code': 'UNREVIEWED_F_REVISION'}, 2
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != input_sha256:
        return {**result, 'status': 'FAIL', 'code': 'INPUT_SHA256_MISMATCH'}, 1
    if not raw:
        return {**result, 'status': 'FAIL', 'code': 'EMPTY_DATASET'}, 1
    output, _lineage, rejected, _groups, report = f.convert(raw, VERSION)
    complete = {split: sum(row['run']['status'] == 'completed' and
                           row['run']['answer_state'] == 'complete' for row in rows)
                for split, rows in output.items()}
    diagnostics = []
    lines = raw.splitlines()
    for rejected_row in rejected:
        item = {'line': rejected_row['line'], 'reason': rejected_row['reason']}
        if item['reason'] == 'schema_invalid':
            # F has rejected this external row: enrich diagnostics only, never
            # revalidate established domain objects or change F admission.
            row = f.load(lines[item['line'] - 1])
            missing = set()
            for error in f.VALIDATOR.iter_errors(row):
                if error.validator == 'required' and isinstance(error.instance, dict):
                    missing.update('.'.join(map(str, (*error.absolute_path, key)))
                                   for key in error.validator_value if key not in error.instance)
            if missing:
                item['missing_fields'] = sorted(missing)
            if isinstance(row, dict) and 'version' in row and row['version'] != VERSION:
                item['version_code'] = 'UNKNOWN_ROW_DATA_VERSION'
        diagnostics.append(item)
    # Keep every F row/group, including partial/none terminal controls. These
    # counts are a preparation report, not selection/export of a training set.
    return {**result, 'status': report['status'], 'f_reviewed_head': F_HEAD,
            'version': VERSION, 'converter_version': f.CONVERTER,
            'input_sha256': actual, 'schema_sha256': SCHEMA_SHA256,
            'tool_schema_sha256': f.TOOLS_HASH, 'report': report,
            'complete_answer_counts': complete,
            'control_only_counts': {split: len(rows) - complete[split]
                                    for split, rows in output.items()},
            'rejections': diagnostics}, 1 if rejected else 0
