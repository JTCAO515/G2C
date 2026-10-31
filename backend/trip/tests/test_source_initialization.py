import json
import pytest
from cj_trip.domain import packed
from cj_trip.source_initialization import SourceInitialization,SourceInitializationSave


def request():
    event={key:dict(state='unknown') for key in ('date','time','timezone','utc_offset')}
    return dict(version='TRIP-source-initialize.1',needs_reference=dict(id='visit',expected_version=1),
        initialization=dict(version='TRIP-initialize.1',request_id='explicit-init',trip_id='original',expected_version=1,
            original_hash='a'*64,items=[dict(id='a',schedule=dict(start=event,end=event),fixed=dict(state='known',value=False))]))


def test_new_source_wrapper_retains_original_input_and_manual_grammar():
    raw=packed(request());value=SourceInitialization.parse(raw)
    assert value.raw==raw and value.needs_id=='visit' and value.needs_version==1
    assert value.initialization.raw==packed(request()['initialization'])
    assert value.request_id=='explicit-init'
    raw=packed(dict(version='TRIP-source-initialize-save.1',action_id='explicit-save',proposal_id='source-init.abc',candidate_hash='b'*64))
    assert SourceInitializationSave.parse(raw).raw==raw


@pytest.mark.parametrize('mode',['old-version','extra','ref-extra','bool-version','large-version','unknown-item-field','noncanonical','large-input'])
def test_source_wrapper_refuses_unknown_or_inferred_inputs(mode):
    d=request()
    if mode=='old-version':d['version']='TRIP-initialize.1'
    if mode=='extra':d['source_authorized']=True
    if mode=='ref-extra':d['needs_reference']['hash']='b'*64
    if mode=='bool-version':d['needs_reference']['expected_version']=True
    if mode=='large-version':d['needs_reference']['expected_version']=129
    if mode=='unknown-item-field':d['initialization']['items'][0]['text']='model text'
    raw=json.dumps(d).encode() if mode=='noncanonical' else packed(d)
    if mode=='large-input':raw=b' '*1_000_001
    with pytest.raises(ValueError):SourceInitialization.parse(raw)
