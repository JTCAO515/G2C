"""Pre-dispatch conservative estimate, additional to B's unchanged sole journal.

JT 2026-11-06 raised model total and stop to10000, including M1.
The tool stop is10000 but its unchanged total200 cap remains binding.
First round actual holds:137 model/54 paid tools. Six new smoke
cases expect16 model rounds and8 paid tool calls (fact intents cost no hold).
This is an estimate, never an invoice or permission to reset UNKNOWN amounts.
"""
from collections import Counter
import json
from pathlib import Path
import sqlite3

MODEL_STOP = 10000
TOOL_STOP = 10000
MODEL_BUDGET = 10000
TOOL_BUDGET = 200
STATE = Path.home()/'.local/share/g2c/m4-real-services'


def stop_reached(counts):
    """Current held usage, including UNKNOWN; no next-case dispatch at a ceiling."""
    model = 13+counts.get('model',0)
    tools = sum(counts.get(k,0) for k in ('place','route','weather'))
    return model>=min(MODEL_STOP,MODEL_BUDGET) or tools>=min(TOOL_STOP,TOOL_BUDGET)


def verified_journal():
    """Read only; never create a missing ledger or accept rolled-back history."""
    path=STATE/'m4-outflows.sqlite'
    with sqlite3.connect('file:'+str(path)+'?mode=ro',uri=True) as db:
        rows=db.execute('SELECT id,kind,input_sha,state,receipt FROM attempt').fetchall()
    records=[dict(attempt_id=a,kind=k,input_sha=h,state=s,receipt=None if r is None else json.loads(r)) for a,k,h,s,r in rows]
    actual={r['attempt_id']:r for r in records}
    baseline=json.loads(Path(__file__).with_name('authorization_checkpoint.json').read_bytes())
    for original in baseline['baseline']:
        row=actual.get(original['attempt_id'])
        if row is None or any(row[k]!=original[k] for k in ('kind','input_sha')):
            raise ValueError('original_authorization_history_missing_or_changed_no_dispatch')
    return records


def estimate(attempts, *, include_smoke):
    counts = Counter(v['kind'] for v in attempts)
    before = dict(model=13+counts['model'], tool=sum(counts[k] for k in ('place','route','weather')))
    added = dict(model=137+(16 if include_smoke else 0), tool=54+(8 if include_smoke else 0))
    after = {k:before[k]+added[k] for k in before}
    within_stops = after['model']<MODEL_STOP and after['tool']<TOOL_STOP
    within_budget = after['model']<=MODEL_BUDGET and after['tool']<=TOOL_BUDGET
    return dict(basis='C first real batch actual authorization holds + planned6 smoke minimum flow; not billed costs',
                counts=dict(counts), before_conservative_cny=before, additional_estimate_cny=added,
                projected_conservative_cny=after, stop_cny=dict(model=MODEL_STOP,tool=TOOL_STOP),
                budget_cny=dict(model=MODEL_BUDGET,tool=TOOL_BUDGET),
                within_stop_lines=within_stops, within_budget=within_budget,
                within_authorization=within_stops and within_budget,
                policy_ref='https://github.com/JTCAO515/G2C/issues/495#issuecomment-6644812116',
                model_policy_ref='https://github.com/JTCAO515/G2C/issues/495#issuecomment-6688002330',
                actual_billed_total='UNKNOWN', M1_hold_cny=13,
                quantity_limits=dict(place=1200,route=600,weather=200,fact=240))
