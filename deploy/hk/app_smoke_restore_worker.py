"""Restore only original C100 after the B host verifies formal capture return.

No refunds, attempt recovery, quota reset, account or scope changes. A native
control ACK failure remains WRITE_INTENT and cannot be blindly repeated.
"""
from hashlib import sha256
import json
import re
import sys

from cj_usage.authorization_budget import AuthorizationBudget,HK_JOURNAL_ROOT,journal_state
from cj_usage.sublimits import policy,usage
from .app_smoke_ceiling import BASELINE,PROFILES
from .configuration import load_secret_environment,authorization

VERSION='G2C-App-smoke-closed-standing-restore.1'
MANUAL_VERSION='G2C-App-manual-smoke-closed-standing-restore.1'


def restore(budget,request):
    if type(request)is not dict:raise ValueError('exact reviewed closed C purpose request required')
    manual=request.get('version')==MANUAL_VERSION
    close_key='closed_manual_sha256'if manual else'closed_capture_sha256'
    keys={'version','expected_policy_sha256','restriction','closed_capture_sha256','ledger_id','producer_id','apply'}
    if manual:keys=(keys-{'closed_capture_sha256'})|{'closed_manual_sha256','expected_ledger'}
    if(set(request)!=keys or request['version']not in(VERSION,MANUAL_VERSION)
            or type(request['apply'])is not bool or type(request['restriction'])is not dict
            or any(type(request[k])is not str or re.fullmatch('[a-f0-9]{64}',request[k])is None
                   for k in('expected_policy_sha256',close_key))):
        raise ValueError('exact reviewed closed C purpose request required')
    if manual:
        anchor=request['expected_ledger']
        if(type(anchor)is not dict or set(anchor)!={'count','sha256'}
                or type(anchor['count'])is not int or anchor['count']<0
                or type(anchor['sha256'])is not str or re.fullmatch('[a-f0-9]{64}',anchor['sha256'])is None):
            raise ValueError('exact manual-close original ledger required')
    if(budget.ledger_id,budget.producer)!=(request['ledger_id'],request['producer_id']):
        raise ValueError('original producer and ledger required')
    original=request['restriction']
    if(original.get('version')!='G2C-App-smoke-purpose-restriction-result.1'
            or original.get('state')!='C_PURPOSE_RESTRICTED_ACKED_NOT_A_LEASE'
            or original.get('baseline_policy')!=BASELINE or original.get('new_money_cny')!=0
            or original.get('native_account_quota_changed')is not False):
        raise ValueError('original acknowledged restriction required')
    restricted=policy(original['restricted_policy']);standing=policy(BASELINE)
    bounds=(original.get('model_call_bound'),original.get('tool_call_bound'),original.get('cash_ceiling_cny'))
    if bounds not in PROFILES.values():raise ValueError('original approved purpose bounds required')
    models,tools,cash=bounds;before=original['original_usage']
    from cj_usage.authorization_budget import CNY_SCALE
    expected=dict(BASELINE,active_cap=min(BASELINE['active_cap'],before['total']+cash*CNY_SCALE),
        max_calls=before['calls']+models+tools,model_calls=before['model_calls']+models,tool_calls=before['tool_calls']+tools)
    if original['restricted_policy']!=expected:raise ValueError('original purpose policy does not match acknowledgement')
    if sha256(restricted.encode()).hexdigest()!=request['expected_policy_sha256']or restricted==standing:
        raise ValueError('exact original temporary C restriction required')
    with budget.connect()as db:
        db.execute('BEGIN');budget.require_producer(db);anchor=journal_state(db)
        if manual and dict(count=anchor[0],sha256=anchor[1])!=request['expected_ledger']:
            raise ValueError('original manual-close ledger changed; inspect only')
        if db.execute("SELECT policy FROM sublimit WHERE line='C'").fetchone()!=(restricted,):
            raise ValueError('current temporary policy changed; inspect only')
        used=usage(db,'C')
        others=db.execute("SELECT * FROM sublimit WHERE line<>'C' ORDER BY line").fetchall()
        scopes=db.execute('SELECT * FROM scope_sublimit ORDER BY scope_hash').fetchall()
        assignments=db.execute('SELECT * FROM attempt_sublimit ORDER BY attempt_id').fetchall()
    result=dict(version='G2C-App-smoke-closed-standing-result.1',state='READONLY_NOT_RESTORED',
        original_usage=used,ledger=dict(count=anchor[0],sha256=anchor[1]),standing_policy=BASELINE,
        **{close_key:request[close_key]},new_money_cny=0,native_quota_changed=False,
        attempts_refunded_or_deleted=0,provider_calls=0,ended_window='REMAINS_CLOSED')
    if manual:result['version']='G2C-App-manual-smoke-closed-standing-result.1'
    if not request['apply']:return result
    with budget.mutation()as db:
        if(journal_state(db)!=anchor or db.execute("SELECT policy FROM sublimit WHERE line='C'").fetchone()!=(restricted,)
                or usage(db,'C')!=used or db.execute("SELECT * FROM sublimit WHERE line<>'C' ORDER BY line").fetchall()!=others
                or db.execute('SELECT * FROM scope_sublimit ORDER BY scope_hash').fetchall()!=scopes
                or db.execute('SELECT * FROM attempt_sublimit ORDER BY attempt_id').fetchall()!=assignments):
            raise ValueError('original accounting changed before standing restore')
        if db.execute('UPDATE sublimit SET policy=? WHERE line=? AND policy=?',(standing,'C',restricted)).rowcount!=1:
            raise ValueError('original standing transition unavailable')
    result['state']='C_ORIGINAL_STANDING_RESTORED_ACKED'
    return result


def main():
    raw=sys.stdin.buffer.read(65537)
    if len(raw)>65536:raise ValueError('bounded original standing request required')
    from cj_strict_json import reject_duplicates
    request=json.loads(raw,object_pairs_hook=reject_duplicates(ValueError,'duplicate C restore field'))
    load_secret_environment('worker');authorization()
    budget=AuthorizationBudget(HK_JOURNAL_ROOT,authorization_guard=authorization,demo=True)
    print(json.dumps(restore(budget,request),sort_keys=True))


if __name__=='__main__':main()
