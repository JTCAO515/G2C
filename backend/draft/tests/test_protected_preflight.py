"""Pure pre-city graph data; synthetic documents are not live source grants."""
from copy import deepcopy
from hashlib import sha256
import base64
import json
from pathlib import Path

import pytest

from cj_draft.calendar_plan import protected_base_data, compose, FIRST_PLAN
from cj_needs.domain import Snapshot
from cj_needs.revision_lease import LeaseUnavailable
from cj_trip.domain import packed
from cj_trip.structured_v4 import calendar_validation_view, validate_document
from test_rich_provider_source import harness

ROOT=Path(__file__).resolve().parents[3]
FIELDS=json.loads((ROOT/'contracts/message/trip-send-examples.2.json').read_bytes())['needs_basis']['fields']
RICH=json.loads((ROOT/'contracts/trip/structured-examples.4.json').read_bytes())['cases']['protected_fixed']['content']


def fields():
    value=deepcopy(FIELDS)
    value.pop('destination_timezone',None);value.pop('party_size',None)
    return value


def test_before_city_preserves_unknowns_and_does_not_create_dates_or_party():
    value=fields();fixed=value['fixed_items'][0]
    for edge in ('start','end'):
        fixed[edge]['timezone']={'state':'missing'}
        fixed[edge]['time']={'state':'unknown'}
    before=packed(value)
    result=protected_base_data(value,{'hotel-meetup':(2,2)},3)
    assert result['calendar']=={'state':'undated'}
    assert result['days']==[{'day_index':i} for i in (1,2,3)]
    item,=result['items']
    assert item['schedule']['start']==dict(day_index=2,time={'state':'unknown'},
        timezone={'state':'missing'},utc_offset={'state':'unknown'})
    assert all('date' not in event for event in item['schedule'].values())
    assert 'party_size' not in result and 'destination_timezone' not in result
    assert result['origins']=={'hotel-meetup':['fixed_fields']}
    assert packed(value)==before and set(result)=={'calendar','days','items','sources','origins'}


def test_same_data_merge_matches_existing_source_compose_without_snapshot_impersonation():
    # The old entry is exercised using its existing real value type, not a
    # SimpleNamespace/DTO pretending to be an issued source or live Snapshot.
    value=deepcopy(FIELDS);snapshot=Snapshot('fixture-needs',1,packed(value))
    raw,_=compose(packed(dict(version=FIRST_PLAN,title='Fixture',items=[],proposed_subjects={})),
        snapshot,{'hotel-meetup':(1,1)},3)
    document=json.loads(raw)
    data=protected_base_data(value,{'hotel-meetup':(1,1)},3)
    assert {key:data[key] for key in ('calendar','days','items','sources')}=={
        key:document[key] for key in ('calendar','days','items','sources')}


@pytest.mark.parametrize('version',['structured.3','structured.4'])
def test_same_id_is_once_and_retained_complete_metadata_and_sources_win(version):
    retained=deepcopy(RICH) if version=='structured.4' else calendar_validation_view(RICH)
    item=retained['items'][0];value=fields();fixed=value['fixed_items'][0]
    fixed['item_id']=item['id']
    first,last=(item['schedule'][edge]['day_index'] for edge in ('start','end'))
    before=packed(retained);original=packed(value)
    data=protected_base_data(value,{item['id']:(first,last)},len(retained['days']),retained=retained)
    assert data['items']==retained['items'] and data['sources']==retained['sources']
    assert len(data['items'])==len(retained['items'])
    assert data['origins'][item['id']]==['current_trip','fixed_fields']
    if version=='structured.4':
        assert all(key in data['items'][0] for key in ('place','note','tip','reason_refs'))
    data['items'][0]['text']='changed display copy';data['sources'].clear()
    assert packed(retained)==before and packed(value)==original


def test_code_fixed_ids_and_new_items_are_not_regenerated_or_merged_by_text():
    value=fields();first=value['fixed_items'][0]
    first['item_id']='fixed-'+sha256(first['description'].encode()).hexdigest()[:20]
    second=deepcopy(first);second['description']='第二天下午另一个已确定的集合'
    second['item_id']='fixed-'+sha256(second['description'].encode()).hexdigest()[:20]
    value['fixed_items'].append(second)
    mapping={first['item_id']:(1,1),second['item_id']:(2,2)}
    data=protected_base_data(value,mapping,3)
    assert [item['id'] for item in data['items']]==[first['item_id'],second['item_id']]
    assert [item['schedule']['start']['day_index'] for item in data['items']]==[1,2]


def test_full_rich_metadata_and_nonempty_legacy_source_bytes_are_preserved():
    retained=deepcopy(RICH);item=retained['items'][0];text=item['text']
    snapshot=packed(dict(display_text=text,record=dict(source=dict(request_ref='fixture-query',evidence='synthetic'),
        query={},place=dict(name_zh=text))))
    retained['sources']=[dict(id='fixture-source',kind='place',reference='fixture-query',text=text,
        snapshot_utf8_base64=base64.b64encode(snapshot).decode(),snapshot_sha256=sha256(snapshot).hexdigest(),
        evidence_level='synthetic')]
    item.update(source_category='queried',source_refs=['fixture-source'],note='汉'*500)
    validate_document(retained)  # Valid synthetic read shape, not live source eligibility.
    data=protected_base_data({}, {},len(retained['days']),retained=retained)
    assert packed(data['items'])==packed(retained['items'])
    assert packed(data['sources'])==packed(retained['sources'])
    assert len(packed(data['items']))>len(packed(data['items']).decode('utf8'))
    data['sources'][0]['text']='mutated copy'
    assert retained['sources'][0]['text']==text


def test_explicit_start_uses_ordinal_arithmetic_and_retained_calendar_cannot_change():
    value=fields();data=protected_base_data(value,{'hotel-meetup':(2,2)},3,start_date='2026-12-01')
    assert data['days'][1]=={'day_index':2,'date':'2026-12-02'}
    assert data['items'][0]['schedule']['start']['day_index']==2
    # Retained content is actual validated read data. Its existing date is not
    # replaced by an optional caller default or a fabricated destination zone.
    retained=deepcopy(RICH)
    with pytest.raises(ValueError):protected_base_data({}, {},len(retained['days']),
        retained=retained,start_date='2026-12-01')
    with pytest.raises(ValueError):protected_base_data(value,{'hotel-meetup':(1,1)},3,start_date='20261201')


@pytest.mark.parametrize('mapping', [{},{'hotel-meetup':(0,1)},{'hotel-meetup':(1,4)},
                                     {'hotel-meetup':(2,1)},{'hotel-meetup':(True,1)},
                                     {'hotel-meetup':(1,1),'foreign':(1,1)}])
def test_missing_extra_out_of_range_or_reversed_fixed_ordinals_are_not_inferred(mapping):
    with pytest.raises(ValueError):protected_base_data(fields(),mapping,3)


def test_source_current_ordinal_conflict_and_duplicate_fixed_ids_are_refused():
    retained=deepcopy(RICH);value=fields();fixed=value['fixed_items'][0];fixed['item_id']=retained['items'][0]['id']
    first,last=(retained['items'][0]['schedule'][edge]['day_index'] for edge in ('start','end'))
    with pytest.raises(ValueError):protected_base_data(value,{fixed['item_id']:(first+1,last+1)},
        len(retained['days']),retained=retained)
    value['fixed_items'].append(deepcopy(fixed))
    with pytest.raises(ValueError):protected_base_data(value,{fixed['item_id']:(first,last)},len(retained['days']))


def test_complete_over_60_data_is_never_truncated_and_old_compose_still_rejects():
    value=fields();prototype=deepcopy(value['fixed_items'][0]);value['fixed_items']=[];mapping={}
    for index in range(61):
        item=deepcopy(prototype);item['item_id']='fixed-'+str(index);value['fixed_items'].append(item)
        mapping[item['item_id']]=(1,1)
    data=protected_base_data(value,mapping,3)
    assert len(data['items'])==61 and len(data['origins'])==61
    snapshot=Snapshot('fixture-needs',1,packed(value))
    with pytest.raises(ValueError):compose(packed(dict(version=FIRST_PLAN,title='Fixture',items=[],proposed_subjects={})),
        snapshot,mapping,3)


@pytest.mark.parametrize('version',['structured.1','structured.2'])
def test_legacy_document_needs_its_explicit_bridge(version):
    with pytest.raises(ValueError):protected_base_data({}, {},3,retained={'content_version':version})


def test_data_is_neither_a_trip_document_nor_a_source_capture(harness):
    data=protected_base_data(fields(),{'hotel-meetup':(1,1)},3)
    with pytest.raises(ValueError):validate_document(data)
    h=harness
    with pytest.raises(LeaseUnavailable):h.source.seal_providers(h.binding,data)
    assert h.providers.capture_calls==0
