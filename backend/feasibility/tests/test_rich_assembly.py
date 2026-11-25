from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
from threading import Event

import pytest

from cj_feasibility.rich_assembly import Activity, assemble, assemble_unconfirmed
from cj_feasibility.rich_edges import activity_windows
from cj_feasibility.rich_solver import DAY, Limits, Window
from cj_trip.domain import packed
from cj_trip.rich_reasons import ProfileFact
from cj_trip.rich_source import capture
from cj_trip.structured import FieldRejected, SourceRejected
from cj_trip.structured_v4 import adjacent_pairs, validate_candidate
from cj_trip.structured_v4 import ITEM_EXTRA

ROOT = Path(__file__).resolve().parents[3]
CASES = json.loads((ROOT/'contracts/trip/structured-examples.4.json').read_bytes())['cases']


def source_for(case):
    return capture(packed(case['source']), **case['host_expected'])


def arguments(case, **kwargs):
    doc = case['content']
    bounds = tuple(Activity(item['id'],(Window((item['schedule']['start']['day_index']-1)*DAY,
                                               len(doc['days'])*DAY-1),),True,
                            'dinner' if item['kind']=='meal' else None) for item in doc['items'])
    result = dict(source=source_for(case),
                  facts=tuple(ProfileFact(k,v,'native formatted value') for k,v in case['source']['profile_states'].items()),
                  activities=bounds, edges=activity_windows(len(doc['days']),arrival_clock=0,
                                                           departure_clock=23*3600,departure_mode='train'),
                  phase='order',locale='zh',limits=Limits(max_seconds=2),stop=Event())
    result.update(kwargs)
    return result


def reset_legs(doc):
    doc['legs'] = [dict(day_index=day,from_item_id=a,to_item_id=b,state='unconfirmed',mode=None,
                        duration_seconds=None,distance_m=None,source=None,
                        time_semantics='provider_estimate_at_query_time',future_guaranteed=False)
                   for day,a,b in adjacent_pairs(doc)]


def light_case():
    case = deepcopy(CASES['unconfirmed'])
    case['content']['items'] = [i for i in case['content']['items'] if i['id'] in ('item-1','item-4','item-5')]
    reset_legs(case['content'])
    return case


def test_explicit_unconfirmed_entry_preserves_complete_light_recipe_without_inventing_proximity():
    case=light_case();args=arguments(case,edges=activity_windows(2))
    args['activities']=tuple(replace(a,nearby=None)for a in args['activities'])
    ids=frozenset(a.item_id for a in args['activities'])
    normal=assemble(case['content'],**args)
    assert normal.status=='UNKNOWN'and normal.content is None
    result=assemble_unconfirmed(case['content'],**args,unconfirmed_items=ids)
    assert result.status=='UNCONFIRMED_SKELETON'and result.unconfirmed_items==tuple(sorted(ids))
    value=json.loads(result.content);validate_candidate(value,args['source'])
    assert {i['id']for i in value['items']}==ids
    assert all(i['place']==next(x for x in case['content']['items']if x['id']==i['id'])['place']for i in value['items'])
    assert all(leg['state']=='unconfirmed'and leg['duration_seconds']is None for leg in value['legs'])
    assert all(a.nearby is None for a in args['activities'])


def test_unconfirmed_entry_does_not_cover_unexplained_unknown_or_known_false_proximity():
    case=light_case();args=arguments(case,edges=activity_windows(2))
    args['activities']=tuple(replace(a,nearby=None)for a in args['activities'])
    result=assemble_unconfirmed(case['content'],**args,unconfirmed_items=frozenset({'item-1'}))
    assert result.status=='UNKNOWN'and result.content is None
    args['activities']=tuple(replace(a,nearby=False)for a in args['activities'])
    result=assemble_unconfirmed(case['content'],**args,unconfirmed_items=frozenset(a.item_id for a in args['activities']))
    # JT 2026-11-26: known-far edge days save with disclosure instead of CONFLICT; the
    # unconfirmed entry still cannot cover unexplained UNKNOWN (asserted above).
    assert result.status=='UNCONFIRMED_SKELETON'and result.edge_far


def test_unconfirmed_entry_cannot_bypass_source_edge_conflicts_or_stop():
    case=light_case();ids=frozenset(i['id']for i in case['content']['items']);args=arguments(case)
    args['stop'].set()
    result=assemble_unconfirmed(case['content'],**args,unconfirmed_items=ids)
    assert result.content is None
    with pytest.raises(ValueError):assemble_unconfirmed(case['content'],**args,unconfirmed_items=frozenset())
    with pytest.raises(ValueError):assemble_unconfirmed(case['content'],**args,unconfirmed_items=frozenset({'invented-item'}))
    bad=deepcopy(case);bad['content']['items'][0]['reason_refs']=['invented-factor']
    with pytest.raises(FieldRejected):assemble_unconfirmed(bad['content'],**arguments(bad),unconfirmed_items=ids)


def test_order_assembly_is_pure_and_independently_valid_structured4_without_fake_dates():
    case = deepcopy(CASES['unconfirmed'])
    before = deepcopy(case)
    args = arguments(case)
    result = assemble(case['content'],**args)
    assert result.status=='CONDITIONAL_SCHEDULE'
    value = json.loads(result.content)
    validate_candidate(value,args['source'])
    assert value['calendar']==dict(state='undated') and not result.date_checks_must_be_recomputed
    assert len(value['items'])==8 and len(value['legs'])==6 and len(result.unknown_transfers)==6
    assert case==before
    assert all(leg['state']=='unconfirmed' and leg['source'] is None for leg in value['legs'])
    assert '按你说的' in result.summary and '默认' in result.summary


def test_bad_reason_states_are_removed_for_items_and_lodging_before_candidate_validation():
    case = deepcopy(CASES['unconfirmed'])
    case['content']['items'][0]['reason_refs']=['interests','city','arrival']
    case['content']['lodging']['recommendations'][0]['reason_refs']=['pace','duration_days']
    result = assemble(case['content'],**arguments(case))
    value = json.loads(result.content)
    assert next(i for i in value['items'] if i['id']=='item-1')['reason_refs']==['interests']
    assert value['lodging']['recommendations'][0]['reason_refs']==['pace']
    assert ('item-1',('city','arrival')) in result.removed_reasons
    args = arguments(case)
    args['facts']=tuple(replace(f,state='known') if f.key=='city' else f for f in args['facts'])
    with pytest.raises(SourceRejected):
        assemble(case['content'],**args)


@pytest.mark.parametrize('locale',['zh','en'])
def test_invalid_factor_also_removes_the_associated_reason_prose(locale):
    case=deepcopy(CASES['unconfirmed'])
    item=case['content']['items'][0]
    item['reason_refs']=['interests','city']  # city is a code default.
    item['note']='按你说的城市来安排。' if locale=='zh' else 'Chosen because you said this city.'
    hotel=case['content']['lodging']['recommendations'][0]
    hotel['reason_refs']=['pace','arrival']  # arrival remains unknown.
    hotel['note']='根据你的到达时间选择。' if locale=='zh' else 'Chosen for your stated arrival time.'
    original=deepcopy(case)
    result=assemble(case['content'],**arguments(case,locale=locale))
    value=json.loads(result.content)
    assert next(i for i in value['items'] if i['id']==item['id'])['note'] is None
    assert value['lodging']['recommendations'][0]['note'] is None
    assert next(i for i in value['items'] if i['id']==item['id'])['reason_refs']==['interests']
    assert value['lodging']['recommendations'][0]['reason_refs']==['pace']
    assert case==original


@pytest.mark.parametrize('name',['protected_fixed','retained_verified'])
def test_original_protected_or_retained_item_is_complete_and_byte_exact(name):
    case = deepcopy(CASES[name])
    protected = next(r['payload']['item'] for r in case['source']['records'] if r['kind'] in ('fixed_item','retained_item'))
    result = assemble(case['content'],**arguments(case))
    assert result.status=='CONDITIONAL_SCHEDULE'
    value = json.loads(result.content)
    original = next(i for i in case['content']['items'] if i['id']==protected['id'])
    assert next(i for i in value['items'] if i['id']==protected['id'])==original
    missing = deepcopy(case['content'])
    missing['items']=[i for i in missing['items'] if i['id']!=protected['id']]
    reset_legs(missing)
    with pytest.raises(SourceRejected):
        assemble(missing,**arguments(dict(case,content=missing)))


def test_unknown_arrival_first_day_recipe_and_last_day_proximity_are_enforced():
    case = light_case()
    args = arguments(case,edges=activity_windows(2))
    # The skeleton's explicit dinner interval is kept as a source constraint.
    args['activities']=tuple(replace(a,windows=(Window(18*3600,21*3600),)) if a.item_id=='item-4' else a for a in args['activities'])
    result = assemble(case['content'],**args)
    assert result.status=='CONDITIONAL_SCHEDULE'
    value = json.loads(result.content)
    assert all(i['schedule']['start']['time']['value']>='12:00' for i in value['items'] if i['schedule']['start']['day_index']==1)
    assert next(i for i in value['items'] if i['id']=='item-5')['schedule']['end']['time']['value']<='12:00'
    # JT 2026-11-26: known-far (False) now saves with item-5 disclosed; unknown stays UNKNOWN.
    for nearby,expected in [(None,'UNKNOWN'),(False,'CONDITIONAL_SCHEDULE')]:
        modified=tuple(replace(a,nearby=nearby) if a.item_id=='item-5' else a for a in args['activities'])
        result=assemble(case['content'],**dict(args,activities=modified))
        assert result.status==expected
        assert result.edge_far==(((2,'item-5'),)if nearby is False else())


def test_unknown_lodging_saves_edge_days_with_disclosed_unconfirmed_proximity():
    # JT 2026-11-25 (via coordination, option "照样保存并提示"): when the host has no
    # observed lodging point, unknown first/last-day proximity no longer blocks the
    # save; it is returned for disclosure. Known-false proximity and every other
    # check keep their original refusal, and the default remains UNKNOWN.
    case = light_case()
    args = arguments(case,edges=activity_windows(2))
    args['activities']=tuple(replace(a,windows=(Window(18*3600,21*3600),)) if a.item_id=='item-4' else a for a in args['activities'])
    unknown=tuple(replace(a,nearby=None) if a.item_id in ('item-1','item-5') else a for a in args['activities'])
    assert assemble(case['content'],**dict(args,activities=unknown)).status=='UNKNOWN'
    result=assemble(case['content'],**dict(args,activities=unknown),lodging_unconfirmed=True)
    assert result.status=='CONDITIONAL_SCHEDULE'and result.reason!='EDGE_DAY_PROXIMITY_UNCONFIRMED'
    assert result.edge_proximity_unconfirmed==('item-1','item-5')
    validate_candidate(json.loads(result.content),args['source'])
    assert assemble(case['content'],**args,lodging_unconfirmed=True).edge_proximity_unconfirmed==()
    false=tuple(replace(a,nearby=False) if a.item_id=='item-5' else a for a in unknown)
    # JT 2026-11-26 extends #1545: known-far proximity also saves and is disclosed separately.
    saved=assemble(case['content'],**dict(args,activities=false),lodging_unconfirmed=True)
    assert saved.status=='CONDITIONAL_SCHEDULE'and saved.edge_far==((2,'item-5'),)
    assert saved.edge_proximity_unconfirmed==('item-1',)
    ids=frozenset({'item-1'})
    combined=assemble_unconfirmed(case['content'],**dict(args,activities=unknown),unconfirmed_items=ids,lodging_unconfirmed=True)
    assert combined.status=='UNCONFIRMED_SKELETON'and combined.edge_proximity_unconfirmed==('item-5',)
    for flag in (None,1,'yes'):
        with pytest.raises(ValueError):assemble(case['content'],**args,lodging_unconfirmed=flag)



def test_known_far_edge_day_saves_with_disclosure_and_nothing_else_relaxes():
    # JT 2026-11-26 (coordination thread, option "照样保存并提示（推荐）"): with a located hotel,
    # a first/last-day stop outside walking range no longer refuses the plan; it is returned
    # in edge_far (day, item) for disclosure. Only EDGE_DAY_NEARBY_REQUIRED is relaxed.
    case = light_case()
    args = arguments(case,edges=activity_windows(2))
    args['activities']=tuple(replace(a,windows=(Window(18*3600,21*3600),)) if a.item_id=='item-4' else a for a in args['activities'])
    far=tuple(replace(a,nearby=False) if a.item_id in ('item-1','item-5') else a for a in args['activities'])
    result=assemble(case['content'],**dict(args,activities=far))
    assert result.status=='CONDITIONAL_SCHEDULE'and result.reason!='EDGE_DAY_NEARBY_REQUIRED'
    assert result.edge_far==((1,'item-1'),(2,'item-5'))
    assert result.edge_proximity_unconfirmed==()
    validate_candidate(json.loads(result.content),args['source'])
    assert assemble(case['content'],**args).edge_far==()
    # Unknown proximity without the host's lodging statement still refuses as UNKNOWN.
    unknown=tuple(replace(a,nearby=None) if a.item_id=='item-1' else a for a in far)
    assert assemble(case['content'],**dict(args,activities=unknown)).reason=='EDGE_DAY_PROXIMITY_UNCONFIRMED'
    # The light first-day recipe and every other check keep refusing.
    heavy=deepcopy(CASES['unconfirmed'])
    assert assemble(heavy['content'],**arguments(heavy,edges=activity_windows(2))).reason=='FIRST_DAY_LIGHT_RECIPE_REQUIRED'


def test_first_day_full_override_is_disclosed_and_light_recipe_is_not_silently_imposed():
    case = deepcopy(CASES['unconfirmed'])
    assert assemble(case['content'],**arguments(case,edges=activity_windows(2))).reason=='FIRST_DAY_LIGHT_RECIPE_REQUIRED'
    result = assemble(case['content'],**arguments(case,edges=activity_windows(2,first_day_full=True,
                                                       departure_clock=23*3600,departure_mode='flight')))
    assert result.status=='CONDITIONAL_SCHEDULE' and '排满第一天' in result.summary


@pytest.mark.parametrize('period,expected',[(None,'UNKNOWN'),('lunch','CONFLICT')])
def test_first_unknown_day_requires_an_explicit_dinner_not_an_inferred_restaurant_name(period,expected):
    case=light_case()
    args=arguments(case,edges=activity_windows(2))
    args['activities']=tuple(replace(a,meal_period=period) if a.item_id=='item-4' else a for a in args['activities'])
    assert assemble(case['content'],**args).status==expected


def test_observed_routes_forbid_reordering_but_final_phase_preserves_all_pairs():
    case=deepcopy(CASES['matched'])
    with pytest.raises(SourceRejected):
        assemble(case['content'],**arguments(case))
    result=assemble(case['content'],**arguments(case,phase='schedule'))
    assert result.status=='CONDITIONAL_SCHEDULE'
    value=json.loads(result.content)
    assert value['legs']==case['content']['legs']
    assert [i['id'] for i in value['items']]==[i['id'] for i in case['content']['items']]
    validate_candidate(value,source_for(case))


def test_actual_route_seconds_round_up_and_clock_outputs_are_exact_minutes():
    case=deepcopy(CASES['matched'])
    leg=next(leg for leg in case['content']['legs'] if leg['state']=='estimated')
    r=next(r for r in case['source']['records'] if r['kind']=='route' and r['sha256']==leg['source']['sha256'])
    r['payload']['duration_seconds']=leg['duration_seconds']=61.1
    r['sha256']=sha256(packed(r['payload'])).hexdigest()
    leg['source']['sha256']=r['sha256']
    case['host_expected']['eligible_records']=deepcopy(case['source']['records'])
    result=assemble(case['content'],**arguments(case,phase='schedule'))
    assert result.status=='CONDITIONAL_SCHEDULE'
    value=json.loads(result.content)
    a,b=[next(i for i in value['items'] if i['id']==leg[key]) for key in ('from_item_id','to_item_id')]
    clock=lambda s:int(s[:2])*3600+int(s[3:])*60
    assert clock(b['schedule']['start']['time']['value'])-clock(a['schedule']['end']['time']['value'])>=62


def test_dated_checks_are_marked_for_recomputation_when_times_change():
    case=deepcopy(CASES['dated'])
    result=assemble(case['content'],**arguments(case,phase='schedule'))
    assert result.status=='CONDITIONAL_SCHEDULE' and result.date_checks_must_be_recomputed
    assert json.loads(result.content)['calendar']==case['content']['calendar']


def test_known_opening_conflict_is_retained_instead_of_becoming_a_schedule_pass():
    case=deepcopy(CASES['dated'])
    check=next(c for c in case['content']['date_checks'] if c['kind']=='day_opening')
    check.update(state='conflict',reason='synthetic closed-day result',evidence_refs=['original-opening-check'])
    r=next(r for r in case['source']['records'] if r['kind']=='day_opening')
    r['payload']=deepcopy(check)
    r['sha256']=sha256(packed(check)).hexdigest()
    case['host_expected']['eligible_records']=deepcopy(case['source']['records'])
    result=assemble(case['content'],**arguments(case,phase='schedule'))
    assert result.status=='CONFLICT' and result.reason=='KNOWN_OPENING_CONFLICT' and result.content is None


def test_unknown_clock_does_not_get_invented_and_stopped_search_does_not_return_content():
    case=deepcopy(CASES['unconfirmed'])
    case['content']['items'][0]['schedule']['start']['time']=dict(state='unknown')
    assert assemble(case['content'],**arguments(case)).reason=='EXPLICIT_CLOCK_OR_ZONE_REQUIRED'
    case=deepcopy(CASES['unconfirmed'])
    stop=Event();stop.set()
    result=assemble(case['content'],**arguments(case,stop=stop))
    assert result.status=='UNKNOWN' and result.content is None


def test_exact_activity_set_and_conflicting_edge_windows_are_not_silently_repaired():
    case=deepcopy(CASES['unconfirmed'])
    args=arguments(case)
    with pytest.raises(ValueError):
        assemble(case['content'],**dict(args,activities=args['activities'][:-1]))
    conflict=replace(args['edges'],status='CONFLICT')
    assert assemble(case['content'],**dict(args,edges=conflict)).status=='CONFLICT'
    unknown_mode=activity_windows(2,arrival_clock=0,departure_clock=15*3600)
    result=assemble(case['content'],**dict(args,edges=unknown_mode))
    assert result.status=='UNKNOWN' and result.reason=='EDGE_CONSTRAINTS_UNCONFIRMED' and result.content is None


def test_retained_light_days_are_counted_without_adding_duplicate_new_stops():
    case = light_case()
    args = arguments(case, edges=activity_windows(2))
    args['activities'] = tuple(replace(a, windows=(Window(18*3600, 21*3600),))
        if a.item_id == 'item-4' else a for a in args['activities'])
    first = assemble(case['content'], **args)
    assert first.status == 'CONDITIONAL_SCHEDULE'
    case['content'] = json.loads(first.content)
    for item in case['content']['items']:
        payload = dict(item={k: v for k, v in item.items() if k not in ITEM_EXTRA})
        case['source']['records'].append(dict(provider='trip', kind='retained_item',
            reference='previous-trip:1:'+item['id'], sha256=sha256(packed(payload)).hexdigest(), payload=payload))
    case['host_expected']['eligible_records'] = deepcopy(case['source']['records'])
    retained = assemble(case['content'], **dict(args, source=source_for(case)))
    assert retained.status == 'CONDITIONAL_SCHEDULE'
    assert json.loads(retained.content)['items'] == case['content']['items']
