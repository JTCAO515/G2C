"""Local-only worker composition; original quota periods never become current by guess."""
import time
from psycopg import Error as DatabaseError
from cj_usage.codec import CorruptLedger
from cj_auth.admission import AdmissionChecker
from cj_auth.jwt_adapter import PyJWTVerifier, JWTConfiguration, StaticPublicKeys, VerificationKey
from cj_message.needs_binding import needs_scope_for
from cj_needs.revision_lease import RevisionLease, LeaseUnavailable
from cj_run.step_usage import ledger_scope_for
from cj_run.operation_usage import ABI as REGISTERED_ABI
from cj_usage.core import Meter
from cj_usage.postgres import PostgresRepository
from cj_usage.local_provider_exit import LocalProviderExit, BudgetUnknown
from cj_usage.registered_exit import RegisteredExit, MODEL_REGISTRY
from .local_app import ISSUER, AUDIENCE, KEY_ID, scope_for, InvitedSubjects


def checker_for(auth_dir):
    return AdmissionChecker(PyJWTVerifier(JWTConfiguration(ISSUER,AUDIENCE,'RS256',0),
        StaticPublicKeys({KEY_ID:VerificationKey('RS256',(auth_dir/'public.pem').read_bytes())})),
        InvitedSubjects(auth_dir/'invited.json'))


class LocalBudgetRouter:
    def __init__(self, database, *, registrations=MODEL_REGISTRY):
        self.database,self.registrations=database,registrations

    def stop(self, binding):
        raise BudgetUnknown('original quota period unresolved; cleanup withheld')

    def for_run(self, binding, state):
        try: return self._resolve_original(binding,state)
        except (OSError,ValueError,DatabaseError,CorruptLedger):
            raise BudgetUnknown('local original quota context unavailable') from None

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
        self.database.require_budget_account(binding.scope,profile=profile)
        def resolve(original, account):
            if original.scope!=binding.scope or account!=ledger_scope_for(binding.scope,profile.meter):
                raise BudgetUnknown('original quota owner changed')
            return Meter(PostgresRepository(lambda:self.database.connect(binding.scope,usage_profile=profile),account),profile.meter,time.time)
        if context.version=='CJ-LOCAL-RUN@2':
            return RegisteredExit(profile.meter,resolve,clock=time.time,output_limits=profile.output_limits,
                                  environment='local',registrations=self.registrations)
        return LocalProviderExit(profile.meter,resolve,clock=time.time,
                                 output_limits=profile.output_limits,environment='local')


def needs_lease_for(database, checker, token_supplier):
    def resolve(principal):
        scope=scope_for(principal.issuer,principal.subject)
        return lambda:database.connect(scope),scope,needs_scope_for(scope)
    lease=RevisionLease(checker,resolve,environment='local',issuer=ISSUER,audience=AUDIENCE)
    def hold(binding):
        try: token=token_supplier()
        except (OSError,ValueError): raise LeaseUnavailable('local worker identity unavailable') from None
        return lease.hold(token,binding)
    return hold
