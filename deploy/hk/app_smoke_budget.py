"""B-only read of the existing C financial ceiling; never allocates or sends."""
from decimal import Decimal
import json

from cj_usage.authorization_budget import AuthorizationBudget,HK_JOURNAL_ROOT,CNY_SCALE,journal_state
from cj_usage.sublimits import snapshot as sublimit_snapshot,usage
from .configuration import authorization,load_secret_environment


def snapshot():
    load_secret_environment('worker');authorization()
    budget=AuthorizationBudget(HK_JOURNAL_ROOT,authorization_guard=authorization,demo=True)
    with budget.connect()as db:
        db.execute('BEGIN');budget.require_producer(db);count,digest=journal_state(db)
        if sublimit_snapshot(db)is None:raise ValueError('existing C allocation required')
        row=db.execute("SELECT policy FROM sublimit WHERE line='C'").fetchone()
        if row is None:raise ValueError('existing C allocation required')
        policy=json.loads(row[0]);used=usage(db,'C')
        ceiling=min(x for x in(policy['cap'],policy['active_cap'])if x is not None)
        remaining=ceiling-used['total']
    return dict(version='G2C-App-smoke-budget.1',ledger_id=budget.ledger_id,producer_id=budget.producer,
        line='C',native_policy=policy,native_usage=used,
        available_cny=format(Decimal(remaining)/CNY_SCALE,'f'),
        ledger_anchor=dict(count=count,sha256=digest),
        quota_change=False,new_charge_attempts=0,actual_supplier_paid='UNKNOWN')


if __name__=='__main__':print(json.dumps(snapshot(),sort_keys=True))
