"""Explicit flat data5 boundary, compiled into the existing checked data4 path."""
import json
from pydantic import ValidationError
from cj_agent.lio_intake_flat_schema import FlatIntake,FIXED_VALUES
from cj_needs.domain import InvalidInput
from .lio_national_intake import parse

EXTRA_OBSERVATIONS=frozenset({'pace','budget_currency','budget_total','budget_per_person','budget_paid',
    'budget_basis','budget_includes','overseas_timezone'})
EXTRA_EVENTS=frozenset({'arrival','departure','overseas_departure'})
EXTRA_COLLECTIONS=frozenset({'companions','temporary_conditions'})
PARTS=('date','time','timezone','place')


def _observations(values,unknown,uncertain):
    allowed=set(values)
    if len(set(unknown))!=len(unknown) or not set(unknown)<=allowed or not set(uncertain)<=allowed or set(unknown)&set(uncertain):
        raise InvalidInput('flat unknown/uncertain paths must be explicit and disjoint')
    if any(not note.strip() or len(note.encode())>4096 for note in uncertain.values()):
        raise InvalidInput('original uncertainty note required')
    result={}
    for path,value in values.items():
        if path in unknown or path in uncertain:
            if value is not None:raise InvalidInput('unknown flat fact cannot also be known')
            result[path]=dict(state='unknown') if path in unknown else dict(state='uncertain',note=uncertain[path])
        else:result[path]=dict(state='missing') if value is None else dict(state='known',value=value)
    return result


def parse_flat(raw,turns):
    from cj_needs.domain import decode
    value=decode(raw.encode() if type(raw) is str else raw)
    try:dto=FlatIntake.model_validate(value)
    except ValidationError:raise InvalidInput('exact typed flat intake required') from None
    data=dto.model_dump(exclude_unset=True)
    return compile_flat(data,turns)


def compile_flat(data,turns):
    """Compile an already validated, code-owned flat DTO representation."""
    core=_observations({key:data[key] for key in ('start_date','party_size')},data['unknown_fields'],data['uncertain_fields'])
    extra=data['extra_fields']
    extra_values={}
    for key in extra:
        if key in EXTRA_OBSERVATIONS:extra_values[key]=extra[key]
        elif key in EXTRA_EVENTS:
            for part in PARTS:extra_values[key+'.'+part]=None if extra[key] is None else extra[key][part]
        elif key not in EXTRA_COLLECTIONS:raise InvalidInput('noncanonical extra field required')
    optional=_observations(extra_values,data['extra_unknown_fields'],data['extra_uncertain_fields'])
    fixed_observations=[_observations({key:item[key] for key in FIXED_VALUES},item['unknown_fields'],item['uncertain_fields']) for item in data['fixed_items']]
    # Non-execution consumes no planning parameters. Supplied optional facts do
    # not become required execution inputs or a path to a writer.
    common={key:data[key] for key in ('intent','reply','needs_tools','city','current_source_index')}
    if data['intent'] in ('consult','discuss','cancel'):
        compiled=dict(version='LIO-planning-intake.4',**common,duration_days=None,start_date=None,
            extraction=None,field_sources={})
        return parse(json.dumps(compiled,ensure_ascii=False),turns,version='LIO-planning-intake.4')
    fields={}
    for key,item in extra.items():
        if key in EXTRA_OBSERVATIONS:
            fields[key]=optional[key]
        elif key in EXTRA_EVENTS:
            fields[key]={part:optional[key+'.'+part] for part in PARTS}
        else:fields[key]=item
    fields['party_size']=core['party_size']
    fixed=[]
    for index,(item,observed) in enumerate(zip(data['fixed_items'],fixed_observations)):
        primary=dict(source_index=item['source_index'],quote=item['quote'])
        result=dict(item_id='unconfirmed-'+str(index),kind=item['kind'],label=item['label'],
            source_ref=primary,detail_refs=item['detail_refs'],applies_to=item['applies_to'],
            locked=observed['locked'],
            booking_status=observed['booking_status'])
        for edge in ('start','end'):
            result[edge]={part:observed[edge+'_'+part] for part in PARTS}
            place=item[edge+'_place']
            if place is not None and not any(place in ref['quote'] for ref in [primary,*item['detail_refs']]):
                raise InvalidInput('fixed place must be an original source span')
        fixed.append(result)
    fields['fixed_items']=fixed
    compiled=dict(version='LIO-planning-intake.4',**common,duration_days=data['duration_days'],
        start_date=core['start_date'],
        extraction=dict(version='LIO-execution-extraction.1',fields=fields,
            unresolved=data['unresolved'],long_term_requests=data['long_term_requests']),field_sources=data['field_sources'])
    return parse(json.dumps(compiled,ensure_ascii=False),turns,version='LIO-planning-intake.4')
