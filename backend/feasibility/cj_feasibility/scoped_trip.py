"""Scoped Trip adapter to the original protect/evaluate/output_check; no solver."""
from copy import deepcopy
import json
from cj_trip.domain import packed,Conflict
from cj_trip.needs_edit_store import mapped_item
from .validator import Candidate,Check,Evidence,_report
from .proposed import evaluate
from .output_check import verify_output
from .solver import Problem,Verification


def check(content,source,previous_fields,selected_ids,limits):
    before,revisions=source.records();fields=deepcopy(before.fields)
    old={v['item_id']:v for v in fields.get('fixed_items',[])}
    previous={v['item_id']:v for v in previous_fields.get('fixed_items',[])}
    document=json.loads(content);items={v['id']:v for v in document['items']}
    # Keep actual NEEDS items not displayed in this Trip. No inferred person,
    # booking/kind or fabricated Snapshot is introduced for unmapped Trip items.
    proposed=[mapped_item(items[v['item_id']],old,previous) if v['item_id'] in items else deepcopy(v)
              for v in fields.get('fixed_items',[])]
    for item in document['items']:
        if item['id'] not in old and item['id'] in previous:proposed.append(mapped_item(item,old,previous))
    fields['fixed_items']=proposed
    candidate=Candidate(before.needs_id,before.version,packed(fields))
    represented={v['item_id'] for v in proposed};selected=frozenset(set(selected_ids)&represented)
    # Already adopted extra declarations are retained, not new source revisions.
    selected|=frozenset(represented-set(old))
    report=evaluate(before,revisions,candidate,selected_fields=frozenset({'fixed_items'}),selected_item_ids=selected)
    if report.status in ('INVALID','CONFLICT'):raise Conflict('current NEEDS/protected constraints rejected')
    if represented<=set(old):
        verification=verify_output(Problem(before,revisions,candidate,frozenset({'fixed_items'}),selected,(),()),candidate,limits)
        if not verification.accepted and set(verification.codes)!={'OUTPUT_INSTANT_UNRESOLVED'}:
            raise Conflict('independent output invariants rejected')
    else:
        verification=Verification(False,('OUTPUT_INPUT_NOT_SOLVER_PROFILE',),
            '已采纳意图缺原求解器占用来源，保留未知。','Adopted intent lacks original solver occupancy provenance; unknown.')
    missing=tuple(item for item in document['items'] if item['id'] not in represented)
    checks=list(report.checks)
    if missing:
        checks.append(Check('TRIP_ITEM_METADATA_UNKNOWN','UNKNOWN',tuple(Evidence('items.'+v['id'],packed(v),None,None,None) for v in missing),
            tuple('items.'+v['id']+'.occupancy_participants_booking' for v in missing),
            '部分正式条目没有当前NEEDS占用/参与人/预订来源，不能推断整体可行。',
            'Some formal items lack current NEEDS occupancy/participants/booking evidence; overall feasibility is unknown.'))
    if not verification.accepted:
        checks.append(Check('INDEPENDENT_OUTPUT_UNKNOWN','UNKNOWN',(),verification.codes,verification.zh,verification.en))
    return candidate,_report(candidate,checks),verification
