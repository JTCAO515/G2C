import json
from hashlib import sha256
import pytest
from test_place_plan import Capture,batch,model,stored
from cj_draft.place_plan import choices,build
from cj_trip.domain import packed,Trip
from cj_trip.manual_needs import NeedsEdit
from cj_trip.manual_needs_v2 import NeedsEditV2,checked


@pytest.mark.parametrize('version',['structured.1','structured.2'])
def test_appended_manual_parser_and_same_source_constraints_preserve_point_data(version):
    capture=Capture();available=choices(batch());raw,_,_=build(packed(model(capture,available)),capture,available,version)
    trip=Trip('trip',1,raw);snapshot=capture.records()[0]
    edit=dict(version='TRIP-manual-edit.1' if version=='structured.1' else 'TRIP-manual-edit.2',request_id='edit',trip_id='trip',expected_version=1,
        original_hash=sha256(raw).hexdigest(),title='explicit title',changes=[],order=None)
    value=packed(dict(version='TRIP-needs-edit.2',needs_reference=dict(id=snapshot.needs_id,expected_version=snapshot.version),edit=edit))
    request=NeedsEditV2.parse(value)
    with pytest.raises(ValueError):NeedsEdit.parse(value)
    result,_,_=checked(trip,request,capture,snapshot.fields)
    assert json.loads(result.content)['sources']==json.loads(raw)['sources']
    assert stored(json.loads(result.content),'b')==stored(json.loads(raw),'b')
    assert stored(json.loads(result.content),'c')==stored(json.loads(raw),'c')
    wrong=json.loads(value);wrong['edit']['version']='TRIP-manual-edit.2' if version=='structured.1' else 'TRIP-manual-edit.1'
    with pytest.raises(ValueError):checked(trip,NeedsEditV2.parse(packed(wrong)),capture,snapshot.fields)
