from copy import deepcopy
from hashlib import sha256
import json
import pytest
from cj_trip.domain import Trip,packed,Conflict
from cj_manual_edit.scoped import Request,resolve,preview


def known(value):return dict(state='known',value=value)
def event(day,clock):return dict(date=known(day),time=known(clock),timezone=known('Asia/Shanghai'),utc_offset=dict(state='unknown'))
def original():
    def item(key,day,start,end,locked):return dict(id=key,text=key,verification='pending',evidence=[],
        schedule=dict(start=event(day,start),end=event(day,end)),fixed=known(locked),source_category='user_provided',source_refs=[])
    return Trip('formal-trip',7,packed(dict(content_version='structured.2',title='真实结构 / explicit',sources=[],
        items=[item('a','2026-11-01','09:00','10:00',True),item('b','2026-11-02','09:00','10:00',False),item('c','2026-11-02','11:00','12:00',False)])))
def request(trip,text='第二天轻松一点',selection=None,language='zh-Hans'):
    return Request.parse(packed(dict(version='TRIP-scoped-request.1',request_id='source-request',trip_id=trip.trip_id,
        expected_version=trip.version,original_hash=sha256(trip.content).hexdigest(),text=text,language=language,
        selection=selection or dict(kind='dates',dates=['2026-11-02']))))
def edit(trip,changes,order=None,title=None):return packed(dict(version='TRIP-manual-edit.2',request_id='source-request',trip_id=trip.trip_id,
    expected_version=trip.version,original_hash=sha256(trip.content).hexdigest(),title=title,changes=changes,order=order))
def changed(key,field='text',value='本次较轻松 / lighter this time'):return dict(item_id=key,field=field,value=value)


def test_zh_en_preserve_same_explicit_trip_and_scope_and_other_day():
    trip=original();zh=resolve(trip,request(trip));en=resolve(trip,request(trip,'Make day 2 more relaxed',language='en'))
    assert zh.status==en.status=='READY';assert zh.selected_ids==en.selected_ids==('b','c')
    result=preview(zh,edit(trip,[changed('b')]))
    assert result.status=='PROVISIONAL';assert result.can_publish is False and zh.can_publish is False
    before=json.loads(trip.content);after=json.loads(result.candidate.content)
    assert packed(before['items'][0])==packed(after['items'][0]);assert before['items'][2]==after['items'][2]
    assert after['items'][1]['source_category']=='unknown'
    assert result.time_report.status=='UNKNOWN';assert result.reason_zh and result.reason_en
    assert result.candidate.original==trip and not hasattr(result,'save')


@pytest.mark.parametrize('text',['第三天轻松一点','第一天轻松一点','tomorrow easier','今天放松','day 1 and day 2','第十一天','day twenty','11th day','day 0'])
def test_ambiguous_or_conflicting_reference_requires_clarification(text):
    trip=original();value=resolve(trip,request(trip,text));assert value.status=='CLARIFICATION_REQUIRED'
    with pytest.raises(ValueError):preview(value,edit(trip,[changed('b')]))


def test_fixed_or_unknown_items_cannot_be_unlocked_by_model():
    trip=original();value=resolve(trip,request(trip,'only selected item',dict(kind='items',item_ids=['a'])))
    with pytest.raises(Conflict):preview(value,edit(trip,[changed('a')]))
    with pytest.raises(ValueError):preview(value,edit(trip,[changed('a','fixed',known(False))]))


def test_outside_date_title_or_global_order_only_requests_new_selection():
    trip=original();scope=resolve(trip,request(trip))
    for raw in (edit(trip,[changed('a')]),edit(trip,[],title='whole trip'),edit(trip,[],order=['b','a','c'])):
        value=preview(scope,raw);assert value.status=='EXPANSION_REQUIRED';assert value.candidate is None and not value.can_publish
    assert trip==original()


def test_same_day_selected_items_can_reorder_without_changing_other_positions():
    trip=original();value=preview(resolve(trip,request(trip)),edit(trip,[],order=['a','c','b']))
    assert [v['id'] for v in json.loads(value.candidate.content)['items']]==['a','c','b']
    assert json.loads(value.candidate.content)['items'][0]==json.loads(trip.content)['items'][0]


def test_unknown_date_or_partly_selected_cross_day_never_infers_scope():
    for mode in ('unknown','cross'):
        doc=json.loads(original().content)
        doc['items'][2]['schedule']['end']['date']=dict(state='unknown') if mode=='unknown' else known('2026-11-03')
        trip=Trip('formal-trip',7,packed(doc))
        assert resolve(trip,request(trip)).status=='CLARIFICATION_REQUIRED'


def test_stale_trip_request_edit_or_duplicate_selection_refuses():
    trip=original();req=request(trip)
    with pytest.raises(Conflict):resolve(Trip(trip.trip_id,8,trip.content),req)
    with pytest.raises(ValueError):request(trip,selection=dict(kind='items',item_ids=['b','b']))
    with pytest.raises(ValueError):resolve(trip,request(trip,selection=dict(kind='items',item_ids=['absent'])))
    raw=json.loads(edit(trip,[changed('b')]));raw['expected_version']=6
    with pytest.raises(Conflict):preview(resolve(trip,req),packed(raw))


def test_explicit_reversed_time_remains_same_feasibility_conflict():
    trip=original();schedule=deepcopy(json.loads(trip.content)['items'][1]['schedule'])
    schedule['start']['time']=known('10:00');schedule['end']['time']=known('09:00')
    with pytest.raises(Conflict):preview(resolve(trip,request(trip)),edit(trip,[changed('b','schedule',schedule)]))


@pytest.mark.parametrize('field,value',[('text',' '*2001),('text','x'*2001),('selection',{'kind':[]}),('language','fr')])
def test_external_request_limits_and_selection_grammar_are_not_inferred(field,value):
    raw=json.loads(request(original()).raw);raw[field]=value
    with pytest.raises(ValueError):Request.parse(packed(raw))


def test_selecting_both_cross_day_endpoints_does_not_authorize_unselected_middle_day():
    doc=json.loads(original().content)
    doc['items'][2]['schedule']['end']['date']=known('2026-11-04')
    trip=Trip('formal-trip',7,packed(doc))
    scope=resolve(trip,request(trip,'selected dates',dict(kind='dates',dates=['2026-11-02','2026-11-04'])))
    assert scope.status=='CLARIFICATION_REQUIRED' and not scope.can_publish
