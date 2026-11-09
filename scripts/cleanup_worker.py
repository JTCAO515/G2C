"""Explicit local-only account recovery and daily 90-day diagnostic maintenance.

Use the same explicit private PG/auth/quota/cleanup configuration as the local
host. No production adapter, real provider or new key/account is provisioned.
"""
import argparse,json,os,time
from pathlib import Path

if os.environ.get('CJ_ENV')!='local':raise SystemExit('CJ_ENV=local is required')

from cj_api.local_app import LocalDatabase,scope_for
from cj_api.local_cleanup import Runtime,load_configuration
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import checker_for
from cj_auth.interfaces import AdmissionStatus
from cj_cleanup.gateway_store import GatewayStore
from cj_cleanup.maintenance import maintain_diagnostics
from run_worker import invited_subjects
import dev_auth


def step(runtime,checker,principal):
    binding=runtime.bind(principal)
    operation=GatewayStore(binding.store).active_operation()
    if operation is not None:return runtime.host_gateway(checker).resume(binding.store.subject_digest,operation)
    return maintain_diagnostics(binding.store,binding.owner_scope,runtime.registry,runtime.configuration.clock)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--conninfo-json',type=Path,required=True)
    parser.add_argument('--auth-dir',type=Path,required=True)
    parser.add_argument('--cleanup-config',type=Path,required=True)
    parser.add_argument('--run-context',type=Path)
    parser.add_argument('--interval',type=int,default=60)
    parser.add_argument('--once',action='store_true')
    args=parser.parse_args()
    if not 1<=args.interval<=3600:parser.error('interval must be 1..3600 seconds')
    context=load_run_context(args.run_context) if args.run_context else None
    runtime=Runtime(LocalDatabase(args.conninfo_json,run_context=context),load_configuration(args.cleanup_config),scope_for)
    checker=checker_for(args.auth_dir)
    while True:
        failure=None
        for subject in sorted(invited_subjects(args.auth_dir)):
            # One subject's failure must not stop recovery or maintenance for the
            # others; the first failure is still raised after this pass.
            try:
                # Actual local signed principal; invitation/current identity remain
                # required for this operator-owned synthetic local host worker.
                decision=checker.check(dev_auth.token(args.auth_dir,subject,5))
                if decision.status is not AdmissionStatus.ALLOWED:raise SystemExit('local maintenance identity unavailable')
                result=step(runtime,checker,decision.principal)
            except (Exception,SystemExit) as error:
                if failure is None:failure=error
                continue
            # No tokens, plaintext scope or user content in operational output.
            print(json.dumps({k:result[k] for k in ('operation_id','status','reason') if k in result}),flush=True)
        if failure is not None:raise failure
        if args.once:return
        time.sleep(args.interval)


if __name__=='__main__':main()
