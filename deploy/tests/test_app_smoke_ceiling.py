"""Original SQLite/control integration; no real HK, provider or account writes."""
from hashlib import sha256
import json

import pytest

from backend.usage.tests.test_sublimits import allocated,received
from cj_usage import sublimits
from cj_usage.authorization_budget import CNY_SCALE,journal_state
from cj_usage.metered_exit import BudgetUnknown
from deploy.hk import app_smoke_ceiling as ceiling


def setup(budget):
    with budget.mutation()as db:
        db.execute('INSERT INTO scope_sublimit VALUES(?,?)',(sublimits.scope_hash('second-C'),'C'))
    request=dict(version=ceiling.VERSION,profile='first_setup',
        scope_hashes=[sublimits.scope_hash('owner-C'),sublimits.scope_hash('second-C')],
        expected_policy_sha256=sha256(sublimits.policy(ceiling.BASELINE).encode()).hexdigest(),apply=False)
    return request


def state(budget):
    with budget.connect()as db:
        db.execute('BEGIN');budget.require_producer(db)
        return dict(anchor=journal_state(db),others=db.execute("SELECT * FROM sublimit WHERE line<>'C' ORDER BY line").fetchall(),
            scopes=db.execute('SELECT * FROM scope_sublimit ORDER BY scope_hash').fetchall(),
            assignments=db.execute('SELECT * FROM attempt_sublimit ORDER BY attempt_id').fetchall(),
            original_usage=sublimits.usage(db,'C'))


def test_preflight_is_readonly_and_apply_only_restricts_original_C_policy(allocated):
    budget,anchor=allocated;request=setup(budget)
    old=sublimits.read(budget);before=state(budget)
    report=ceiling.restrict(budget,request)
    assert report['state']=='READONLY_NOT_A_LEASE'and sublimits.read(budget)==old
    assert report['cash_ceiling_cny']==80 and report['model_call_bound']==80 and report['tool_call_bound']==64
    assert report['new_money_cny']==0 and report['native_account_quota_changed']is False
    report=ceiling.restrict(budget,dict(request,apply=True))
    assert report['state']=='C_PURPOSE_RESTRICTED_ACKED_NOT_A_LEASE'
    assert state(budget)==before
    view=sublimits.read(budget)
    assert view['C']['policy']['cap']==100*CNY_SCALE
    assert view['C']['policy']['active_cap']==80*CNY_SCALE
    assert(view['C']['policy']['model_calls'],view['C']['policy']['tool_calls'],view['C']['policy']['max_calls'])==(80,64,144)
    assert all(view[k]==old[k]for k in view if k!='C')
    with pytest.raises(ValueError,match='standing policy'):ceiling.restrict(budget,dict(request,apply=True))


def test_native_begin_cash_ceiling_refuses_next_full_hold_and_preserves_UNKNOWN(allocated):
    budget,_=allocated;request=setup(budget);ceiling.restrict(budget,dict(request,profile='standard',apply=True))
    for _ in range(40):budget.begin(sublimits.operation_id('owner-C'),'model',b'original model')
    for _ in range(20):budget.begin(sublimits.operation_id('owner-C'),'weather',b'original tool')
    before=state(budget)
    with pytest.raises(BudgetUnknown,match='authorization ceiling'):
        budget.begin(sublimits.operation_id('second-C'),'model',b'no room for its full hold')
    assert state(budget)==before
    assert sublimits.read(budget)['C']['usage']['total']==60*CNY_SCALE
    assert sum(row['state']=='INTENT'for row in budget.inspect())==61  # includes retained historical UNKNOWN


def test_native_call_caps_are_independent_of_receipt_estimates(allocated):
    budget,_=allocated;request=setup(budget);ceiling.restrict(budget,dict(request,profile='standard',apply=True))
    for index in range(40):
        attempt=sublimits.operation_id('owner-C');budget.begin(attempt,'model',b'original')
        budget.finish(attempt,received('C-smoke-'+str(index)))
    with pytest.raises(BudgetUnknown,match='category'):
        budget.begin(sublimits.operation_id('owner-C'),'model',b'forty-first')
    assert sublimits.read(budget)['C']['usage']['model_calls']==40


def test_existing_usage_and_hold_are_included_without_increasing_original_C100(allocated):
    budget,_=allocated;request=setup(budget)
    for _ in range(30):budget.begin(sublimits.operation_id('owner-C'),'weather',b'existing unpriced')
    before=state(budget);ceiling.restrict(budget,dict(request,apply=True))
    assert state(budget)==before
    p=sublimits.read(budget)['C']['policy']
    assert p['active_cap']==100*CNY_SCALE and p['tool_calls']==94 and p['max_calls']==174


@pytest.mark.parametrize('change',[dict(profile=[]),dict(scope_hashes=[[],[]]),dict(profile='other'),
    dict(scope_hashes=[sublimits.scope_hash('owner-C')]*2),dict(scope_hashes=[sublimits.scope_hash('owner-C'),sublimits.scope_hash('owner-L')]),
    dict(expected_policy_sha256='f'*64)])
def test_malformed_foreign_or_stale_request_changes_nothing(allocated,change):
    budget,_=allocated;request=setup(budget);before=state(budget)
    with pytest.raises(ValueError):ceiling.restrict(budget,dict(request,**change,apply=True))
    assert state(budget)==before and sublimits.read(budget)['C']['policy']==ceiling.BASELINE


def test_lost_control_ACK_remains_unknown_and_cannot_repeat_policy_write(allocated,monkeypatch):
    from cj_usage import authorization_budget as parent
    budget,anchor=allocated;request=setup(budget);original=parent.save_anchor
    def interrupt(value):
        if value['state']==sublimits.ADOPTED:raise OSError('fixture lost control ACK')
        original(value)
    monkeypatch.setattr(parent,'save_anchor',interrupt)
    with pytest.raises(OSError,match='control ACK'):ceiling.restrict(budget,dict(request,apply=True))
    assert json.loads(anchor.read_text())['state']=='WRITE_INTENT'
    with pytest.raises(BudgetUnknown):ceiling.restrict(budget,dict(request,apply=True))
    with pytest.raises(BudgetUnknown):budget.begin(sublimits.operation_id('owner-C'),'model',b'no replacement')


def test_new_original_attempt_before_commit_prevents_stale_purpose_write(allocated,monkeypatch):
    from contextlib import contextmanager
    budget,_=allocated;request=setup(budget);original=budget.mutation
    @contextmanager
    def raced():
        monkeypatch.setattr(budget,'mutation',original)
        budget.begin(sublimits.operation_id('owner-C'),'model',b'concurrent original')
        with original()as db:yield db
    monkeypatch.setattr(budget,'mutation',raced)
    with pytest.raises(ValueError,match='changed before restriction'):
        ceiling.restrict(budget,dict(request,apply=True))
    assert sublimits.read(budget)['C']['policy']==ceiling.BASELINE
    assert sublimits.read(budget)['C']['usage']['model_calls']==1
