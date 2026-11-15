"""Local-only worker composition; original quota periods never become current by guess."""
import time
from psycopg import Error as DatabaseError
from cj_usage.codec import CorruptLedger
from cj_auth.admission import AdmissionChecker
from cj_auth.jwt_adapter import PyJWTVerifier, JWTConfiguration, StaticPublicKeys, VerificationKey
from cj_needs.revision_lease import RevisionLease, LeaseUnavailable
from cj_run.step_usage import ledger_scope_for
from cj_run.operation_usage import ABI as REGISTERED_ABI
from cj_usage.core import Meter, NATIVE4_PROFILE
from cj_usage.postgres import PostgresRepository
from cj_usage.local_provider_exit import LocalProviderExit, BudgetUnknown
from cj_usage.registered_exit import RegisteredExit, Native4RegisteredExit, MODEL_REGISTRY
from .local_app import ISSUER, AUDIENCE, KEY_ID, InvitedSubjects, needs_lease_resolver


def checker_factory_for(auth_dir, *, selected_subjects=None):
    invitations = InvitedSubjects(auth_dir / 'invited.json', selected_subjects)
    verifier = PyJWTVerifier(
        JWTConfiguration(ISSUER, AUDIENCE, 'RS256', 0),
        StaticPublicKeys({KEY_ID: VerificationKey('RS256', (auth_dir / 'public.pem').read_bytes())}),
    )

    def build(account_retired=None):
        if account_retired is None:
            return AdmissionChecker(verifier, invitations)
        from cj_auth.account_revocation import AccountRevocationAccess
        return AdmissionChecker(verifier, AccountRevocationAccess(invitations, account_retired))

    return build


def checker_for(auth_dir, *, account_retired=None, selected_subjects=None):
    return checker_factory_for(auth_dir, selected_subjects=selected_subjects)(account_retired)


class LocalBudgetRouter:
    def __init__(self, database, *, registrations=None, registrations_for_run=None,exit_observer_for_run=None):
        self.database=database
        self.registrations=MODEL_REGISTRY if registrations is None else registrations
        self.registrations_for_run=registrations_for_run
        self.exit_observer_for_run=exit_observer_for_run

    def stop(self, binding):
        raise BudgetUnknown('original quota period unresolved; cleanup withheld')

    def for_run(self, binding, state):
        try: return self._resolve_original(binding,state)
        except (OSError,ValueError,DatabaseError,CorruptLedger):
            raise BudgetUnknown('local original quota context unavailable') from None

    def _native4_policy(self,binding,profile):
        """Operator qualification is not a client flag; the actual outer wire decides."""
        from cj_message.demo_dialogue import LIO_VERSION_V4
        from cj_message.lio_wire import exploration_original_protocol
        from cj_message.domain import read_active_message
        account=ledger_scope_for(binding.scope,profile.meter)
        with self.database.connect(binding.scope,usage_profile=profile)as conn:
            row=conn.execute('SELECT q.policy,l.format_version FROM cj_native4_usage_profile q '
                'JOIN cj_usage_ledger_candidate l ON l.scope_id=q.ledger_scope '
                'WHERE q.scope=%s AND q.ledger_scope=%s',(binding.scope,account)).fetchone()
            if row is None:return None
            if row!=(NATIVE4_PROFILE,2):raise BudgetUnknown('original native4 account qualification unavailable')
            wire=conn.execute('SELECT lio_wire_protocol FROM cj_message_receipt WHERE scope=%s '
                'AND conversation_id=%s AND generation=%s AND message_id=%s AND run_id=%s',
                (binding.scope,binding.conversation_id,binding.generation,binding.message_id,binding.run_id)).fetchone()
            if wire is None:raise BudgetUnknown('original native4 MESSAGE unavailable')
            if wire[0]!=LIO_VERSION_V4:return None
            with self.database.message_repository(binding.scope).transaction()as tx:
                tx.lock_scope()
                stored=read_active_message(tx,binding.message_id)
            if stored is None:raise BudgetUnknown('original native4 MESSAGE unavailable')
            exploration_original_protocol(conn.cursor(),binding,stored)
        return NATIVE4_PROFILE

    def _resolve_original(self, binding, state):
        context=self.database.run_context
        matches=[]
        for profile in context.profiles:
            account=ledger_scope_for(binding.scope,profile.meter)
            with self.database.connect(binding.scope,usage_profile=profile) as conn:
                registered=context.version=='CJ-LOCAL-RUN@2'
                table='cj_run_metered_binding' if registered else 'cj_run_step_usage'
                fields='ledger_scope,unit,period_start,period_end'+(',source_abi' if registered else '')
                rows=conn.execute('SELECT '+fields+' FROM '+table+
                                  ' WHERE scope=%s AND run_id=%s',(binding.scope,binding.run_id)).fetchall()
                if rows:
                    expected=(account,'provider_call',profile.meter.period_start,profile.meter.period_end)
                    if registered: expected+= (REGISTERED_ABI,)
                    if any(row!=expected for row in rows): raise BudgetUnknown('original profile integrity unavailable')
                    matches.append(profile)
        if len(matches)>1: raise BudgetUnknown('original run spans quota periods')
        if matches: profile=matches[0]
        elif any(event.kind=='started' for event in state.events):
            raise BudgetUnknown('original run period not visible; query with retained original configuration')
        else: profile=context.current
        ledger_version=self.database.require_budget_account(binding.scope,profile=profile)
        run_profile=(self._native4_policy(binding,profile)
                     if context.version=='CJ-LOCAL-RUN@2'and ledger_version==2 else None)
        def resolve(original, account):
            if original.scope!=binding.scope or account!=ledger_scope_for(binding.scope,profile.meter):
                raise BudgetUnknown('original quota owner changed')
            return Meter(PostgresRepository(lambda:self.database.connect(binding.scope,usage_profile=profile),account,
                read_binder=lambda connection,cursor:connection.bind_scope(cursor)),profile.meter,time.time,run_profile=run_profile)
        if context.version=='CJ-LOCAL-RUN@2':
            registrations=(self.registrations if self.registrations_for_run is None else
                           self.registrations_for_run(binding))
            options=dict(clock=time.time,output_limits=profile.output_limits,environment='local',registrations=registrations)
            observer=None if self.exit_observer_for_run is None else self.exit_observer_for_run(binding)
            if observer is not None:
                from .runtime_controlled_generation import ControlledRegisteredExit
                if run_profile is not None:
                    class ControlledNative4Exit(ControlledRegisteredExit,Native4RegisteredExit):pass
                    return ControlledNative4Exit(profile.meter,resolve,observer=observer,**options)
                return ControlledRegisteredExit(profile.meter,resolve,observer=observer,**options)
            selected=Native4RegisteredExit if run_profile is not None else RegisteredExit
            return selected(profile.meter,resolve,**options)
        return LocalProviderExit(profile.meter,resolve,clock=time.time,
                                 output_limits=profile.output_limits,environment='local')


def needs_lease_for(database, checker, token_supplier):
    lease=RevisionLease(checker,needs_lease_resolver(database),environment='local',issuer=ISSUER,audience=AUDIENCE)
    def hold(binding):
        try: token=token_supplier()
        except (OSError,ValueError): raise LeaseUnavailable('local worker identity unavailable') from None
        return lease.hold(token,binding)
    return hold
