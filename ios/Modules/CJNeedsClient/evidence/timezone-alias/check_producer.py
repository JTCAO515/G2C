"""Read-only replay of the same alias inputs against the exact c821 producer."""
from pathlib import Path
import json
import subprocess
import sys
import types

PIN = 'c821b34d607016c6dbc1020c203621841f1a60e8'
source = subprocess.check_output(['git', '-C', sys.argv[1], 'show', PIN + ':backend/needs/cj_needs/domain.py'])
module = types.ModuleType('fixed_needs_alias_domain')
sys.modules[module.__name__] = module
exec(compile(source, 'fixed-domain.py', 'exec'), module.__dict__)
results = []
for alias in ['Etc/UTC', 'US/Eastern', 'PRC']:
    known = {'state': 'known', 'value': alias}
    local = {'date': {'state': 'known', 'value': '2026-11-01'}, 'time': {'state': 'known', 'value': '01:30:00'},
             'timezone': known, 'place': {'state': 'unknown'}}
    command = {'action_id': 'alias-action', 'needs_id': 'alias-needs', 'expected_version': 0,
               'source': {'kind': 'manual', 'text': 'Explicit timezone alias / 用户原样输入'},
               'changes': {'destination_timezone': known, 'overseas_timezone': known, 'arrival': local}}
    raw = json.dumps(command, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    original = module.Command(raw)
    module.validate_fields(original.data['changes'], complete=True)
    assert original.raw == raw and original.data['changes']['arrival']['timezone']['value'] == alias
    results.append({'timezone': alias, 'producer_accepts': True, 'original_preserved': True})
for invalid in ['', 'Not/A_Real_Zone']:
    try:
        module.zone(invalid)
    except module.InvalidInput:
        results.append({'timezone': invalid, 'producer_rejects': True})
    else:
        raise AssertionError('invalid timezone unexpectedly accepted')
print(json.dumps({'producer': PIN, 'checks': results, 'SQL': 'UNRUN', 'HTTP': 'UNRUN'}, ensure_ascii=False, indent=2))
