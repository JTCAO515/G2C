import json
from hashlib import sha256
import pytest
from test_place_plan import Capture,batch,model,stored
from cj_draft.place_plan import choices,build
from cj_trip.domain import packed,Trip
from cj_trip.manual_needs import NeedsEdit
from cj_trip.manual_needs_v2 import NeedsEditV2,checked
from cj_feasibility.scoped_trip import check as check_scoped
from cj_feasibility.solver import Limits
from datetime import datetime,timezone


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


def test_adopted_baseline_retains_only_unchanged_mutable_declarations_not_fixed_changes():
    from cj_trip.domain import Conflict
    capture=Capture();available=choices(batch());raw,candidate,_=build(packed(model(capture,available)),capture,available,'structured.2')
    limits=Limits(datetime(2026,11,1,tzinfo=timezone.utc),7*86400,1,10_000_000,60,120,128,.05,.05,100)
    previous=json.loads(candidate.content)
    # Default frozen checker still rejects an unselected override of canonical
    # NEEDS; the new opt-in accepts only this already adopted equal declaration.
    with pytest.raises(Conflict):check_scoped(raw,capture,previous,('b',),limits)
    _,report,_=check_scoped(raw,capture,previous,('b',),limits,retain_adopted=True)
    assert report.status=='UNKNOWN'
    changed=json.loads(raw);changed['items'][2]['schedule']['end']['time']['value']='14:10:00'
    with pytest.raises(Conflict):check_scoped(packed(changed),capture,previous,('b',),limits,retain_adopted=True)
    changed=json.loads(raw);changed['items'][0]['text']='changed fixed original'
    with pytest.raises(Conflict):check_scoped(packed(changed),capture,previous,('b',),limits,retain_adopted=True)
