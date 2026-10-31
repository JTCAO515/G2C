"""Structured source-bound candidate builder; no authority or alternative checker."""
from copy import deepcopy
import json

from cj_needs.domain import validate_fields
from cj_feasibility.validator import Candidate
from cj_feasibility.proposed import evaluate
from .domain import packed
from .structured_v2 import validate_document

MODEL_VERSION='TRIP-model-plan.1'


def build(raw,capture):
    def unique(pairs):
        out={}
        for key,value in pairs:
            if key in out:raise ValueError('duplicate plan field')
            out[key]=value
        return out
    if type(raw) is not bytes or not 0<len(raw)<=1_000_000:raise ValueError('bounded plan required')
    model=json.loads(raw,object_pairs_hook=unique)
    if type(model) is not dict or set(model)!={'version','title','items','proposed_subjects'} or model['version']!=MODEL_VERSION:
        raise ValueError('explicit structured model plan required')
    document=dict(content_version='structured.2',title=model['title'],items=model['items'],sources=[])
    validate_document(document)
    before,revisions=capture.records()
    fields=deepcopy(before.fields)
    originals={item['item_id']:item for item in fields.get('fixed_items',[])}
    subjects=model['proposed_subjects']
    new_ids={item['id'] for item in document['items']} - set(originals)
    if type(subjects) is not dict or set(subjects)!=new_ids:raise ValueError('explicit proposed subjects required for each new item')
    proposed=[];selected=set()
    for item in document['items']:
        if item['verification']!='pending' or item['evidence'] or item['source_refs']:
            raise ValueError('model cannot supply approved evidence or source')
        if any(edge['utc_offset'].get('state')=='known' for edge in item['schedule'].values()):
            raise ValueError('model cannot invent an observed UTC offset')
        original=originals.get(item['id'])
        if original is None:
            # New model material remains unconfirmed intent/unknown occupancy.
            if item['source_category']!='unknown' or item['fixed']!={'state':'unknown'}:
                raise ValueError('new model items cannot invent source or fixed intent')
            value=dict(item_id=item['id'],kind='intent',description=item['text'],applies_to=subjects[item['id']],
                locked={'state':'unknown'},booking_status={'state':'unknown'})
            selected.add(item['id'])
        else:
            if item['fixed']!=original['locked']:raise ValueError('model cannot change explicit fixed intent')
            value=deepcopy(original)
            value['description']=item['text'];value['locked']=item['fixed']
            if original['locked']=={'state':'known','value':False}:selected.add(item['id'])
            expected='user_provided' if item['text']==original['description'] else 'unknown'
            if item['source_category']!=expected:raise ValueError('source association is not a model claim')
        for edge in ('start','end'):
            event=item['schedule'][edge]
            value[edge]={key:deepcopy(event[key]) for key in ('date','time','timezone')}
            value[edge]['place']=(deepcopy(original[edge]['place']) if original is not None else {'state':'unknown'})
        proposed.append(value)
    # Missing original items are explicitly outside generated edit permission.
    if not set(originals)<={item['item_id'] for item in proposed}:raise ValueError('original source item removed')
    fields['fixed_items']=proposed
    validate_fields(fields,complete=True)
    candidate=Candidate(before.needs_id,before.version,packed(fields))
    report=evaluate(before,revisions,candidate,selected_fields=frozenset({'fixed_items'}),selected_item_ids=frozenset(selected))
    if (report.status in ('INVALID','CONFLICT') or not any(c.code=='PROTECTED_SCOPE_UNCHANGED' and c.status=='PASS' for c in report.checks)):
        raise ValueError('source constraints or protected scope rejected')
    return packed(document),candidate,report
