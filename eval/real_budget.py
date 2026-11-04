"""Pre-dispatch conservative estimate, additional to B's unchanged sole journal.

JT PR540 caps. First round actual holds:137 model/54 paid tools. Six new smoke
cases expect16 model rounds and8 paid tool calls (fact intents cost no hold).
This is an estimate, never an invoice or permission to reset UNKNOWN amounts.
"""
from collections import Counter

MODEL_STOP = 400
TOOL_STOP = 160


def estimate(attempts, *, include_smoke):
    counts = Counter(v['kind'] for v in attempts)
    before = dict(model=13+counts['model'], tool=sum(counts[k] for k in ('place','route','weather')))
    added = dict(model=137+(16 if include_smoke else 0), tool=54+(8 if include_smoke else 0))
    after = {k:before[k]+added[k] for k in before}
    return dict(basis='C first real batch actual authorization holds + planned6 smoke minimum flow; not billed costs',
                counts=dict(counts), before_conservative_cny=before, additional_estimate_cny=added,
                projected_conservative_cny=after, stop_cny=dict(model=MODEL_STOP,tool=TOOL_STOP),
                within_stop_lines=after['model']<MODEL_STOP and after['tool']<TOOL_STOP,
                actual_billed_total='UNKNOWN', M1_hold_cny=13,
                quantity_limits=dict(place=1200,route=600,weather=200,fact=240))
