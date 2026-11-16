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
from . import checkpoint,demo_quota,local_postgres


def control():return Path(os.environ['CJ_DEPLOY_CONTROL'])
def heartbeat():return Path(os.environ['CJ_DEPLOY_HEARTBEAT'])/'worker.json'


def _runtime_gate(database, runtime):
    authorization()
    local_postgres.require_serving(control())
    with database._open_runtime_connection() as connection:
        release=checkpoint.require_release(connection,control())
    if runtime is not None and local_database_target():
        marker=checkpoint.verified(control()/'demo-schema52.json')
        if (marker['state']!='COMPLETE' or marker['lineage']!=release['lineage']
                or runtime.context.current.meter.budget!=demo_quota.APPROVED_BUDGET
                or marker['quota_policy_sha256']!=demo_quota.policy_digest(runtime.context_path.read_text(),
                    demo_quota.APPROVED_BUDGET)):
            raise ValueError('HK Demo quota cutover incomplete')
        if checkpoint.versions()[-1]>=53:
            marker=checkpoint.verified(control()/'demo-schema53.json')
            if marker['state']!='COMPLETE' or marker['lineage']!=release['lineage']:
                raise ValueError('HK wire-origin cutover incomplete')
        if checkpoint.versions()[-1]>=54:
            marker=checkpoint.verified(control()/'demo-schema54.json')
            if marker['state']!='COMPLETE' or marker['lineage']!=release['lineage']:
                raise ValueError('HK exploration-origin cutover incomplete')
        if checkpoint.versions()[-1]>=55:
            marker=checkpoint.verified(control()/'demo-schema55.json')
            if marker['state']!='COMPLETE'or marker['lineage']!=release['lineage']:
                raise ValueError('HK native4 accounting cutover incomplete')


def ready(database, runtime=None):
    try:
        _runtime_gate(database,runtime)
        state=json.loads(heartbeat().read_bytes())
        if set(state)!={'at','component','status'} or not 0<=time.time()-state['at']<15:return 'worker_heartbeat_stale'
        return None if state['status']=='ready' else state['component']+'_unavailable'
    except psycopg.Error:return 'database_unavailable'
    except (OSError,ValueError,KeyError,TypeError,CompositionUnavailable):return 'deployment_gate_unavailable'


def api(runtime):
    app=runtime.app();database=runtime.database()
    @app.middleware('http')
    async def deployment_gate(request,call_next):
        if request.url.path=='/health/live':return JSONResponse({'status':'alive'})
        reason=await run_in_threadpool(ready,database,runtime)
        if reason is not None:request.state.access_gate=reason
        if request.url.path=='/health/ready':
            return JSONResponse({'status':'ready' if reason is None else 'unavailable','component':reason},status_code=200 if reason is None else 503)
        if reason is not None:return JSONResponse({'error':'deployment_unavailable'},status_code=503)
        return await call_next(request)
    # Outermost: sees gate 503s too. Content-free; see deploy/hk/access_log.py (#1036).
    from .access_log import AccessLog,Sink
    app.add_middleware(AccessLog,sink=Sink())
    import uvicorn
    uvicorn.run(app,host='0.0.0.0',port=8765,access_log=False)


@contextmanager
def worker_pulse():
    stop=threading.Event()
    def pulse():
        while not stop.is_set():
            path=heartbeat();temporary=path.with_suffix('.tmp')
            temporary.write_text(json.dumps(dict(at=time.time(),component='worker',status='ready')));temporary.replace(path)
            stop.wait(3)
    thread=threading.Thread(target=pulse,name='g2c-worker-pulse',daemon=True);thread.start()
    try:yield
    finally:stop.set();thread.join()


def worker(runtime, *, tool_evidence=None,runtime_manifest=None,app_smoke_manifest=None):
    from .demo_login import signing_socket
    with signing_socket(runtime):
        _run_worker(runtime, tool_evidence=tool_evidence,runtime_manifest=runtime_manifest,app_smoke_manifest=app_smoke_manifest)


def _run_worker(runtime, *, tool_evidence=None,runtime_manifest=None,app_smoke_manifest=None):
    # Missing transferred journal is a configuration failure, never a new quota.
    if not (Path.home()/'.local/share/g2c/m4-real-services/m4-outflows.sqlite').is_file():
        raise ValueError('original_shared_authorization_journal_required')
    services=RealServices.from_environment(runtime.auth,authorization_guard=authorization,demo_subjects=runtime.demo_subjects,national_subjects=runtime.demo_subjects)
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
                                     if runtime.demo_subjects else frozenset()),controlled_probe=binding,
        tool_evidence=tool_evidence)
    database=runtime.database()
    lio_confirmation = None
    if runtime.demo_subjects and 'CJ_BETA_CONFIRMATION_B64' in os.environ:
        lio_confirmation = ConfirmationSigner(decoded('CJ_BETA_CONFIRMATION_B64', length=32))
    if app_smoke_manifest is not None:
        from cj_api.app_smoke_capture import AppSmokeCapture
        smoke=AppSmokeCapture(app_smoke_manifest,runtime.demo_subjects,tools.registrations,database,services.model.authorization)
        tools.tool_evidence=smoke.evidence
        return _worker_loop(runtime,services,tools,database,lio_confirmation,smoke,smoke_capture=smoke)
    if runtime_manifest is None:
        return _worker_loop(runtime,services,tools,database,lio_confirmation)
    from cj_api.runtime_worker_bindings import RuntimeWorkerBindings
    from cj_api.runtime_rpc import runtime_socket
    from cj_api.tool_evidence import ToolEvidence
    bindings=RuntimeWorkerBindings(runtime_manifest,runtime,services,tools,confirmation_signer=lio_confirmation)
    evidence=ToolEvidence.load(bindings.evidence_manifest,runtime.demo_subjects,runtime_selection=bindings.selects)
    bindings.attach_evidence(evidence)
    if tool_evidence is not None:
        from cj_api.runtime_evidence_windows import EvidenceWindows
        tools.tool_evidence=EvidenceWindows(evidence,tool_evidence)
    with runtime_socket(bindings,Path('/run/g2c-demo/runtime.sock')):
        return _worker_loop(runtime,services,tools,database,lio_confirmation,bindings)


def _worker_loop(runtime,services,tools,database,lio_confirmation,bindings=None,*,smoke_capture=None):
    from cj_api.rejected_intake_capture import RejectedIntakeSink,use_rejected_intake_sink
    rejected=RejectedIntakeSink('/rejected-intakes')
    rejected.prune()
    while True:
        component='deployment_gate';status='unavailable'
        try:
            _runtime_gate(database,runtime)
            rejected.prune()
            with use_rejected_intake_sink(rejected),worker_pulse():
                outcomes=run_worker.run_once(database,services.model,runtime.auth,tools_configuration=tools,real_services=services,account_admission=True,
                    hk_beta_b_run_credential=True,
                    hk_assembly_scopes=frozenset(scope_for(ISSUER,subject) for subject in runtime.assembly_subjects),
                    hk_demo_scopes=frozenset(scope_for(ISSUER,subject) for subject in runtime.demo_subjects),
                    lio_confirmation=lio_confirmation,
                    hk_assembly_run_credential_scopes=frozenset(
                        scope_for(ISSUER,subject) for subject in runtime.assembly_run_credential_subjects),
                    memory_configuration_for_scope=None if runtime.memory_runtime is None else runtime.memory_configuration_for_scope,
                    runtime_registrations_for_run=None if bindings is None else bindings.registrations,
                    runtime_reflection=None if bindings is None else bindings.reflection,
                    runtime_exit_observer_for_run=None if bindings is None else bindings.exit_observer)
            if smoke_capture is not None:
                from cj_usage.metered_exit import BudgetUnknown
                try:smoke_capture.completed(outcomes)
                except (OSError,ValueError,BudgetUnknown):
                    # A missing witness blocks the smoke verdict. It must not
                    # rewrite a terminal RUN or disrupt unrelated App users.
                    print('ALERT app_smoke_producer_witness_unavailable',file=sys.stderr,flush=True)
            for outcome in outcomes:
                if outcome.status in ('unknown','failed'):
                    print('ALERT run_'+outcome.status+' run_id='+outcome.run_id,file=sys.stderr,flush=True)
            component='worker';status='ready'
        except psycopg.Error:component='database'
        except (OSError,ValueError,CompositionUnavailable):pass
        if status!='ready':print('ALERT '+component+'_unavailable',file=sys.stderr,flush=True)
        path=heartbeat();temporary=path.with_suffix('.tmp')
        temporary.write_text(json.dumps(dict(at=time.time(),component=component,status=status)));temporary.replace(path)
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
    parser.add_argument('--tool-evidence-manifest',type=Path)
    parser.add_argument('--runtime-manifest',type=Path)
    parser.add_argument('--app-smoke-manifest',type=Path)
    args=parser.parse_args();runtime=None
    if args.tool_evidence_manifest is not None and args.command!='worker':
        parser.error('tool evidence is available only on the existing synthetic worker')
    if args.runtime_manifest is not None and args.command!='worker':
        parser.error('runtime composition is available only on the existing synthetic worker')
    if args.app_smoke_manifest is not None and (args.command!='worker' or args.runtime_manifest is not None
                                               or args.tool_evidence_manifest is not None):
        parser.error('App smoke capture is an exclusive worker composition')
    try:
        load_secret_environment(args.command)
        audit=logging.getLogger('cj_usage.audit');audit.setLevel(logging.INFO)
        audit.addHandler(logging.StreamHandler(sys.stderr));audit.propagate=False
        runtime=Runtime.load('/tmp/g2c-beta',worker=args.command=='worker')
        if args.command=='worker':
            from cj_api.tool_evidence import ToolEvidence
            evidence=(None if args.tool_evidence_manifest is None else
                      ToolEvidence.load(args.tool_evidence_manifest,runtime.demo_subjects))
            worker(runtime,tool_evidence=evidence,runtime_manifest=args.runtime_manifest,app_smoke_manifest=args.app_smoke_manifest)
        else:
            dict(migrate=initialize,api=api)[args.command](runtime)
    except (OSError,ValueError,KeyError,CompositionUnavailable,psycopg.Error):
        print('ALERT beta_startup_configuration_or_database_unavailable',file=sys.stderr)
        raise SystemExit(1) from None
    finally:
        if runtime is not None:runtime.close()


if __name__=='__main__':main()
