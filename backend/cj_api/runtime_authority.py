"""Original authenticated runtime binding and standing resource guards.

This does not issue/renew credentials, reserve fees or change windows/limits.
Actual provider sends still pass the original RUN/Meter/financial guards.
"""
from datetime import datetime
from hashlib import sha256
from time import monotonic
from zoneinfo import ZoneInfo

from cj_auth.interfaces import AdmissionStatus
from cj_usage.authorization_budget import CNY_SCALE
from cj_usage.sublimits import scope_hash,usage
from runtime_adapter import Binding
from runtime_adapter.contract import Unavailable

from .local_app import scope_for

WINDOWS={'L':((9,11),(17,19)),'C':((11,13),(19,21)),
         'E':((21,22),),'F':((22,23),)}


class RuntimeAuthority:
    def __init__(self,checker,token_supplier,budget,pins,current_pins,*,line,
                 wall_clock,clock=monotonic):
        if line not in WINDOWS:raise ValueError('explicit admitted runtime line required')
        self.checker,self.token_supplier,self.budget=checker,token_supplier,budget
        self.original_pins,self.current_pins=pins,current_pins
        self.line,self.wall_clock,self.clock=line,wall_clock,clock

    def binding(self):
        token=self.token_supplier();decision=self.checker.check(token)
        if decision.status is not AdmissionStatus.ALLOWED:
            raise Unavailable('ORIGINAL_AUTH_UNAVAILABLE')
        principal=decision.principal
        return Binding(scope_for(principal.issuer,principal.subject),sha256(token.encode()).hexdigest(),
                       self.budget.ledger_id,self.budget.producer)

    def pins(self):return self.current_pins()

    def require(self,*,binding,pins_sha256,purpose,deadline,read_only):
        if self.clock()>=deadline:raise Unavailable('DEADLINE_REACHED')
        if self.binding()!=binding:raise Unavailable('ORIGINAL_AUTH_CONTEXT_CHANGED')
        if pins_sha256!=self.original_pins.key:raise Unavailable('ORIGINAL_PIN_BINDING_CHANGED')
        with self.budget.connect() as db:
            db.execute('BEGIN');self.budget.require_producer(db)
            row=db.execute('SELECT line FROM scope_sublimit WHERE scope_hash=?',(scope_hash(binding.scope),)).fetchone()
            if row!=(self.line,):raise Unavailable('ORIGINAL_LINE_ALLOCATION_CHANGED')
            if not read_only:
                import json
                limits=json.loads(db.execute('SELECT policy FROM sublimit WHERE line=?',(self.line,)).fetchone()[0])
                spent=usage(db,self.line)
                if (limits['active_cap'] is not None and spent['total']+CNY_SCALE>limits['active_cap'] or
                        limits['max_calls'] is not None and spent['calls']>=limits['max_calls']):
                    raise Unavailable('ORIGINAL_LINE_ALLOWANCE_EXHAUSTED')
        if not read_only:
            self.budget.check_date()
            if self.current_pins()!=self.original_pins.raw:raise Unavailable('RUNTIME_PIN_CHANGED')
            now=self.wall_clock()
            if not isinstance(now,datetime) or now.tzinfo is None:
                raise Unavailable('RESOURCE_CLOCK_UNAVAILABLE')
            local=now.astimezone(ZoneInfo('Asia/Shanghai'))
            minute=local.hour*60+local.minute+local.second/60
            if not any(start*60<=minute<end*60-10 for start,end in WINDOWS[self.line]):
                raise Unavailable('OUTSIDE_STANDING_DISPATCH_WINDOW')
        # AUTH/clock may change while reading the original financial snapshot.
        if self.binding()!=binding:raise Unavailable('ORIGINAL_AUTH_CONTEXT_CHANGED')
        if self.clock()>=deadline:raise Unavailable('DEADLINE_REACHED')
