"""Structured grammar fixtures do not establish source authority or feasibility."""
from copy import deepcopy
import pytest
from cj_trip.structured import validate_document


def unknown():return {'state':'unknown'}
def event():return {key:unknown() for key in ('date','time','timezone','utc_offset')}
def document():
    return dict(content_version='structured.1',title='明确标题 / explicit title',sources=[],items=[dict(
        id='item-1',text='Tomorrow 09:00 is free text only',verification='pending',evidence=[],
        schedule=dict(start=event(),end=event()),fixed=unknown(),source_category='user_provided',source_refs=[])])


def test_unknown_is_not_inferred_from_free_text_or_device():
    value=document();before=deepcopy(value)
    validate_document(value)
    assert value==before
    assert value['items'][0]['schedule']['start']['date']==unknown()


def test_explicit_cross_day_and_unknown_fixed_are_structurally_valid():
    value=document()
    for edge,day in (('start','2026-11-01'),('end','2026-11-02')):
        value['items'][0]['schedule'][edge]=dict(date={'state':'known','value':day},time={'state':'known','value':'23:00:00'},
            timezone={'state':'known','value':'Asia/Shanghai'},utc_offset=unknown())
    validate_document(value)


@pytest.mark.parametrize('change',[
    lambda d:d['items'].append(deepcopy(d['items'][0])),
    lambda d:d['items'][0]['fixed'].update(value=False),
    lambda d:d['items'][0].update(fixed={'state':'known','value':1}),
    lambda d:d['items'][0]['schedule']['start'].update(time={'state':'known','value':'tomorrow'}),
    lambda d:d['items'][0]['schedule']['start'].update(date={'state':'known','value':'2026-02-30'}),
    lambda d:d['items'][0]['schedule']['start'].update(timezone={'state':'known','value':'localtime'}),
    lambda d:d['items'][0]['schedule']['start'].update(utc_offset={'state':'known','value':'+99:00'}),
    lambda d:d['items'][0].update(verification='verified'),
    lambda d:d.update(owner='caller'),
    lambda d:d['items'][0].update(source_category='queried')])
def test_invalid_structures_reject(change):
    value=document();change(value)
    with pytest.raises(ValueError):validate_document(value)
