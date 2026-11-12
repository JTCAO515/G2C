"""Standing guards on the actual original SQLite; AUTH is controlled locally."""
from datetime import datetime,timezone
from types import SimpleNamespace

import pytest

from cj_auth.interfaces import AdmissionStatus
from cj_api.local_app import scope_for
from cj_api.runtime_authority import RuntimeAuthority
from cj_usage.authorization_budget import AuthorizationBudget,CNY_SCALE,journal_state
from cj_usage.sublimits import activate,scope_hash,operation_id
from runtime_adapter import Unavailable


@pytest.fixture
def authority(tmp_path):
    state=dict(token='original-token',allowed=True,clock=10.,wall=datetime(2026,11,12,13,5,tzinfo=timezone.utc),pins=b'original-runtime-pins')
    principal=SimpleNamespace(issuer='local-unit',subject='original-E')
    checker=SimpleNamespace(check=lambda token:SimpleNamespace(status=AdmissionStatus.ALLOWED if state['allowed'] else AdmissionStatus.DENIED,principal=principal))
    budget=AuthorizationBudget(tmp_path/'fees',clock=lambda:datetime(2026,11,12,tzinfo=timezone.utc))
    budget.begin('retained-legacy','model',b'legacy')
    base=dict(cap=None,active_cap=None,model_cap=None,tool_cap=None,max_calls=None,model_calls=None,tool_calls=None)
    grants={line:dict(base) for line in ('A','B','L','C','E','F')}
    for line in ('L','C','E','F'):grants[line].update(cap=2*CNY_SCALE,active_cap=2*CNY_SCALE)
    scope=scope_for(principal.issuer,principal.subject)
    activate(budget,grants,{scope_hash(scope):'E'})
    pins=SimpleNamespace(key='a'*64,raw=state['pins'])
    guard=RuntimeAuthority(checker,lambda:state['token'],budget,pins,lambda:state['pins'],line='E',wall_clock=lambda:state['wall'],clock=lambda:state['clock'])
    return guard,state,budget,pins


def require(guard,pins,*,binding=None,read_only=False):
    guard.require(binding=guard.binding() if binding is None else binding,pins_sha256=pins.key,
                  purpose='query' if read_only else 'call',deadline=100.,read_only=read_only)


def test_fixed_window_allows_own_original_without_reserve_or_login(authority):
    guard,state,budget,pins=authority
    with budget.connect() as db:before=journal_state(db)
    original=guard.binding();require(guard,pins,binding=original)
    with budget.connect() as db:assert journal_state(db)==before
    state['token']='rotated-token'
    with pytest.raises(Unavailable,match='AUTH_CONTEXT_CHANGED'):require(guard,pins,binding=original)


def test_stop_new_and_outside_slot_only_allow_protected_read(authority):
    guard,state,budget,pins=authority
    for wall in (datetime(2026,11,12,13,50,tzinfo=timezone.utc),datetime(2026,11,12,14,5,tzinfo=timezone.utc)):
        state['wall']=wall
        with pytest.raises(Unavailable,match='OUTSIDE_STANDING'):require(guard,pins)
        require(guard,pins,read_only=True)


def test_budget_exhaustion_stops_new_but_preserves_queries(authority):
    guard,state,budget,pins=authority;binding=guard.binding()
    for _ in range(2):budget.begin(operation_id(binding.scope),'model',b'original')
    with pytest.raises(Unavailable,match='ALLOWANCE_EXHAUSTED'):require(guard,pins)
    require(guard,pins,read_only=True)


def test_runtime_drift_revocation_and_deadline_fail_closed(authority):
    guard,state,budget,pins=authority
    state['pins']=b'another-runtime'
    with pytest.raises(Unavailable,match='RUNTIME_PIN_CHANGED'):require(guard,pins)
    require(guard,pins,read_only=True)
    state['allowed']=False
    with pytest.raises(Unavailable,match='AUTH_UNAVAILABLE'):guard.binding()
    state['allowed']=True;state['clock']=101.
    with pytest.raises(Unavailable,match='DEADLINE_REACHED'):require(guard,pins,read_only=True)
