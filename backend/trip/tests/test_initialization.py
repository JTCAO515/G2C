import json
from hashlib import sha256
import pytest
from cj_trip.domain import Trip, Conflict, packed
from cj_trip.initialization import Initialization, initialize


def fixture():
    trip=Trip('trip-1',3,packed(dict(title='Original title',items=[dict(id='a',text='Tomorrow is not a date',verification='pending',evidence=[])])))
    event={key:{'state':'unknown'} for key in ('date','time','timezone','utc_offset')}
    raw=dict(version='TRIP-initialize.1',request_id='init-1',trip_id=trip.trip_id,expected_version=trip.version,
        original_hash=sha256(trip.content).hexdigest(),items=[dict(id='a',schedule=dict(start=event,end=event),fixed={'state':'unknown'})])
    return trip,raw


def test_explicit_unknown_initialization_preserves_original_and_no_text_inference():
    trip,raw=fixture();candidate=initialize(trip,Initialization.parse(packed(raw)))
    after=json.loads(candidate.content)
    assert after['items'][0]['text']=='Tomorrow is not a date'
    assert after['items'][0]['fixed']=={'state':'unknown'}
    assert after['items'][0]['schedule']['start']['date']=={'state':'unknown'}
    assert after['items'][0]['source_category']=='unknown'
    assert candidate.original.content==trip.content


@pytest.mark.parametrize('change',[
    lambda d:d['items'][0].update(text='unselected'),
    lambda d:d['items'].append(d['items'][0]),
    lambda d:d['items'][0]['schedule']['start'].update(timezone={'state':'known','value':'localtime'}),
    lambda d:d.update(owner='client'),
])
def test_invalid_explicit_initialization_rejects(change):
    trip,raw=fixture();change(raw)
    with pytest.raises(ValueError):Initialization.parse(packed(raw))


def test_missing_foreign_id_or_stale_base_refused():
    trip,raw=fixture();raw['items'][0]['id']='foreign'
    with pytest.raises(ValueError):initialize(trip,Initialization.parse(packed(raw)))
    trip,raw=fixture();request=Initialization.parse(packed(raw))
    with pytest.raises(Conflict):initialize(Trip(trip.trip_id,4,trip.content),request)
