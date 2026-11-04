"""Explicit local container composition. Existing local security gates remain."""
import argparse
import json
import os
from pathlib import Path
import sys
import time

import psycopg
from fastapi.responses import JSONResponse
from cj_agent.provider import FakeProvider, ProviderFailed
from cj_api.local_app import LocalDatabase, app_from_environment, local_conninfo
from cj_api.local_run_context import load_run_context
from cj_strict_json import reject_duplicates
import migrate
import run_worker


def control():
    return Path(os.environ['CJ_DEPLOY_CONTROL'])


def write_state(name, value):
    path = control() / name
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, separators=(',', ':')))
    temporary.replace(path)


def schema(connection):
    if migrate.applied(connection) != [m['version'] for m in migrate.load()]:
        raise ValueError('application_schema_mismatch')


def require_configuration():
    if os.environ.get('CJ_ENV') != 'local' or os.environ.get('CJ_DEPLOY_PROVIDER') not in ('fake', 'fake-unavailable'):
        raise ValueError('explicit_local_fake_provider_required')
    for name in ('CJ_LOCAL_CONNINFO', 'CJ_LOCAL_AUTH_DIR', 'CJ_LOCAL_RUN_CONTEXT', 'CJ_DEPLOY_CONTROL'):
        if not os.environ.get(name):
            raise ValueError('missing_' + name)
    load_run_context(os.environ['CJ_LOCAL_RUN_CONTEXT'])


def ready():
    try:
        require_configuration()
        # This out-of-band marker is never part of a database backup.
        from .recovery import require_release
        require_release(local_conninfo(os.environ['CJ_LOCAL_CONNINFO']), control())
        with psycopg.connect(**local_conninfo(os.environ['CJ_LOCAL_CONNINFO']), autocommit=True) as conn:
            schema(conn)
        state = json.loads((control() / 'worker.json').read_text(),
                           object_pairs_hook=reject_duplicates(ValueError, 'duplicate heartbeat field'))
        if set(state) != {'at', 'component', 'status'} or not 0 <= time.time() - state['at'] < 15:
            return 'worker_heartbeat_stale'
        if state['status'] != 'ready':
            return state['component'] + '_unavailable'
        if json.loads((control() / 'model.json').read_text())['status'] != 'ready':
            return 'model_unavailable'
        return None
    except psycopg.Error:
        return 'database_unavailable'
    except (OSError, ValueError, KeyError, TypeError):
        return 'deployment_gate_unavailable'


def api():
    require_configuration()
    app = app_from_environment()

    @app.middleware('http')
    async def deployment_gate(request, call_next):
        if request.url.path == '/health/live':
            return JSONResponse({'status': 'alive'})
        reason = ready()
        if request.url.path == '/health/ready':
            return JSONResponse({'status': 'ready' if reason is None else 'unavailable', 'component': reason},
                                status_code=200 if reason is None else 503)
        if reason is not None:
            return JSONResponse({'error': 'deployment_unavailable'}, status_code=503)
        return await call_next(request)

    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8765, access_log=False)


def worker():
    require_configuration()
    database = LocalDatabase(os.environ['CJ_LOCAL_CONNINFO'],
                             run_context=load_run_context(os.environ['CJ_LOCAL_RUN_CONTEXT']))
    class ObservedProvider(FakeProvider):
        def stream(self, *args, **kwargs):
            try:
                if os.environ['CJ_DEPLOY_PROVIDER'] == 'fake-unavailable':
                    raise ProviderFailed('synthetic_model_unavailable')
                yield from super().stream(*args, **kwargs)
            except ProviderFailed:
                write_state('model.json', {'status': 'unavailable'})
                print('ALERT model_unavailable', file=sys.stderr, flush=True)
                raise
    model = ObservedProvider()
    write_state('model.json', {'status': 'ready' if os.environ['CJ_DEPLOY_PROVIDER'] == 'fake' else 'unavailable'})
    if os.environ['CJ_DEPLOY_PROVIDER'] == 'fake-unavailable':
        print('ALERT model_unavailable', file=sys.stderr, flush=True)
    while True:
        try:
            from .recovery import require_release
            require_release(local_conninfo(os.environ['CJ_LOCAL_CONNINFO']), control())
            with psycopg.connect(**local_conninfo(os.environ['CJ_LOCAL_CONNINFO']), autocommit=True) as conn:
                schema(conn)
            run_worker.run_once(database, model, os.environ['CJ_LOCAL_AUTH_DIR'])
            write_state('worker.json', dict(at=time.time(), component='worker', status='ready'))
        except psycopg.Error:
            write_state('worker.json', dict(at=time.time(), component='database', status='unavailable'))
            print('ALERT database_unavailable', file=sys.stderr, flush=True)
        except (OSError, ValueError):
            write_state('worker.json', dict(at=time.time(), component='deployment_gate', status='unavailable'))
            print('ALERT deployment_gate_unavailable', file=sys.stderr, flush=True)
        time.sleep(1)


def initialize():
    require_configuration()
    path = os.environ['CJ_DEPLOY_MIGRATION_CONNINFO']
    with migrate.connect(path) as conn:
        migrations = migrate.load()
        old = migrate.applied(conn)
        if any(version > migrations[-1]['version'] for version in old):
            raise ValueError('application_schema_mismatch')
        migrate.up(conn, migrations, migrations[-1]['version'])
    if not (control() / 'latest.json').exists():
        from .recovery import bootstrap
        bootstrap(local_conninfo(path), control())
    from local_run_context import provision_budget
    context = load_run_context(os.environ['CJ_LOCAL_RUN_CONTEXT'])
    for subject in run_worker.invited_subjects(os.environ['CJ_LOCAL_AUTH_DIR']):
        provision_budget(path, context, subject)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=('migrate', 'api', 'worker'))
    args = parser.parse_args()
    try:
        {'migrate': initialize, 'api': api, 'worker': worker}[args.command]()
    except (ValueError, KeyError, OSError, psycopg.Error):
        print('ALERT startup_configuration_or_database_unavailable', file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
