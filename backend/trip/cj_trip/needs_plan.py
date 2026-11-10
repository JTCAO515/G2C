"""Structured source-bound candidate builder; no authority or alternative checker."""
from copy import deepcopy
import json

from cj_needs.domain import validate_fields
from cj_feasibility.validator import Candidate
from cj_feasibility.proposed import evaluate
from .domain import packed
from .structured import FieldRejected,SourceRejected,_fields
from .structured_v2 import validate_document
from cj_strict_json import reject_duplicates

MODEL_VERSION='TRIP-model-plan.1'


def parse_model(raw, *, versions=(MODEL_VERSION,), source_title_versions=()):
    if type(raw) is not bytes or not 0<len(raw)<=1_000_000:
        raise FieldRejected('plan','bounded plan bytes required')
    try:
        model=json.loads(raw,object_pairs_hook=reject_duplicates(ValueError,'duplicate plan field'))
    except (ValueError,RecursionError):
        raise FieldRejected('plan','strict JSON object without duplicate fields required') from None
    fields={'version','title','items','proposed_subjects'}
    if type(model) is dict and model.get('version') in source_title_versions:
        fields.remove('title')
    _fields(model,fields,'plan','exact model plan fields required')
    if model['version'] not in versions:
        raise FieldRejected('version',' or '.join(versions)+' required')
    return model


def build(raw,capture):
    return _build(raw,capture,{})


def _build(raw,capture,adopted):
    model=parse_model(raw)
    document=dict(content_version='structured.2',title=model['title'],items=model['items'],sources=[])
    validate_document(document)
    before,revisions=capture.records()
    fields=deepcopy(before.fields)
    originals={item['item_id']:item for item in fields.get('fixed_items',[])}
    subjects=model['proposed_subjects']
    new_ids={item['id'] for item in document['items']} - set(originals) - set(adopted)
    if type(subjects) is not dict or set(subjects)!=new_ids:
        raise SourceRejected('proposed_subjects','explicit proposed subjects required for each new item')
    proposed=[];selected=set()
    for index,item in enumerate(document['items']):
        path=f'items[{index}]'
        for field,expected in (('verification','pending'),('evidence',[]),('source_refs',[])):
            if item[field]!=expected:raise SourceRejected(path+'.'+field,'model cannot supply approved evidence or source')
        for edge,event in item['schedule'].items():
            if event['utc_offset']['state']=='known':
                raise SourceRejected(path+'.schedule.'+edge+'.utc_offset','model cannot invent an observed UTC offset')
        original=originals.get(item['id'])
        if original is None and item['id'] in adopted:
            value=deepcopy(adopted[item['id']]);value['description']=item['text']
            selected.add(item['id'])
        elif original is None:
            # New model material remains unconfirmed intent/unknown occupancy.
            if item['source_category']!='unknown':
                raise SourceRejected(path+'.source_category','new model items cannot invent source')
            if item['fixed']!={'state':'unknown'}:
                raise SourceRejected(path+'.fixed','new model items cannot invent fixed intent')
            value=dict(item_id=item['id'],kind='intent',description=item['text'],applies_to=subjects[item['id']],
                locked={'state':'unknown'},booking_status={'state':'unknown'})
            selected.add(item['id'])
        else:
            if item['fixed']!=original['locked']:
                raise SourceRejected(path+'.fixed','model cannot change explicit fixed intent')
            value=deepcopy(original)
            value['description']=item['text'];value['locked']=item['fixed']
            if original['locked']=={'state':'known','value':False}:selected.add(item['id'])
            expected='user_provided' if item['text']==original['description'] else 'unknown'
            if item['source_category']!=expected:
                raise SourceRejected(path+'.source_category','source association is not a model claim')
        for edge in ('start','end'):
            event=item['schedule'][edge]
            value[edge]={key:deepcopy(event[key]) for key in ('date','time','timezone')}
            value[edge]['place']=(deepcopy(original[edge]['place']) if original is not None else deepcopy(adopted[item['id']][edge]['place']) if item['id'] in adopted else {'state':'unknown'})
        proposed.append(value)
    # Missing original items are explicitly outside generated edit permission.
    if not set(originals)<={item['item_id'] for item in proposed}:
        raise SourceRejected('items','original source item removed')
    fields['fixed_items']=proposed
    try:validate_fields(fields,complete=True)
    except ValueError:raise SourceRejected('fixed_items','projected NEEDS fields invalid') from None
    candidate=Candidate(before.needs_id,before.version,packed(fields))
    report=evaluate(before,revisions,candidate,selected_fields=frozenset({'fixed_items'}),selected_item_ids=frozenset(selected))
    if (report.status in ('INVALID','CONFLICT') or not any(c.code=='PROTECTED_SCOPE_UNCHANGED' and c.status=='PASS' for c in report.checks)):
        rejection=next((c.code for c in report.checks if c.status in ('INVALID','CONFLICT')
                        or c.code=='LOCK_UNKNOWN_CHANGED'),'PROTECTED_SCOPE_UNCHANGED required')
        raise SourceRejected('fixed_items',rejection)
    return packed(document),candidate,report
