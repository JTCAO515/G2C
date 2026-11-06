"""Non-secret operator inputs for the explicitly selected beta-b API-only case.

These are UI choices and expected records, never server permission or a lease.
The App must authenticate B and read current record/Travel versions itself.
"""
import hashlib
import json
import os
from pathlib import Path

OWNER = 'm4-synthetic-beta-b'
ORIGIN = 'https://api-beta.go2china.space'


def _owned_json(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Regular non-symlink typed fixture required')
    info = path.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o777 != 0o600 or info.st_size > 262144:
        raise ValueError('Owned bounded 0600 typed fixture required')
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def operator_typed_fixture(config_path, records_path):
    config, config_hash = _owned_json(config_path)
    records, records_hash = _owned_json(records_path)
    if not isinstance(config, dict) or set(config) != {'owner', 'status', 'server_context_version', 'server_context_versions',
                       'G2C_DEV_TRAVEL_PROFILE', 'G2C_DEV_TYPED_MEMORY_PROFILE', 'G2C_DEV_TYPED_MEMORY_URL'}:
        raise ValueError('Exact non-secret typed configuration required')
    if config['owner'] != OWNER or config['G2C_DEV_TYPED_MEMORY_URL'] != ORIGIN:
        raise ValueError('Only the approved beta-b owner and exact beta origin are supported')
    if not isinstance(config['status'], str) or not 0 < len(config['status']) <= 128:
        raise ValueError('Bounded source-snapshot status required, not a deployment grant')
    travel = config['G2C_DEV_TRAVEL_PROFILE']
    if not isinstance(travel, dict) or set(travel) != {'version', 'travel_ids'} or travel['version'] != 'app-travel.1':
        raise ValueError('Canonical App Travel profile required')
    ids = travel['travel_ids']
    if (not isinstance(ids, list) or len(ids) != 2
            or any(not isinstance(v, str) or len(v) != 32 or any(c not in '0123456789abcdef' for c in v) for v in ids)
            or len(set(ids)) != 2):
        raise ValueError('Two distinct canonical Travel identifiers required')
    versions = config['server_context_versions']
    if (not isinstance(versions, dict) or set(versions) != set(ids)
            or any(type(v) is not int or not 0 < v < 2**63 for v in versions.values())
            or type(config['server_context_version']) is not int or not 0 < config['server_context_version'] < 2**63):
        raise ValueError('Explicit operator Travel-version metadata required')
    expected_memory = {'version': 'app-memory.2', 'subjects': ['self'],
        'slots': {'preference': {'kind': 'preference', 'collection_allowed': True, 'semantic_resolved': True}},
        'extents': ['long_term', 'current']}
    if config['G2C_DEV_TYPED_MEMORY_PROFILE'] != expected_memory:
        raise ValueError('Only the existing self/preference collection choices are supported')
    flags = config['G2C_DEV_TYPED_MEMORY_PROFILE']['slots']['preference']
    if any(type(flags[k]) is not bool for k in ['collection_allowed', 'semantic_resolved']):
        raise ValueError('Collection-choice flags must be actual JSON booleans')
    if (not isinstance(records, dict) or set(records) != {'owner', 'source_capture_sha256', 'captured_state', 'items', 'budget', 'worker_memory'}
            or records['owner'] != OWNER or records['worker_memory'] != 'UNRUN'):
        raise ValueError('B-owned API-only captured records required; model recall remains UNRUN')
    if not isinstance(records['items'], list) or len(records['items']) != 3:
        raise ValueError('One existing active seed for each of the three scopes required')
    capture = records['source_capture_sha256']
    if not isinstance(capture, str) or len(capture) != 64 or any(c not in '0123456789abcdef' for c in capture):
        raise ValueError('Original source-capture SHA256 required')
    fields = {'item_id', 'operation_id', 'subject', 'slot', 'kind', 'text', 'occurred_at', 'extent',
              'context', 'source_id', 'source_version', 'version', 'status', 'recorded_at'}
    by_scope = {}
    seen = set()
    for item in records['items']:
        if not isinstance(item, dict) or set(item) != fields or any(not isinstance(item[k], str) or not item[k] for k in fields - {'context', 'version', 'source_version'}):
            raise ValueError('Complete captured seed fields required')
        if (item['subject'], item['slot'], item['kind'], item['status']) != ('self', 'preference', 'preference', 'active'):
            raise ValueError('Only the original active B seeds may be paused and restored')
        if any(type(item[k]) is not int or not 0 < item[k] < 2**63 - 8 for k in ['version', 'source_version']):
            raise ValueError('Positive captured item/source versions required')
        context = item['context']
        if item['extent'] == 'long_term' and context is None:
            key = 'long_term'
        elif (item['extent'] == 'current' and isinstance(context, dict)
              and set(context) == {'kind', 'id', 'expected_version'} and context['kind'] == 'travel'
              and context['id'] in ids and type(context['expected_version']) is int
              and 0 < context['expected_version'] < 2**63):
            key = context['id']
        else:
            raise ValueError('Original null or Travel context must remain explicit')
        if key in by_scope or item['item_id'] in seen:
            raise ValueError('Captured scopes and item IDs must be distinct')
        by_scope[key] = item
        seen.add(item['item_id'])
    if set(by_scope) != {'long_term', *ids}:
        raise ValueError('Missing one of the approved seed scopes')
    environment = {key: json.dumps(config[key], ensure_ascii=False, separators=(',', ':'))
        for key in ['G2C_DEV_TRAVEL_PROFILE', 'G2C_DEV_TYPED_MEMORY_PROFILE']}
    environment['G2C_DEV_TYPED_MEMORY_URL'] = ORIGIN
    fixture = dict(owner=OWNER, environment=environment, travels=ids, travel_versions=versions,
                   seeds=[by_scope[k] for k in ['long_term', *ids]])
    provenance = dict(config_sha256=config_hash, records_sha256=records_hash,
        source_capture_sha256=records['source_capture_sha256'], owner=OWNER,
        source_status=config['status'], model_recall='UNRUN',
        write_scope='read/list, reversible seed pause, new manual save, new-item pause/resume/pause, seed resume; no edit/withdraw/delete/MESSAGE')
    return fixture, provenance
