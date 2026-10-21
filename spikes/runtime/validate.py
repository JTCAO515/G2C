"""Run against real installed packages and fresh local SQLite databases.

All provider responses are deterministic fixtures. Failures are preserved.
"""
import concurrent.futures
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from importlib.metadata import version

import ledger

HERE = Path(__file__).resolve().parent
PARSER = argparse.ArgumentParser()
PARSER.add_argument('--group', choices=['all', 'cancel'], default='all')
PARSER.add_argument('--case')
OPTIONS = PARSER.parse_args()
GROUP = OPTIONS.group
RUN = HERE / '.runs' / ('validation-' + str(time.time_ns()))
RUN.mkdir(parents=True)
RECORDS = []
CHECKS = []
ENV = {'PATH': str(Path(sys.executable).parent) + ':/usr/bin:/bin', 'LANG': 'en_US.UTF-8',
       'PYTHONHASHSEED': '0', 'PYTHONDONTWRITEBYTECODE': '1'}


def command(mode, root, **kwargs):
    return [sys.executable, str(HERE / 'runtime.py'), mode, '--root', str(root),
            *[v for key, value in kwargs.items() for v in ('--' + key, str(value))]]


def decode(stdout):
    return json.loads([line for line in stdout.splitlines() if line.startswith('{')][-1])


def save(proc, argv, stdout, stderr, label):
    log = RUN / (label + '.log')
    log.write_text(stdout + '\nSTDERR\n' + stderr)
    record = {'label': label, 'argv': [x.replace(str(HERE), '<spike>') for x in argv],
              'exit_code': proc.returncode, 'log': str(log.relative_to(HERE)),
              'stdout': stdout, 'stderr': stderr}
    RECORDS.append(record)
    return decode(stdout) if proc.returncode == 0 else None


def run(mode, root, label, env=None, expected=0, **kwargs):
    argv = command(mode, root, **kwargs)
    p = subprocess.run(argv, env=ENV | (env or {}), capture_output=True, text=True, timeout=35)
    result = save(p, argv, p.stdout, p.stderr, label)
    assert p.returncode == expected, (label, p.returncode, p.stderr)
    return result


def check(name, fn):
    if OPTIONS.case and name != OPTIONS.case:
        return
    try:
        detail = fn()
        CHECKS.append({'case': name, 'status': 'PASS', 'detail': detail})
        print('PASS', name, flush=True)
    except Exception as exc:
        CHECKS.append({'case': name, 'status': 'FAIL', 'error': repr(exc)})
        print('FAIL', name, repr(exc), flush=True)


def successful(locale):
    root = RUN / ('success-' + locale)
    data = run('start', root, 'success-' + locale, locale=locale)
    assert data['workflow_status'] == 'SUCCESS'
    assert data['result']['outcome'] == 'SUCCESS'
    assert len(data['ledger']['business']) == 1
    assert len(data['ledger']['provider_dispatches']) == 2
    assert data['result']['event_types'].count('TEXT_BLOCK_DELTA') == 2
    same = run('start', root, 'same-workflow-' + locale, locale=locale)
    assert same['result'] == data['result']
    assert len(same['ledger']['provider_dispatches']) == 2
    new = run('start', root, 'new-workflow-same-attempt-' + locale, locale=locale, workflow='workflow-2')
    assert new['result']['outcome'] == 'SUCCESS'
    assert len(new['ledger']['provider_dispatches']) == 2
    assert len(new['ledger']['business']) == 1
    return {'workflow_replays': 1, 'workflows': 2, 'model_dispatches': 2, 'business_receipts': 1,
            'text': data['result']['output']['text']}


def crash(point):
    root = RUN / point
    run('start', root, point + '-crash', env={'CJ002_FAULT': point}, expected=91)
    before = ledger.snapshot(root)
    data = run('recover', root, point + '-recover')
    unresolved = point in ('intent_before_send', 'during_call', 'after_provider_response')
    assert data['workflow_status'] == 'SUCCESS', data
    assert data['result']['outcome'] == ('UNKNOWN' if unresolved else 'SUCCESS'), data
    assert data['ledger']['probes'] == [{'label': 'prepare', 'count': 1}]
    if unresolved:
        assert len(data['ledger']['provider_dispatches']) == len(before['provider_dispatches'])
        assert not data['ledger']['business']
        assert data['ledger']['attempts'][0]['state'] == 'UNKNOWN'
        new = run('start', root, point + '-new-workflow', workflow='workflow-2')
        assert new['result']['outcome'] == 'UNKNOWN'
        assert len(new['ledger']['provider_dispatches']) == len(before['provider_dispatches'])
    else:
        assert len(data['ledger']['provider_dispatches']) == 2
        assert len(data['ledger']['business']) == 1
    return {'before_dispatches': len(before['provider_dispatches']),
            'after_dispatches': len(data['ledger']['provider_dispatches']),
            'outcome': data['result']['outcome'], 'completed_prepare_executions': 1,
            'business_receipts': len(data['ledger']['business'])}


def paused_worker(root, point):
    argv = command('start', root)
    proc = subprocess.Popen(argv, env=ENV | {'CJ002_PAUSE': point}, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 15
    while not (root / ('paused-' + point)).exists():
        if proc.poll() is not None or time.monotonic() > deadline:
            proc.kill()
            stdout, stderr = proc.communicate()
            save(proc, argv, stdout, stderr, point + '-pause-failed')
            raise AssertionError('pause not reached')
        time.sleep(0.02)
    return proc, argv


def cancellation(point):
    root = RUN / ('cancel-' + point)
    proc, argv = paused_worker(root, point)
    try:
        ack = run('cancel', root, 'cancel-' + point + '-ack')
        assert ack['workflow_status'] == 'CANCELLED'
        (root / ('release-' + point)).write_text('release\n')
        stdout, stderr = proc.communicate(timeout=30)
        data = save(proc, argv, stdout, stderr, 'cancel-' + point + '-result')
        assert data['workflow_status'] == 'CANCELLED', data
        assert data['result']['outcome'] != 'SUCCESS', data
        expected_business = 0 if point == 'inflight_model' else 1
        expected_dispatches = 2 if point == 'before_publish' else 1
        assert len(data['ledger']['business']) == expected_business
        assert len(data['ledger']['provider_dispatches']) == expected_dispatches
        inspect = run('inspect', root, 'cancel-' + point + '-readback')
        assert inspect['workflow_status'] == 'CANCELLED'
        assert len(inspect['ledger']['business']) == expected_business
        recovered = run('recover', root, 'cancel-' + point + '-restart')
        assert recovered['workflow_status'] == 'CANCELLED'
        assert recovered['ledger'] == inspect['ledger']
        return {'status': 'CANCELLED', 'business_receipts': expected_business,
                'model_dispatches': expected_dispatches, 'after_restart': 'CANCELLED'}
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()


def sigkill():
    root = RUN / 'sigkill'
    proc, argv = paused_worker(root, 'before_model_step')
    proc.kill()
    stdout, stderr = proc.communicate(timeout=5)
    save(proc, argv, stdout, stderr, 'sigkill-killed')
    assert proc.returncode == -9
    data = run('recover', root, 'sigkill-recovered')
    assert data['result']['outcome'] == 'SUCCESS'
    assert data['ledger']['probes'] == [{'label': 'prepare', 'count': 1}]
    assert len(data['ledger']['provider_dispatches']) == 2
    return {'kill_signal': 9, 'recovered': True, 'completed_prepare_executions': 1}


def failed_scenario(scenario, expected, count):
    data = run('start', RUN / scenario, scenario, scenario=scenario)
    assert data['result']['outcome'] == expected, data
    assert len(data['ledger']['provider_dispatches']) == count
    if scenario == 'tool_failure':
        assert not data['ledger']['business']
    if scenario == 'bad_structure':
        assert data['result']['reason'] == 'invalid_structured_output'
        assert len(data['ledger']['business']) == 1  # partial effect stays visible
    return {'workflow_status': data['workflow_status'], 'outcome': data['result']['outcome'],
            'reason': data['result'].get('reason'), 'business_receipts': len(data['ledger']['business'])}


def business_and_attempt_guards():
    root = RUN / 'guards'
    ledger.initialize(root)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        receipts = list(pool.map(lambda _: ledger.commit_business(root, 'user-a', 'same-action', 7), range(8)))
    assert all(r == receipts[0] for r in receipts)
    try:
        ledger.commit_business(root, 'user-a', 'same-action', 8)
        raise AssertionError('changed business input was accepted')
    except ValueError as exc:
        assert str(exc) == 'BUSINESS_INPUT_CONFLICT'
    ledger.commit_business(root, 'user-b', 'same-action', 8)
    assert len(ledger.snapshot(root)['business']) == 2
    assert ledger.begin_attempt(root, 'attempt-1', 'user-a', 'hash-a') is None
    for principal, digest in [('user-a', 'hash-b'), ('user-b', 'hash-a')]:
        try:
            ledger.begin_attempt(root, 'attempt-1', principal, digest)
            raise AssertionError('attempt identity conflict was accepted')
        except ValueError as exc:
            assert str(exc) == 'ATTEMPT_INPUT_CONFLICT'
    assert ledger.begin_attempt(root, 'attempt-1', 'user-a', 'hash-a')['outcome'] == 'UNKNOWN'
    return {'concurrent_same_business_actions': 8, 'user_a_receipts': 1,
            'user_b_receipts': 1, 'changed_input': 'CONFLICT', 'unresolved_attempt': 'UNKNOWN',
            'scope': 'local serialization only; not authentication/RLS proof'}


for locale in (('en', 'zh') if GROUP == 'all' else ()):
    check('agentscope-dbos-' + locale, lambda locale=locale: successful(locale))
for point in (('before_model_step', 'after_model_step', 'intent_before_send', 'during_call',
              'after_provider_response', 'after_attempt_receipt', 'after_business_commit') if GROUP == 'all' else ()):
    check('process-crash-' + point, lambda point=point: crash(point))
if GROUP == 'all':
    check('sigkill-between-steps', sigkill)
for point in ('inflight_model', 'after_business_step', 'before_publish'):
    check('cancel-' + point, lambda point=point: cancellation(point))
for scenario, expected, count in ([('timeout', 'UNKNOWN', 1), ('bad_structure', 'FAILED', 2), ('tool_failure', 'FAILED', 2)] if GROUP == 'all' else []):
    check(scenario, lambda s=scenario, e=expected, n=count: failed_scenario(s, e, n))
if GROUP == 'all':
    check('business-and-attempt-distinction', business_and_attempt_guards)

if not CHECKS:
    PARSER.error('no matching test case')

report = {'scope': 'local synthetic provider / real AgentScope+DBOS packages / fresh SQLite',
          'versions': {p: version(p) for p in ('agentscope', 'dbos', 'pydantic', 'openai')},
          'python': platform.python_version(), 'platform': platform.platform(),
          'real_provider': 'UNRUN', 'postgres': 'UNRUN', 'production': 'UNRUN',
          'source_sha256': {p: hashlib.sha256((HERE / p).read_bytes()).hexdigest()
                            for p in ('runtime.py', 'ledger.py', 'validate.py', 'pyproject.toml', 'uv.lock')},
          'checks': CHECKS, 'records': RECORDS}
report_path = RUN / 'report.json'
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
# Stable tracked evidence omits huge raw output but includes each subprocess log hash.
summary = {k: v for k, v in report.items() if k != 'records'}
summary['records'] = [{k: v for k, v in r.items() if k not in ('stdout', 'stderr')} |
                      {'log_sha256': hashlib.sha256((HERE / r['log']).read_bytes()).hexdigest()} for r in RECORDS]
summary['raw_report'] = str(report_path.relative_to(HERE))
prefix = OPTIONS.case or GROUP
(HERE / 'evidence' / (prefix + '-validation.json')).write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
(HERE / 'evidence' / (prefix + '-process-records.json')).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print('Report:', report_path, flush=True)
sys.exit(1 if any(c['status'] == 'FAIL' for c in CHECKS) else 0)
