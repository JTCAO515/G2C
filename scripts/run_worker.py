"""Host worker for CJ_ENV=local: MESSAGE pending deliveries -> model -> RUN events (P2a).

  run_worker.py --conninfo-json conn.json [--once] [--real]

The formal worker requires explicit quota context. Only deterministic FakeProvider
is enabled; --real refuses before reading credentials. Interrupted work is queried
by its original identity and never automatically resent.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import logging
import time

if os.environ.get('CJ_ENV') != 'local':
    raise SystemExit('CJ_ENV=local is required')

from cj_agent.draft import DraftPublisher
from cj_agent.provider import FakeProvider, ProviderFailed
from cj_agent.worker import RunWorker, original_context_valid
from cj_api.local_app import LocalDatabase, ISSUER, scope_for, travel_configuration
from cj_api.composition import CompositionUnavailable
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import LocalBudgetRouter, checker_for, needs_lease_for
from cj_auth.interfaces import AdmissionStatus
from cj_needs.revision_lease import LeaseUnavailable
from cj_memory.local_runtime import load_runtime_configuration
from cj_memory.runtime import RuntimeDenied, RuntimeUnknown
from cj_memory.typed_runtime import TypedRuntimeConfiguration
import dev_auth
from cj_message.domain import Service as MessageService
from cj_run.core import Service as RunService, Denied


def provider(real):
    if real: raise ProviderFailed('no approved metered real provider adapter')
    return FakeProvider()


def invited_subjects(auth_dir):
    subjects = json.loads((Path(auth_dir) / 'invited.json').read_text())
    if type(subjects) is not list or any(type(s) is not str or not s.strip() for s in subjects):
        raise ValueError('explicit local invitation list required')
    return set(subjects)


def scopes(database, auth_dir):
    # Enumerate only the operator-owned invitation source, never all tenants via
    # an initialization/superuser connection. Each query has its own scoped role.
    result = []
    for subject in sorted(invited_subjects(auth_dir)):
        scope = scope_for(ISSUER, subject)
        with database.connect(scope) as conn:
            if conn.execute('SELECT 1 FROM cj_message_delivery WHERE NOT acknowledged LIMIT 1').fetchone():
                result.append(scope)
    return result


class InvitedProvider:
    def __init__(self, model, auth_dir, subject):
        self.model, self.auth_dir, self.subject = model, auth_dir, subject

    def stream(self, *args, **kwargs):
        # Repeat at each model outflow, including structured-draft generation.
        # A failed/unknown invitation read raises before calling the provider.
        if self.subject not in invited_subjects(self.auth_dir):
            raise ProviderFailed('local invitation denied before dispatch')
        yield from self.model.stream(*args, **kwargs)


def require_memory_configuration(database, scope, configuration):
    typed=type(configuration) is TypedRuntimeConfiguration
    travel=database.travel_profile(scope)
    if travel and configuration is not None and not typed:
        raise RuntimeDenied('travel execution requires explicit typed memory configuration')
    with database.connect(scope) as conn:
        exists=conn.execute('SELECT 1 FROM cj_memory_scope WHERE scope=%s',(scope,)).fetchone() is not None
    if exists and configuration is None:
        raise RuntimeDenied('existing memory requires explicit runtime configuration')


def _worker_for_scope(database,model,auth_dir,scope,checker, *, memory_configuration=None,tools_configuration=None):
    database.require_execution(scope)
    require_memory_configuration(database, scope, memory_configuration)
    if tools_configuration is not None and (database.run_context is None or database.run_context.version!='CJ-LOCAL-RUN@2'):
        raise CompositionUnavailable('tools require the registered M2 exit')
    messages = MessageService(database.message_repository(scope), new_run_id=lambda: None)
    subject = scope.removeprefix('local:' + ISSUER + ':')
    def token(subject=subject): return dev_auth.token(Path(auth_dir),subject,5)
    memory_credential = token() if memory_configuration is not None else None
    def memory_admit(credential=memory_credential, scope=scope):
        decision = checker.check(credential)
        if decision.status is AdmissionStatus.UNKNOWN:
            raise RuntimeUnknown('memory admission unknown')
        if decision.status is not AdmissionStatus.ALLOWED or scope_for(
                decision.principal.issuer, decision.principal.subject) != scope:
            raise RuntimeDenied('memory admission denied')
        return decision.principal
    message_context=None
    if database.travel_profile(scope) or type(memory_configuration) is TypedRuntimeConfiguration:
        from cj_message.travel_reference import MessageContextAuthority
        credential=memory_credential if type(memory_configuration) is TypedRuntimeConfiguration else token()
        def travel_admit():
            decision=checker.check(credential)
            if decision.status is AdmissionStatus.UNKNOWN:
                raise LeaseUnavailable('travel admission unknown')
            if (decision.status is not AdmissionStatus.ALLOWED
                    or scope_for(decision.principal.issuer,decision.principal.subject)!=scope):
                raise Denied('travel admission denied')
            return decision.principal
        message_context=MessageContextAuthority(database.message_repository(scope),travel_admit)
    if type(memory_configuration) is TypedRuntimeConfiguration:
        memory=memory_configuration.bind(database,scope,subject,memory_admit,message_context=message_context)
    else:
        memory=(memory_configuration.bind(database,scope,subject,memory_admit)
                if memory_configuration is not None else None)
    def valid(binding, messages=messages, subject=subject, token=token):
        if message_context is not None:
            return message_context.valid(binding)
        database.require_execution(binding.scope,binding)
        credential=token()
        first=checker.check(credential)
        if first.status is AdmissionStatus.UNKNOWN: raise LeaseUnavailable('worker admission unknown')
        if first.status is not AdmissionStatus.ALLOWED: return False
        if scope_for(first.principal.issuer,first.principal.subject)!=binding.scope: return False
        original=original_context_valid(binding,messages,lambda:True)
        last=checker.check(credential)
        if last.status is AdmissionStatus.UNKNOWN: raise LeaseUnavailable('worker admission unknown')
        return original is True and last.status is AdmissionStatus.ALLOWED and last.principal==first.principal
    runs = RunService(database.run_repository(scope),valid=valid)
    drafts = DraftPublisher(database.trip_repository(scope))
    return RunWorker(scope=scope, messages=messages, runs=runs, provider=model, drafts=drafts,
        memory=memory,
        message_context=message_context,
        tools=tools_configuration,
        execution_guard=lambda binding:database.require_execution(binding.scope,binding),
        needs_lease=needs_lease_for(database,checker,token),
        budget_exit=(LocalBudgetRouter(database) if tools_configuration is None else
                     LocalBudgetRouter(database,registrations=tools_configuration.registrations)))


def run_once(database, model, auth_dir, *, memory_configuration=None,tools_configuration=None):
    pending_scopes=scopes(database,auth_dir)
    if not pending_scopes: return []
    if database.run_context is None:
        raise CompositionUnavailable('explicit run context required before execution')
    if not isinstance(model,FakeProvider):
        raise ProviderFailed('configured local context permits only FakeProvider')
    checker=checker_for(Path(auth_dir))
    results = []
    for scope in pending_scopes:
        results += _worker_for_scope(database,model,auth_dir,scope,checker,
                                     memory_configuration=memory_configuration,tools_configuration=tools_configuration).process()
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--conninfo-json', type=Path, required=True)
    parser.add_argument('--auth-dir', type=Path, default=os.environ.get('CJ_LOCAL_AUTH_DIR'))
    parser.add_argument('--run-context', type=Path, default=os.environ.get('CJ_LOCAL_RUN_CONTEXT'))
    parser.add_argument('--memory-run-policy', type=Path, default=os.environ.get('CJ_LOCAL_MEMORY_RUN_POLICY'))
    parser.add_argument('--travel-context',choices=['message-travel.1'],default=os.environ.get('CJ_LOCAL_TRAVEL_CONTEXT'))
    parser.add_argument('--tools-profile',choices=['synthetic-v1','synthetic-fact-v1'],default=os.environ.get('CJ_LOCAL_TOOLS_PROFILE'))
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--real', action='store_true')
    parser.add_argument('--interval', type=float, default=0.5)
    args = parser.parse_args()
    if args.auth_dir is None:
        parser.error('--auth-dir or CJ_LOCAL_AUTH_DIR is required for local invitations')
    if args.real:
        parser.error('local run context permits FakeProvider only; --real is unavailable')
    if args.run_context is None: parser.error('--run-context or CJ_LOCAL_RUN_CONTEXT is required')
    context=load_run_context(args.run_context)
    audit=logging.getLogger('cj_usage.audit')
    audit.setLevel(logging.INFO)
    audit.addHandler(logging.StreamHandler(sys.stderr))
    audit.propagate=False
    memory = load_runtime_configuration(args.memory_run_policy) if args.memory_run_policy is not None else None
    database=LocalDatabase(args.conninfo_json,run_context=context,travel_context=travel_configuration(args.travel_context))
    # Protection metadata is checked before even loading real-provider credentials.
    # run_once repeats the check before accepting every original pending run.
    for scope in scopes(database,args.auth_dir):
        database.require_execution(scope)
        require_memory_configuration(database, scope, memory)
    tools=None
    if args.tools_profile=='synthetic-v1':
        from cj_api.local_tools import LocalTools,SyntheticToolModel
        tools=LocalTools();model=SyntheticToolModel()
    elif args.tools_profile=='synthetic-fact-v1':
        from cj_api.local_fact_tools import LocalFactTools,SyntheticFactModel
        tools=LocalFactTools();model=SyntheticFactModel()
    elif args.tools_profile is None:model=provider(args.real)
    else:raise CompositionUnavailable('unknown tools profile')
    while True:
        for outcome in run_once(database, model, args.auth_dir, memory_configuration=memory,tools_configuration=tools):
            print(f'{outcome.status} run={outcome.run_id}'
                  + (f' proposal={outcome.proposal_id}' if outcome.proposal_id else ''), flush=True)
        if args.once:
            if context is not None: print(f'local_provider_calls={model.calls}',flush=True)
            return
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
