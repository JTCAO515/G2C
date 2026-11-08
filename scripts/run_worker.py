"""Host worker for CJ_ENV=local: MESSAGE pending deliveries -> model -> RUN events (P2a).

  run_worker.py --conninfo-json conn.json [--once] [--real]

The formal worker requires explicit quota context. Only deterministic FakeProvider
is enabled; --real refuses before reading credentials. Interrupted work is queried
by its original identity and never automatically resent.
"""
import argparse
from contextlib import closing, contextmanager, nullcontext
from functools import cache
import json
import os
from pathlib import Path
import sys
import logging
import time
from uuid import uuid4

if os.environ.get('CJ_ENV') != 'local':
    raise SystemExit('CJ_ENV=local is required')

from cj_agent.draft import DraftPublisher
from cj_agent.provider import FakeProvider, ProviderFailed
from cj_agent.worker import RunWorker, original_context_valid
from cj_api.local_app import LocalDatabase, ISSUER, scope_for, travel_configuration, trip_configuration
from cj_api.composition import CompositionUnavailable
from cj_api.local_run_context import load_run_context
from cj_api.local_worker_context import LocalBudgetRouter, checker_for, checker_factory_for, needs_lease_for
from cj_auth.interfaces import AdmissionStatus
from cj_needs.revision_lease import LeaseUnavailable
from cj_memory.local_runtime import load_runtime_configuration
from cj_memory.runtime import RuntimeDenied, RuntimeUnknown
from cj_memory.typed_runtime import TypedRuntimeConfiguration
import dev_auth
from cj_message.domain import Service as MessageService, Unavailable as MessageUnavailable, read_active_message
from cj_message.edit_reference import profile as edit_profile
from cj_message.travel_reference import profile as travel_profile
from cj_message.trip_reference import profile as trip_profile
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
    with database.connect(scope) as conn:
        with conn.cursor() as cursor:
            _require_memory_configuration(cursor, scope, configuration, travel_profile(cursor, scope))


def _require_memory_configuration(cursor, scope, configuration, travel):
    if travel and configuration is not None and type(configuration) is not TypedRuntimeConfiguration:
        raise RuntimeDenied('travel execution requires explicit typed memory configuration')
    cursor.execute('SELECT 1 FROM cj_memory_scope WHERE scope=%s', (scope,))
    exists = cursor.fetchone() is not None
    if trip_profile(cursor, scope) and (exists or configuration is not None):
        raise RuntimeDenied('formal Trip MEMORY adapter is not installed')
    if exists and configuration is None:
        raise RuntimeDenied('existing memory requires explicit runtime configuration')


def _worker_for_scope(database,model,auth_dir,scope,checker, *, memory_configuration=None,tools_configuration=None,draft_profile=None,place_draft_configuration=None,formal_memory_configuration=None,account_checker_builder=None,beta_b_run_credential=False):
    if draft_profile not in (None,'needs-structured.1','needs-current-trip.1'):
        raise CompositionUnavailable('unknown explicit draft profile')
    if place_draft_configuration is not None:
        from cj_place.draft_source import PlaceDraftConfiguration,ABI,PUBLISHER_ABI
        from cj_api.local_place_draft import LocalPlaceDraftTools
        if (type(place_draft_configuration) is not PlaceDraftConfiguration or place_draft_configuration.abi!=ABI
                or place_draft_configuration.publisher is None or place_draft_configuration.publisher.abi!=PUBLISHER_ABI
                or type(tools_configuration) is not LocalPlaceDraftTools or draft_profile is not None):
            raise CompositionUnavailable('explicit compatible PLACE-source tools and C producer required')
    reuse_preflight = (account_checker_builder is not None and memory_configuration is None
                       and formal_memory_configuration is None)
    with (closing(database.connect(scope)) if reuse_preflight else nullcontext()) as preflight_connection:
        database.require_execution(scope, connection=preflight_connection)
        edit_config = None
        with database.scoped_cursor(scope, connection=preflight_connection) as cursor:
            editing = edit_profile(cursor, scope)
            if editing:
                from cj_message.edit_reference import configured
                from cj_api.edit_result_profile import profile as result_profile
                edit_config = configured(database.edit_configuration)
                if result_profile(cursor, scope) != database.edit_results:
                    raise CompositionUnavailable('explicit activated publisher2 profile/configuration required')
                if memory_configuration is not None or tools_configuration is not None:
                    raise CompositionUnavailable('edit profile requires its negotiated memory/publisher only')
            elif formal_memory_configuration is not None:
                if (memory_configuration is not None or not database.trip_context or not database.travel_context
                        or not trip_profile(cursor, scope)):
                    raise CompositionUnavailable('explicit existing formal profile and sole C formal Memory configuration required')
            else:
                _require_memory_configuration(cursor, scope, memory_configuration, travel_profile(cursor, scope))
        if editing and formal_memory_configuration is not None:
            raise CompositionUnavailable('formal discussion and scoped edit have separate C configurations')
        if tools_configuration is not None and (database.run_context is None or database.run_context.version!='CJ-LOCAL-RUN@2'):
            raise CompositionUnavailable('tools require the registered M2 exit')
        messages = MessageService(database.message_repository(scope), new_run_id=lambda: None)
        subject = scope.removeprefix('local:' + ISSUER + ':')
        def token(subject=subject): return dev_auth.token(Path(auth_dir),subject,5)
        bootstrap_credential = token() if memory_configuration is not None or editing or formal_memory_configuration is not None else None
        # Use a new transaction for the final live Travel profile check.
        with database.scoped_cursor(scope, connection=preflight_connection) as cursor:
            travel_enabled = travel_profile(cursor, scope)

    issue_run_credential = None

    @contextmanager
    def lease_beta_b_credential():
        nonlocal issue_run_credential
        from cj_api.local_account_admission_v2 import permit_retirement_read_lease,retirement_read_operation

        @cache
        def issue():
            return dev_auth.token(Path(auth_dir), subject, 11, jti=str(uuid4()))

        issue_run_credential = issue
        try:
            # Reuse only the physical connection: every retirement check still
            # gets a fresh read-only transaction with the current scope/release.
            with permit_retirement_read_lease(database,lambda:tools_configuration.services.require_scope(scope)), \
                    retirement_read_operation(purpose='hk_beta_b_worker_retirement'):
                yield
        finally:
            issue_run_credential = None
            issue.cache_clear()

    def memory_credential():
        return bootstrap_credential if issue_run_credential is None else issue_run_credential()

    def memory_admit():
        decision = checker.check(memory_credential())
        if decision.status is AdmissionStatus.UNKNOWN:
            raise RuntimeUnknown('memory admission unknown')
        if decision.status is not AdmissionStatus.ALLOWED or scope_for(
                decision.principal.issuer, decision.principal.subject) != scope:
            raise RuntimeDenied('memory admission denied')
        return decision.principal
    message_context=None
    if travel_enabled or type(memory_configuration) is TypedRuntimeConfiguration:
        from cj_message.travel_reference import MessageContextAuthority
        uses_memory_credential = type(memory_configuration) is TypedRuntimeConfiguration or formal_memory_configuration is not None
        travel_credential = None if uses_memory_credential else token()
        def travel_admit():
            decision=checker.check(memory_credential() if uses_memory_credential else travel_credential)
            if decision.status is AdmissionStatus.UNKNOWN:
                raise LeaseUnavailable('travel admission unknown')
            if (decision.status is not AdmissionStatus.ALLOWED
                    or scope_for(decision.principal.issuer,decision.principal.subject)!=scope):
                raise Denied('travel admission denied')
            return decision.principal
        if editing:
            from cj_message.edit_reference import EditAuthority
            message_context=EditAuthority(database.message_repository(scope),travel_admit,database.run_repository(scope),result_mode=database.edit_results)
        else:message_context=MessageContextAuthority(database.message_repository(scope),travel_admit)
    if editing:
        memory=edit_config.memory.bind(database,scope,subject,memory_admit,message_context=message_context)
        if memory is None:raise RuntimeDenied('C memory adapter did not bind')
    elif formal_memory_configuration is not None:
        memory=formal_memory_configuration.bind(database,scope,subject,memory_admit,message_context=message_context)
    elif type(memory_configuration) is TypedRuntimeConfiguration:
        memory=memory_configuration.bind(database,scope,subject,memory_admit,message_context=message_context)
    else:
        memory=(memory_configuration.bind(database,scope,subject,memory_admit)
                if memory_configuration is not None else None)
    def check_admitted_original(binding, active_checker, read_original):
        credential=token()
        first=active_checker.check(credential)
        if first.status is AdmissionStatus.UNKNOWN: raise LeaseUnavailable('worker admission unknown')
        if first.status is not AdmissionStatus.ALLOWED: return False
        if scope_for(first.principal.issuer,first.principal.subject)!=binding.scope: return False
        original=read_original()
        last=active_checker.check(credential)
        if last.status is AdmissionStatus.UNKNOWN: raise LeaseUnavailable('worker admission unknown')
        return original is True and last.status is AdmissionStatus.ALLOWED and last.principal==first.principal

    execution_connection = None

    @contextmanager
    def lease_execution():
        nonlocal execution_connection
        connection = database.connect(scope)
        execution_connection = connection
        try:
            yield
        finally:
            execution_connection = None
            connection.close()

    def valid(binding):
        if message_context is not None:
            return message_context.valid(binding)
        if account_checker_builder is None:
            database.require_execution(binding.scope, binding)
            return check_admitted_original(binding, checker, lambda: original_context_valid(binding, messages, lambda: True))
        if binding.scope != scope:
            return False
        from cj_api.local_account_admission_v2 import retired_in_transaction
        with database.execution_transaction(scope, binding, connection=execution_connection) as tx:
            scoped_checker = account_checker_builder(retired_in_transaction(tx.cur, scope))

            def same_original():
                try:
                    stored = read_active_message(tx, binding.message_id)
                except MessageUnavailable:
                    return False
                if stored is None:
                    return False
                receipt = stored.receipt
                return (receipt.message_id, receipt.conversation_id, receipt.generation, receipt.run_id, receipt.sequence) == (
                    binding.message_id, binding.conversation_id, binding.generation, binding.run_id, binding.message_sequence)

            return check_admitted_original(binding, scoped_checker, same_original)

    runs = RunService(database.run_repository(scope),valid=valid)
    reuse_connections = account_checker_builder is not None and message_context is None
    place_sources=None
    if place_draft_configuration is not None:
        if editing or database.run_context is None or database.run_context.version!='CJ-LOCAL-RUN@2' or message_context is None:
            raise CompositionUnavailable('PLACE-source producer requires registered M2/travel creation host')
        place_sources=tools_configuration.source_for(scope)
        drafts=place_draft_configuration.publisher.bind(database,checker,message_context,token,scope,place_sources=place_sources)
        if drafts.content_version not in ('structured.1','structured.2'):
            raise CompositionUnavailable('new PLACE producer must explicitly support structured.1 or structured.2')
    elif draft_profile is None:
        drafts=DraftPublisher(database.trip_repository(scope))
    else:
        if editing or tools_configuration is not None or database.run_context is None or database.run_context.version!='CJ-LOCAL-RUN@2' or message_context is None:
            raise CompositionUnavailable('NEEDS draft profile requires registered M2/travel creation host')
        if draft_profile=='needs-structured.1':
            from cj_draft.needs_local import publisher
            drafts=publisher(database,checker,message_context,token,scope)
        else:
            from cj_api.local_current_plan import publisher
            drafts=publisher(database,checker,message_context,token,scope)
    history=None
    if editing:
        from cj_memory.edit_runtime import EditRuntimeConfiguration
        from cj_memory.scoped_capture import ScopedMemoryConfiguration
        # Only the provided canonical C factories opt into the new history ABI.
        # Existing test-only/custom EDIT-MEMORY@1 adapters retain their original
        # capture contract; they are not an accepted #26 history implementation.
        history_supported=type(edit_config.memory) in (EditRuntimeConfiguration,ScopedMemoryConfiguration)
    else:history_supported=True
    if memory is not None and history_supported:
        from cj_api.local_memory_history import HistoryMemory,OriginalHistory,OriginalDecisions
        decisions=OriginalDecisions(database,Path(auth_dir),memory_credential,memory_admit,message_context)
        history=HistoryMemory(memory,OriginalHistory(messages,decisions))
    return RunWorker(scope=scope, messages=messages, runs=runs, provider=model, drafts=drafts,
        memory=memory,edit_publisher=None if edit_config is None else edit_config.publisher,edit_results=database.edit_results,
        memory_history=history is not None,history_adapter=history,
        message_context=message_context,
        execution_lease=lease_beta_b_credential if beta_b_run_credential else lease_execution if reuse_connections else nullcontext,
        owned_transaction_lease=(lambda: database.lease_run_transactions(runs.repository)) if reuse_connections else None,
        tools=tools_configuration,place_sources=place_sources,
        execution_guard=lambda binding: database.require_execution(binding.scope, binding, connection=execution_connection),
        needs_lease=needs_lease_for(database,checker,memory_credential if beta_b_run_credential else token),
        budget_exit=(LocalBudgetRouter(database) if tools_configuration is None else
                     LocalBudgetRouter(database,registrations=tools_configuration.registrations)))


def run_once(database, model, auth_dir, *, memory_configuration=None,memory_configuration_for_scope=None,tools_configuration=None,draft_profile=None,place_draft_configuration=None,background_jobs=None,formal_memory_configuration=None,real_services=None,account_admission=False,hk_beta_b_run_credential=False):
    if memory_configuration_for_scope is not None and (memory_configuration is not None or formal_memory_configuration is not None):
        raise ValueError('select one explicit Memory configuration source')
    if formal_memory_configuration is not None:
        from cj_api.local_formal_memory import configuration
        formal_memory_configuration=configuration(formal_memory_configuration)
        if not database.travel_context or not database.trip_context or database.edit_configuration is not None:
            raise CompositionUnavailable('explicit formal/travel worker required, separate from scoped edit')
    pending_scopes=scopes(database,auth_dir)
    if not pending_scopes and background_jobs is None: return []
    if database.run_context is None:
        raise CompositionUnavailable('explicit run context required before execution')
    if real_services is None:
        if not isinstance(model,FakeProvider):raise ProviderFailed('configured local context permits only FakeProvider')
    else:
        from cj_api.real_services import RealServices,RealTools
        if (type(real_services) is not RealServices or model is not real_services.model
                or type(tools_configuration) is not RealTools or tools_configuration.services is not real_services
                or database.run_context.version!='CJ-LOCAL-RUN@2' or background_jobs is not None):
            raise ProviderFailed('explicit registered M4 real composition required')
        for scope in pending_scopes:real_services.require_scope(scope)
    account_checker_builder = None
    if formal_memory_configuration is None and not account_admission:
        checker = checker_for(Path(auth_dir))
    elif real_services is not None and account_admission:
        from cj_api.local_account_admission_v2 import retired_for
        account_checker_builder = checker_factory_for(Path(auth_dir))
        checker = account_checker_builder(retired_for(database))
    else:
        from cj_api.local_account_admission_v2 import account_checker_for
        checker=account_checker_for(Path(auth_dir),database)
    results = []
    failure = None
    for scope in pending_scopes:
        # One scope's unreconciled run (for example an unresolved original quota
        # period) must not starve every later scope; it is still raised below.
        try:
            selected_memory=(memory_configuration if memory_configuration_for_scope is None
                             else memory_configuration_for_scope(scope))
            beta_b_run_credential = (hk_beta_b_run_credential and account_checker_builder is not None
                and scope == scope_for(ISSUER, 'm4-synthetic-beta-b')
                and type(selected_memory) is TypedRuntimeConfiguration
                and database.run_context.current.meter.max_seconds == 600)
            results += _worker_for_scope(database,model,auth_dir,scope,checker,
                                         memory_configuration=selected_memory,tools_configuration=tools_configuration,draft_profile=draft_profile,place_draft_configuration=place_draft_configuration,formal_memory_configuration=formal_memory_configuration,
                                         account_checker_builder=account_checker_builder,beta_b_run_credential=beta_b_run_credential).process()
        except Exception as error:
            if failure is None: failure = error
    if background_jobs is not None:results+=background_jobs.run_once(model)
    if failure is not None: raise failure
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--conninfo-json', type=Path, required=True)
    parser.add_argument('--auth-dir', type=Path, default=os.environ.get('CJ_LOCAL_AUTH_DIR'))
    parser.add_argument('--run-context', type=Path, default=os.environ.get('CJ_LOCAL_RUN_CONTEXT'))
    parser.add_argument('--memory-run-policy', type=Path, default=os.environ.get('CJ_LOCAL_MEMORY_RUN_POLICY'))
    parser.add_argument('--formal-memory-run-policy',type=Path,default=os.environ.get('CJ_LOCAL_FORMAL_MEMORY_RUN_POLICY'))
    parser.add_argument('--travel-context',choices=['message-travel.1'],default=os.environ.get('CJ_LOCAL_TRAVEL_CONTEXT'))
    parser.add_argument('--trip-context',choices=['message-trip.1'],default=os.environ.get('CJ_LOCAL_TRIP_CONTEXT'))
    parser.add_argument('--tools-profile',choices=['synthetic-v1','synthetic-fact-v1','synthetic-needs-v1','real-m4'],default=os.environ.get('CJ_LOCAL_TOOLS_PROFILE'))
    parser.add_argument('--draft-profile',choices=['needs-structured.1','needs-current-trip.1'])
    parser.add_argument('--once', action='store_true')
    parser.add_argument('--real', action='store_true')
    parser.add_argument('--interval', type=float, default=0.5)
    args = parser.parse_args()
    if args.auth_dir is None:
        parser.error('--auth-dir or CJ_LOCAL_AUTH_DIR is required for local invitations')
    if args.real != (args.tools_profile=='real-m4'):
        parser.error('--real and --tools-profile real-m4 must be explicitly paired')
    if args.run_context is None: parser.error('--run-context or CJ_LOCAL_RUN_CONTEXT is required')
    context=load_run_context(args.run_context)
    audit=logging.getLogger('cj_usage.audit')
    audit.setLevel(logging.INFO)
    audit.addHandler(logging.StreamHandler(sys.stderr))
    audit.propagate=False
    memory = load_runtime_configuration(args.memory_run_policy) if args.memory_run_policy is not None else None
    formal_memory=None
    if args.formal_memory_run_policy is not None:
        from cj_memory.formal_runtime import load_formal_runtime_configuration
        if memory is not None:parser.error('select one explicit Memory configuration')
        formal_memory=load_formal_runtime_configuration(args.formal_memory_run_policy)
    database=LocalDatabase(args.conninfo_json,run_context=context,travel_context=travel_configuration(args.travel_context),trip_context=trip_configuration(args.trip_context))
    if formal_memory is not None and (not database.travel_context or not database.trip_context):
        parser.error('formal Memory requires an explicit formal/travel host')
    # Protection metadata is checked before even loading real-provider credentials.
    # run_once repeats the check before accepting every original pending run.
    for scope in scopes(database,args.auth_dir):
        database.require_execution(scope)
        if formal_memory is None:require_memory_configuration(database, scope, memory)
        elif not database.trip_context or not database.trip_profile(scope):
            parser.error('formal Memory requires an activated formal Trip host')
    if args.draft_profile is not None and args.tools_profile is not None:
        parser.error('explicit NEEDS draft and tool profiles cannot be combined')
    tools=None;real_services=None
    if args.tools_profile=='real-m4':
        from cj_api.real_services import RealServices,RealTools
        real_services=RealServices.from_environment(args.auth_dir)
        tools=RealTools(real_services);model=real_services.model
    elif args.tools_profile=='synthetic-v1':
        from cj_api.local_tools import LocalTools,SyntheticToolModel
        tools=LocalTools();model=SyntheticToolModel()
    elif args.tools_profile=='synthetic-fact-v1':
        from cj_api.local_fact_tools import LocalFactTools,SyntheticFactModel
        tools=LocalFactTools();model=SyntheticFactModel()
    elif args.tools_profile=='synthetic-needs-v1':
        from cj_api.local_needs_preview import LocalNeedsPreview,SyntheticNeedsModel
        tools=LocalNeedsPreview();model=SyntheticNeedsModel()
    elif args.tools_profile is None:
        if args.draft_profile=='needs-structured.1':
            from cj_api.local_plan_model import NeedsPlanFakeProvider
            model=NeedsPlanFakeProvider()
        elif args.draft_profile=='needs-current-trip.1':
            from cj_api.local_plan_model import CurrentTripPlanFakeProvider
            model=CurrentTripPlanFakeProvider()
        else:model=provider(args.real)
    else:raise CompositionUnavailable('unknown tools profile')
    while True:
        for outcome in run_once(database, model, args.auth_dir, memory_configuration=memory,tools_configuration=tools,draft_profile=args.draft_profile,formal_memory_configuration=formal_memory,real_services=real_services):
            print(f'{outcome.status} run={outcome.run_id}'
                  + (f' proposal={outcome.proposal_id}' if outcome.proposal_id else ''), flush=True)
        if args.once:
            if context is not None: print(f'local_provider_calls={model.calls}',flush=True)
            return
        time.sleep(args.interval)


if __name__ == '__main__':
    main()
