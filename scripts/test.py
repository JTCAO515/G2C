"""Single entry for all non-PostgreSQL checks (ADR-0004). PostgreSQL suites: scripts/pg_suites.py.

Usage: uv run --locked python -B scripts/test.py
"""
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / 'backend'

# Domain pytest suites that need no database (feasibility/needs/trip run in pg_suites.py).
DOMAINS = ('agent', 'auth', 'cleanup', 'draft', 'fact', 'feedback', 'manual_edit', 'memory_jobs',
           'memory_withdrawal', 'message', 'place', 'run', 'usage')
# cj_api wire checks that need a PostgreSQL config run in pg_suites.py.
PG_WIRE_CHECKS = {'feasibility_wire_checks.py', 'needs_cohost_checks.py',
                  'memory_management_wire_checks.py', 'memory_cohost_checks.py'}
# Standalone check scripts (no database), run as `python <script>` from their tests directory.
STANDALONE = ('fact/tests/check_examples.py', 'fact/tests/independent_overflow_checks.py',
              'fact/tests/independent_time_checks.py', 'message/tests/auth_consumption.py',
              'message/tests/context_query_tests.py', 'place/tests/https_transport_checks.py',
              'place/tests/secret_body_controls.py', 'place/tests/secret_echo_checks.py',
              'place/tests/trip_projection_checks.py', 'run/tests/display_projected_checks.py',
              'run/tests/display_snapshot_checks.py', 'run/tests/original_usage_read_checks.py',
              'run/tests/usage_boundary_probe.py', 'run/tests/usage_composition_checks.py',
              'usage/tests/protected_status_checks.py', 'memory/tests/binding_checks.py',
              'memory/tests/typed_unit.py')
# Modules without a __main__ runner.
STANDALONE_MODULES = (('message/tests', 'history_context_tests'),)
CONTRACT_SCRIPTS = ('scripts/check_contract.py', 'contracts/auth/check.py', 'contracts/auth/check_email.py',
                    'contracts/auth/check_ui.py', 'contracts/message/check.py',
                    'contracts/message/check_list_cursor.py', 'contracts/message/check_message_cursor.py',
                    'contracts/message/check_send_permit.py',
                    'contracts/ui/check_contract.py')


def env():
    value = {k: v for k, v in os.environ.items() if not k.startswith(('PG', 'LIBPQ'))}
    value.update(CJ_ENV='local', PYTHONDONTWRITEBYTECODE='1')
    return value


def run(label, argv, cwd=ROOT, extra_path=None, executable=sys.executable):
    print(f'::group::{label}', flush=True)
    current = env()
    if extra_path:
        current['PYTHONPATH'] = str(extra_path)
    code = subprocess.run([executable, *argv], cwd=cwd, env=current).returncode
    print('::endgroup::', flush=True)
    return label, code


def main():
    pytest = ['-m', 'pytest', '-q', '-p', 'no:cacheprovider']
    results = [run('default entry failure propagation',
                   ['-B', '-m', 'unittest', '-v', 'scripts.test_test_entry'])]
    results.append(run('backend/tests', [*pytest, 'backend/tests']))
    results.append(run('deploy boundaries', [*pytest, 'deploy/tests'],
                       extra_path=os.pathsep.join((str(ROOT),str(ROOT/'scripts')))))
    results.append(run('Supabase M4 boundaries', [*pytest, 'scripts/test_supabase_m4.py'],extra_path=ROOT/'scripts'))
    tests = BACKEND / 'cj_api/tests'
    results.append(run('cj_api unit', ['-B', '-m', 'unittest', 'discover', '-s', '.', '-p', 'test_*.py'], tests, tests))
    for check in sorted(p.name for p in tests.glob('*_checks.py') if p.name not in PG_WIRE_CHECKS):
        results.append(run(f'cj_api {check}', ['-B', '-m', 'unittest', 'discover', '-s', '.', '-p', check], tests, tests))
    for domain in DOMAINS:
        results.append(run(f'backend/{domain}', [*pytest, 'tests'], BACKEND / domain))
    for script in STANDALONE:
        path = BACKEND / script
        results.append(run(f'backend/{script}', ['-B', path.name], path.parent, path.parent))
    for directory, module in STANDALONE_MODULES:
        results.append(run(f'backend/{directory}/{module}', ['-B', '-m', 'unittest', module],
                           BACKEND / directory, BACKEND / directory))
    results.append(run('evaluation/cj028', [*pytest, 'tests'], ROOT / 'evaluation/cj028', ROOT / 'evaluation/cj028'))
    results.append(run('eval/optimization', ['-B', '-m', 'unittest', '-v', 'eval.optimization.test_score']))
    results.append(run('eval/lio_simulated_user',
                       ['-B', '-m', 'unittest', 'discover', '-s', 'eval/lio_simulated_user/tests', '-v']))
    results.append(run('eval/lio_calendar_transitions',
                       [*pytest, 'eval/tests/test_lio_calendar_transitions.py']))
    results.append(run('tooling/datasets',
                       ['-B', '-m', 'unittest', 'discover', '-s', 'tooling/datasets',
                        '-t', '.', '-p', 'test_*.py', '-v']))
    # GEPA uses its accepted project lock and environment, not the production root dependencies.
    results.append(run('tooling/optimization',
                       ['run', '--project', 'tooling/optimization', '--locked', 'python',
                        '-B', '-m', 'unittest', '-v', 'tooling.optimization.test_optimization'],
                       extra_path=ROOT, executable='uv'))
    results.append(run('tooling/training preflight',
                       ['-B', '-m', 'unittest', 'discover', '-s', 'tooling/training',
                        '-p', 'test_*.py', '-v']))
    results.append(run('tooling/training F schema', ['-B', 'tooling/training/check_f_dataset.py', '-v']))
    results.append(run('ops/recovery-preflight', [*pytest, '.'], ROOT / 'ops/recovery-preflight'))
    results.append(run('contracts/api proposal', ['-B', '-m', 'unittest', 'contracts/api/check_trip_content_v2_schema_proposal.py']))
    results.append(run('contracts/trip structured3', ['-B', 'contracts/trip/check_structured_v3.py']))
    results.append(run('contracts/trip structured4', ['-B', 'contracts/trip/check_structured_v4.py']))
    results.append(run('contracts/message calendar2', ['-B', 'contracts/message/check_trip_v2.py']))
    for script in CONTRACT_SCRIPTS:
        results.append(run(script, ['-B', script]))
    results.append(run('openapi', ['-m', 'openapi_spec_validator', 'contracts/api/openapi.json']))
    failed = [label for label, code in results if code]
    print(f'{len(results) - len(failed)}/{len(results)} passed' + (f'; FAILED: {", ".join(failed)}' if failed else ''))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
