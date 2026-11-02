"""L0 data/transform checks only; runtime authority is verified in the PG suite."""
import base64,json,sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from hashlib import sha256
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'feasibility/tests'))
from test_validator import history,item,event
from cj_place import Config,ORIGIN,Response,prepare,parse_response
from datetime import datetime,timezone
from cj_place.models import Search
from cj_place.local_source import LocalPlaceProducer
from cj_trip.domain import packed,Trip
from cj_trip.manual import ManualEdit,prepare as prepare_one
from cj_trip.manual_needs import EditV2,prepare as prepare_two
from cj_manual_edit.scoped import Request,resolve,preview
from cj_needs.revision_lease import LeaseUnavailable
from cj_draft.place_plan import choices,build,MODEL_VERSION


class Capture:
    def __init__(self,seconds=True):
        clocks=('09:00:00','10:00:00','11:00:00','12:00:00','13:00:00','14:00:00') if seconds else ('09:00','10:00','11:00','12:00','13:00','14:00')
        values=[item(k,start=event(wall=clocks[2*i]),end=event(wall=clocks[2*i+1]),locked=i==0) for i,k in enumerate(('a','b','c'))]
        for v in values[1:]:v.update(kind='intent',booking_status={'state':'unknown'})
        self.value=history(dict(fixed_items=values))
    def records(self):return self.value


def batch(keyword='synthetic',ref='original',producer=None):
    config=Config(ORIGIN,4096,16384,5,60);query=Search(keyword,'synthetic',1,20)
    producer=producer or LocalPlaceProducer(config);at=datetime.now(timezone.utc)
    request=prepare(config,query,ref,at);status,payload=producer._response(query)
    response=Response(request.binding_digest,request.origin,request.path,status,payload if type(payload) is bytes else packed(payload),at)
    result=parse_response(config,request,response,now=at,evidence='synthetic')
    return SimpleNamespace(observations=(SimpleNamespace(operation_key='tool.0.0',request_ref=ref,result=result),))


def model(capture,available):
    fields=capture.records()[0].fields;items=[]
    for original in fields['fixed_items']:
        schedule={edge:{key:deepcopy(original[edge][key]) for key in ('date','time','timezone')} for edge in ('start','end')}
        for value in schedule.values():value['utc_offset']={'state':'unknown'}
        items.append(dict(id=original['item_id'],text=original['description'],verification='pending',evidence=[],schedule=schedule,
            fixed=original['locked'],source_category='user_provided',source_refs=[]))
    refs={}
    for row,choice in zip(items[1:],available):
        row.update(text=choice.source['text'],source_category='unknown');refs[row['id']]=choice.choice_id
    return dict(version=MODEL_VERSION,title='same names, distinct sources',items=items,proposed_subjects={},place_refs=refs)


def stored(document,item_id):
    row=next(v for v in document['items'] if v['id']==item_id)
    source=next(v for v in document['sources'] if v['id']==row['source_refs'][0])
    return source,json.loads(base64.b64decode(source['snapshot_utf8_base64']))['record']


@pytest.mark.parametrize('version',['structured.1','structured.2'])
def test_actual_synthetic_values_distinct_same_name_and_original_precision(version):
    capture=Capture();available=choices(batch());raw,candidate,report=build(packed(model(capture,available)),capture,available,version)
    doc=json.loads(raw);east,e=stored(doc,'b');west,w=stored(doc,'c')
    assert doc['items'][1]['text']==doc['items'][2]['text']=='合成酒店'
    assert east['id']!=west['id']
    assert (e['place']['provider_id'],w['place']['provider_id'])==('SYNTH_EAST','SYNTH_WEST')
    assert e['place']['coordinate']['value']==dict(raw='116.100000,39.100000',longitude='116.100000',latitude='39.100000',crs='GCJ-02')
    assert w['place']['coordinate']['value']['raw']=='116.200000,39.200000'
    assert e['place']['entrance_coordinate']['value']['raw']=='116.100100,39.100100'
    assert w['place']['exit_coordinate']==dict(state='missing',value=None)
    assert e['source']['request_ref']=='original' and e['source']['evidence']=='synthetic'
    assert e['query']==dict(keyword='synthetic',city='synthetic',page=1,page_size=20)
    assert all(v['verification']=='pending' and v['evidence']==[] for v in doc['items'])
    assert all(v['evidence_level']=='synthetic' for v in doc['sources'])
    assert report.status=='UNKNOWN'


@pytest.mark.parametrize('version',['structured.1','structured.2'])
def test_manual_and_scoped_keep_original_point_snapshots_and_unselected_item(version):
    capture=Capture();available=choices(batch());raw,_,_=build(packed(model(capture,available)),capture,available,version)
    before=json.loads(raw);trip=Trip('actual-trip',1,raw)
    def edit(**kwargs):return dict(version='TRIP-manual-edit.1' if version=='structured.1' else 'TRIP-manual-edit.2',request_id='request',trip_id=trip.trip_id,
        expected_version=trip.version,original_hash=sha256(raw).hexdigest(),title=None,order=None,changes=[],**kwargs)
    parse,prepare=(ManualEdit.parse,prepare_one) if version=='structured.1' else (EditV2.parse,prepare_two)
    request=edit();request['title']='user title only'
    changed=json.loads(prepare(trip,parse(packed(request))).content)
    assert changed['sources']==before['sources'] and changed['items']==before['items']
    request=edit();schedule=deepcopy(before['items'][1]['schedule']);schedule['start']['time']['value']='11:10:00';schedule['end']['time']['value']='12:10:00'
    request['changes']=[dict(item_id='b',field='schedule',value=schedule)]
    changed=json.loads(prepare(trip,parse(packed(request))).content)
    assert changed['sources']==before['sources'] and changed['items'][2]==before['items'][2]
    scope=resolve(trip,Request.parse(packed(dict(version='TRIP-scoped-request.1',request_id='request',trip_id=trip.trip_id,expected_version=1,
        original_hash=sha256(raw).hexdigest(),text='selected item time only',language='en',selection=dict(kind='items',item_ids=['b'])))))
    changed=json.loads(preview(scope,packed(request)).candidate.content)
    assert changed['sources']==before['sources'] and changed['items'][2]==before['items'][2]
    assert stored(changed,'b')==stored(before,'b') and stored(changed,'c')==stored(before,'c')
    # Existing frozen semantics: new words cannot borrow the old queried name.
    request=edit();request['changes']=[dict(item_id='b',field='text',value='explicit new user words')]
    changed=json.loads(prepare(trip,parse(packed(request))).content)
    assert changed['items'][1]['source_refs']==[]
    assert stored(changed,'c')==stored(before,'c')


@pytest.mark.parametrize('mutation',['foreign_choice','source_upload','queried_label','verified','different_name'])
def test_model_cannot_invent_or_borrow_sources(mutation):
    capture=Capture();available=choices(batch());value=model(capture,available)
    if mutation=='foreign_choice':value['place_refs']['b']=choices(batch(ref='other-run'))[0].choice_id
    elif mutation=='source_upload':value['sources']=[]
    elif mutation=='queried_label':value['items'][1]['source_category']='queried'
    elif mutation=='verified':value['items'][1].update(verification='verified',evidence=['invented'])
    else:value['items'][1]['text']='a different branch name'
    with pytest.raises(ValueError):build(packed(value),capture,available,'structured.2')


def test_optional_no_result_and_missing_coordinate_stay_unknown_without_zero_fill():
    capture=Capture();available=choices(batch('SYNTH_MISSING'));assert available==()
    raw,_,_=build(packed(model(capture,available)),capture,available,'structured.2')
    assert json.loads(raw)['sources']==[] and all(not i['source_refs'] for i in json.loads(raw)['items'])
    class Missing(LocalPlaceProducer):
        def _response(self,query):return 200,dict(status='1',info='OK',infocode='10000',count='1',pois=[dict(id='SYNTH_NO_COORD',name='合成未知坐标')])
    available=choices(batch(producer=Missing(Config(ORIGIN,4096,16384,5,60))))
    raw,_,_=build(packed(model(capture,available)),capture,available,'structured.2')
    _,record=stored(json.loads(raw),'b')
    assert record['place']['coordinate']==dict(state='missing',value=None)
    assert record['place']['provider_id']=='SYNTH_NO_COORD'


def test_structured_one_never_fills_missing_seconds_from_minute_precision():
    capture=Capture(seconds=False);available=choices(batch());value=model(capture,available)
    with pytest.raises(ValueError):build(packed(value),capture,available,'structured.1')
    raw,_,_=build(packed(value),capture,available,'structured.2')
    assert json.loads(raw)['items'][0]['schedule']['start']['time']==dict(state='known',value='09:00')


def test_failed_source_cannot_silently_publish_a_partial_place_set():
    first=batch();second=batch('SYNTH_RATE_LIMIT')
    combined=SimpleNamespace(observations=first.observations+second.observations)
    with pytest.raises(LeaseUnavailable):choices(combined)
