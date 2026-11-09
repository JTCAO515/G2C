"""Explicit Hong Kong synthetic test composition; no production defaults."""
import argparse
import json
import logging
import os
from pathlib import Path
import re
import sys
import time
import threading
from contextlib import contextmanager

import psycopg
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

import migrate
import run_worker
from cj_api.composition import CompositionUnavailable
from cj_api.local_app import ISSUER,scope_for
from cj_api.real_services import RealServices,RealTools
from cj_trip.confirmation import ConfirmationSigner
from local_run_context import provision_budget_connection
from .configuration import ASSEMBLY_PROBE_MESSAGE,MODEL_STREAM_SUBJECT,Runtime,authorization,decoded,load_secret_environment,local_database_target
from . import checkpoint,local_postgres


def control():return Path(os.environ['CJ_DEPLOY_CONTROL'])
def heartbeat():return Path(os.environ['CJ_DEPLOY_HEARTBEAT'])/'worker.json'


def ready(database, *, require_lio=False):
    try:
        authorization()
        local_postgres.require_serving(control())
        with database._open_runtime_connection() as connection:checkpoint.require_release(connection,control())
        state=json.loads(heartbeat().read_bytes())
        fields = {'at','component','status'}
        if (set(state) not in (fields, fields | {'lio_ready'})
                or type(state.get('lio_ready', False)) is not bool
                or not 0<=time.time()-state['at']<15):
            return 'worker_heartbeat_stale'
        if state['status'] != 'ready':
            return state['component']+'_unavailable'
        if require_lio and not state.get('lio_ready', False):
            return 'lio_unavailable'
        return None
    except psycopg.Error:return 'database_unavailable'
    except (OSError,ValueError,KeyError,TypeError,CompositionUnavailable):return 'deployment_gate_unavailable'


def api(runtime):
    app=runtime.app();database=runtime.database()
    @app.middleware('http')
    async def deployment_gate(request,call_next):
        if request.url.path=='/health/live':return JSONResponse({'status':'alive'})
        lio = request.url.path.startswith('/v1/lio/')
        reason=await run_in_threadpool(ready,database,require_lio=lio)
        if request.url.path=='/health/ready':
            return JSONResponse({'status':'ready' if reason is None else 'unavailable','component':reason},status_code=200 if reason is None else 503)
        if reason is not None:
            if lio:
                return JSONResponse({'failure':'unavailable'},status_code=503,headers={'Cache-Control':'no-store'})
            return JSONResponse({'error':'deployment_unavailable'},status_code=503)
        return await call_next(request)
    import uvicorn
    uvicorn.run(app,host='0.0.0.0',port=8765,access_log=False)


def _publish_worker_state(component, status, lio_ready):
    path=heartbeat();temporary=path.with_suffix('.tmp')
    state = dict(at=time.time(),component=component,status=status)
    if lio_ready:
        state['lio_ready'] = True
    temporary.write_text(json.dumps(state));temporary.replace(path)


@contextmanager
def worker_pulse(*, lio_ready=False):
    stop=threading.Event()
    def pulse():
        while not stop.is_set():
            _publish_worker_state('worker', 'ready', lio_ready)
            stop.wait(3)
    thread=threading.Thread(target=pulse,name='g2c-worker-pulse',daemon=True);thread.start()
    try:yield
    finally:stop.set();thread.join()


def worker(runtime):
    from .demo_login import signing_socket
    with signing_socket(runtime):
        _run_worker(runtime)


def _run_worker(runtime):
    # Missing transferred journal is a configuration failure, never a new quota.
    if not (Path.home()/'.local/share/g2c/m4-real-services/m4-outflows.sqlite').is_file():
        raise ValueError('original_shared_authorization_journal_required')
    services=RealServices.from_environment(runtime.auth,authorization_guard=authorization,demo_subjects=runtime.demo_subjects)
    with services.model.authorization.connect() as journal:services.model.authorization.require_producer(journal)
    probe=os.environ.get(ASSEMBLY_PROBE_MESSAGE)
    binding=None
    if probe is not None:
        if (not local_database_target() or not runtime.assembly_subjects
                or runtime.assembly_run_credential_subjects!=runtime.assembly_subjects
                or re.fullmatch(r'hk-674-jt-20261109-[a-f0-9]{8}',probe) is None):
            raise ValueError('explicit authorized HK assembly probe required')
        subject=next(s for s in runtime.assembly_subjects if s.endswith('-zh'))
        binding=(scope_for(ISSUER,subject),probe)
    tools=RealTools(services,streaming_subject=os.environ.get(MODEL_STREAM_SUBJECT),
        assembly_streaming_subjects=runtime.assembly_model_stream_subjects,
        buffered_streaming_subjects=(runtime.assembly_model_stream_subjects|runtime.demo_subjects
                                     if runtime.demo_subjects else frozenset()),controlled_probe=binding)
    database=runtime.database()
    lio_confirmation = None
    if runtime.demo_subjects and 'CJ_BETA_CONFIRMATION_B64' in os.environ:
        lio_confirmation = ConfirmationSigner(decoded('CJ_BETA_CONFIRMATION_B64', length=32))
    lio_ready = lio_confirmation is not None
    _publish_worker_state('deployment_gate', 'unavailable', False)
    while True:
        component='deployment_gate';status='unavailable'
        try:
            authorization()
            local_postgres.require_serving(control())
            with database._open_runtime_connection() as connection:checkpoint.require_release(connection,control())
            with worker_pulse(lio_ready=lio_ready):
                outcomes=run_worker.run_once(database,services.model,runtime.auth,tools_configuration=tools,real_services=services,account_admission=True,
                    hk_beta_b_run_credential=True,
                    hk_assembly_scopes=frozenset(scope_for(ISSUER,subject) for subject in runtime.assembly_subjects),
                    hk_demo_scopes=frozenset(scope_for(ISSUER,subject) for subject in runtime.demo_subjects),
                    lio_confirmation=lio_confirmation,
                    hk_assembly_run_credential_scopes=frozenset(
                        scope_for(ISSUER,subject) for subject in runtime.assembly_run_credential_subjects),
                    memory_configuration_for_scope=None if runtime.memory_runtime is None else runtime.memory_configuration_for_scope)
            for outcome in outcomes:
                if outcome.status in ('unknown','failed'):
                    print('ALERT run_'+outcome.status+' run_id='+outcome.run_id,file=sys.stderr,flush=True)
            component='worker';status='ready'
        except psycopg.Error:component='database'
        except (OSError,ValueError,CompositionUnavailable):pass
        if status!='ready':print('ALERT '+component+'_unavailable',file=sys.stderr,flush=True)
        _publish_worker_state(component, status, lio_ready and status == 'ready')
        time.sleep(1)


def initialize(runtime):
    with checkpoint.operator() as (connection,_):
        if local_database_target():
            checkpoint.require_release(connection,control())
            return
        if (control()/'release.json').exists():checkpoint.require_release(connection,control())
        migrate.up(connection,migrate.load(),checkpoint.versions()[-1])
    def seed(connection):
        with connection.transaction():
            for subject in run_worker.invited_subjects(runtime.auth):provision_budget_connection(connection,runtime.context,subject)
    checkpoint.bootstrap(control(),seed)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('command',choices=['migrate','api','worker'])
    args=parser.parse_args();runtime=None
    try:
        load_secret_environment(args.command)
        audit=logging.getLogger('cj_usage.audit');audit.setLevel(logging.INFO)
        audit.addHandler(logging.StreamHandler(sys.stderr));audit.propagate=False
        runtime=Runtime.load('/tmp/g2c-beta',worker=args.command=='worker')
        dict(migrate=initialize,api=api,worker=worker)[args.command](runtime)
    except (OSError,ValueError,KeyError,CompositionUnavailable,psycopg.Error):
        print('ALERT beta_startup_configuration_or_database_unavailable',file=sys.stderr)
        raise SystemExit(1) from None
    finally:
        if runtime is not None:runtime.close()


if __name__=='__main__':main()
