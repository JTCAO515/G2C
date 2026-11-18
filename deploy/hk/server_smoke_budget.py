"""Temporary ¥5 restriction of the existing C sublimit. No account quota changes."""
import hashlib

from cj_usage.authorization_budget import CNY_SCALE, LIMITS, _price_receipt, journal_state
from cj_usage.sublimits import policy, usage

from deploy.hk.app_smoke_ceiling import BASELINE

CASH_CAP = 5 * CNY_SCALE


def _policy_and_scope(db, owner):
    if db.execute('SELECT line FROM scope_sublimit WHERE scope_hash=?', (owner,)).fetchone() != ('C',):
        raise ValueError('a pre-existing C scope is required')
    return db.execute("SELECT policy FROM sublimit WHERE line='C'").fetchone()[0]


def budget_state(budget, owner):
    with budget.connect() as db:
        db.execute('BEGIN')
        budget.require_producer(db)
        return {
            'owner': owner,
            'ledger': journal_state(db),
            'tail': db.execute('SELECT COALESCE(MAX(rowid),0) FROM attempt').fetchone()[0],
            'policy': _policy_and_scope(db, owner),
            'used': usage(db, 'C')['total'],
        }


def restrict(budget, before):
    if before['policy'] != policy(BASELINE):
        raise ValueError('original C standing policy required')
    limit = min(BASELINE['cap'], before['used'] + CASH_CAP)
    if limit - before['used'] < CNY_SCALE:
        raise ValueError('insufficient C room for one reservation')
    restricted = policy(dict(BASELINE, active_cap=limit))
    if restricted == before['policy']:
        raise ValueError('distinct temporary C purpose restriction required')
    with budget.mutation() as db:
        if (journal_state(db) != tuple(before['ledger'])
                or _policy_and_scope(db, before['owner']) != before['policy']
                or usage(db, 'C')['total'] != before['used']):
            raise ValueError('C policy or original journal changed before restriction')
        db.execute("UPDATE sublimit SET policy=? WHERE line='C'", (restricted,))
    return restricted


def settlement(budget, owner, restricted, after_tail):
    with budget.connect() as db:
        db.execute('BEGIN')
        budget.require_producer(db)
        if _policy_and_scope(db, owner) != restricted:
            raise ValueError('temporary C restriction changed')
        tail = db.execute('SELECT COALESCE(MAX(rowid),0) FROM attempt').fetchone()[0]
        rows = db.execute(
            "SELECT a.id,a.kind,a.state,a.receipt FROM attempt a "
            "JOIN attempt_sublimit s ON s.attempt_id=a.id "
            "WHERE s.line='C' AND a.rowid>? ORDER BY a.rowid", (after_tail,),
        ).fetchall()
        return tail, summarize(rows, owner), usage(db, 'C')['total']


def summarize(rows, owner):
    prefix = f'g2c1-{owner}-'
    estimates = holds = unavailable = 0
    model_attempts = []
    for ident, kind, state, receipt in rows:
        if not ident.startswith(prefix):
            raise ValueError('new attempts from another C scope')
        estimate = _price_receipt(kind, receipt) if state == 'RECEIVED' else None
        if estimate is None:
            holds += LIMITS[kind][1] * CNY_SCALE
            unavailable += 1
        else:
            estimates += estimate
        if kind == 'model':
            model_attempts.append(hashlib.sha256(ident.encode()).hexdigest())
    return dict(estimated_cny_1e7=estimates, conservative_cny_1e7=estimates+holds,
                unresolved_attempts=unavailable, paid_cny='UNKNOWN', model_attempts=model_attempts)


def restore(budget, before, restricted, expected_ledger):
    limit = min(BASELINE['cap'], before['used'] + CASH_CAP)
    if (before['policy'] != policy(BASELINE) or restricted == before['policy']
            or restricted != policy(dict(BASELINE, active_cap=limit))):
        raise ValueError('original smoke restriction receipt required')
    # The operator binds this to the freshly verified drained state, under the
    # application deployment lock. Consumption and unknown holds remain in the
    # same journal. A changed ledger or cap requires a readback, never a replay.
    with budget.mutation() as db:
        if (journal_state(db) != tuple(expected_ledger)
                or _policy_and_scope(db, before['owner']) != restricted):
            raise ValueError('drained journal or affected sublimit changed')
        db.execute("UPDATE sublimit SET policy=? WHERE line='C'", (before['policy'],))
