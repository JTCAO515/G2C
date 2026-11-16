"""B-only purpose restriction inside original C100; no new money or native quota.

Call bounds and the independently authorized 60/80 CNY cash ceiling both apply.
This is never an automatic retry/restore after FAIL or UNKNOWN. Installation,
actual quote approval, source/lease qualification and idle proof are external
B operator prerequisites; constructing this request grants none of them.
"""
from hashlib import sha256
import json
import re
import sys

from cj_usage.authorization_budget import AuthorizationBudget,HK_JOURNAL_ROOT,CNY_SCALE,journal_state
from cj_usage.sublimits import policy,usage
from .configuration import load_secret_environment,authorization

VERSION='G2C-App-smoke-purpose-restriction.1'
PROFILES={'standard':(40,32,60),'first_setup':(80,64,80)}
BASELINE=dict(cap=100*CNY_SCALE,active_cap=100*CNY_SCALE,model_cap=None,tool_cap=None,
              max_calls=None,model_calls=None,tool_calls=None)


def restrict(budget,request):
    fields={'version','profile','scope_hashes','expected_policy_sha256','apply'}
    if(type(request)is not dict or set(request)!=fields or request['version']!=VERSION
            or type(request['profile'])is not str or request['profile']not in PROFILES or type(request['apply'])is not bool
            or type(request['scope_hashes'])is not list or len(request['scope_hashes'])!=2
            or any(type(x)is not str or re.fullmatch('[a-f0-9]{32}',x)is None for x in request['scope_hashes'])
            or len(set(request['scope_hashes']))!=2
            or type(request['expected_policy_sha256'])is not str
            or re.fullmatch('[a-f0-9]{64}',request['expected_policy_sha256'])is None):
        raise ValueError('fixed two-owner C purpose request required')
    models,tools,cash=PROFILES[request['profile']]
    with budget.connect()as db:
        db.execute('BEGIN');budget.require_producer(db);anchor=journal_state(db)
        row=db.execute("SELECT policy FROM sublimit WHERE line='C'").fetchone()
        if row is None:raise ValueError('original C100 allocation required')
        original=row[0]
        if (sha256(original.encode()).hexdigest()!=request['expected_policy_sha256']
                or original!=policy(BASELINE)):
            raise ValueError('exact original C100 standing policy required')
        for scope in request['scope_hashes']:
            if db.execute('SELECT line FROM scope_sublimit WHERE scope_hash=?',(scope,)).fetchone()!=('C',):
                raise ValueError('only the two original C owners may enter this purpose')
        used=usage(db,'C')
        others=db.execute("SELECT * FROM sublimit WHERE line<>'C' ORDER BY line").fetchall()
        scopes=db.execute('SELECT * FROM scope_sublimit ORDER BY scope_hash').fetchall()
        assignments=db.execute('SELECT * FROM attempt_sublimit ORDER BY attempt_id').fetchall()
    limits=dict(BASELINE,active_cap=min(BASELINE['active_cap'],used['total']+cash*CNY_SCALE),
        max_calls=used['calls']+models+tools,model_calls=used['model_calls']+models,
        tool_calls=used['tool_calls']+tools)
    encoded=policy(limits)
    result=dict(version='G2C-App-smoke-purpose-restriction-result.1',state='READONLY_NOT_A_LEASE',
        baseline_policy=BASELINE,restricted_policy=limits,original_usage=used,
        original_ledger=dict(count=anchor[0],sha256=anchor[1]),new_money_cny=0,
        native_account_quota_changed=False,provider_calls=0,
        cash_ceiling_cny=cash,model_call_bound=models,tool_call_bound=tools,
        effective_cash_room_cny_1e7=limits['active_cap']-used['total'],
        amount_status='independent simultaneous caps; not prepaid consumption or supplier invoice')
    if not request['apply']:return result
    with budget.mutation()as db:
        if (journal_state(db)!=anchor or db.execute("SELECT policy FROM sublimit WHERE line='C'").fetchone()!=(original,)
                or usage(db,'C')!=used or db.execute('SELECT * FROM scope_sublimit ORDER BY scope_hash').fetchall()!=scopes
                or db.execute('SELECT * FROM attempt_sublimit ORDER BY attempt_id').fetchall()!=assignments
                or db.execute("SELECT * FROM sublimit WHERE line<>'C' ORDER BY line").fetchall()!=others):
            raise ValueError('original accounting or allocation changed before restriction')
        changed=db.execute('UPDATE sublimit SET policy=? WHERE line=? AND policy=?',(encoded,'C',original)).rowcount
        if changed!=1:raise ValueError('original C policy transition unavailable')
    result['state']='C_PURPOSE_RESTRICTED_ACKED_NOT_A_LEASE'
    return result


def main():
    raw=sys.stdin.buffer.read(16385)
    if len(raw)>16384:raise ValueError('bounded C purpose request required')
    from cj_strict_json import reject_duplicates
    request=json.loads(raw,object_pairs_hook=reject_duplicates(ValueError,'duplicate C purpose field'))
    load_secret_environment('worker');authorization()
    budget=AuthorizationBudget(HK_JOURNAL_ROOT,authorization_guard=authorization,demo=True)
    print(json.dumps(restrict(budget,request),sort_keys=True))


if __name__=='__main__':main()
