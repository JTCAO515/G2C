"""Complete post-retrieval data for C's assembler; no source lease or save."""
from copy import deepcopy
from datetime import date
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from cj_api.lio_pipeline_compilation import compile_retrieved
from cj_api.lio_plan_understanding import parse_plan_understanding,prepare_plan_fields
from cj_api.lio_planning_grounding import PlanningTurn
from cj_api.lio_pipeline_document import declared_endpoint_names,representation_size
from cj_api.lio_pipeline_preflight import preflight_document
from cj_api.lio_pipeline_skeleton import recipes,parse_skeleton,CapacityExceeded
from cj_feasibility.rich_edges import activity_windows
from cj_message.lio_plan_input_schema import PLAN_UNDERSTANDING
from cj_trip.domain import packed
from cj_trip.structured_v4 import validate_document
from test_lio_pipeline_document import checks
from test_lio_pipeline_preflight import projection,fixed
from test_lio_pipeline_skeleton import proposal

ROOT=Path(__file__).resolve().parents[3]
CASES=json.loads((ROOT/'contracts/trip/structured-examples.4.json').read_bytes())['cases']


def prepared(fields=None):
    edges=activity_windows(3)
    expected=recipes(3,'moderate',light_first=True,light_last=True)
    return SimpleNamespace(skeleton=parse_skeleton(packed(proposal(expected)),expected,id_prefix='compile-data'),
        projection=projection(fields),projected=projection(fields),edges=edges,id_prefix='compile-data',
        city=SimpleNamespace(timezone='Asia/Shanghai'))


def build(value,*,retained=None,hotel=None):
    return compile_retrieved(value,{s.item_id:None for s in value.skeleton.stops},
        (hotel,None),checks=checks(3),subjects=('party',),locale='en',retained=retained)


class RetrievedCompilation(unittest.TestCase):
    def test_suggested_order_leaves_narrow_meal_windows_before_flexible_sights(self):
        locked=fixed();locked['description']='第一天固定集合'
        for edge,clock in (('start','09:00'),('end','10:00')):
            locked[edge]['time']={'state':'known','value':clock}
            locked[edge]['timezone']={'state':'known','value':'Asia/Shanghai'}
        value=prepared({'fixed_items':[locked]})
        value.edges=activity_windows(3,first_day_full=True)
        expected=recipes(3,'relaxed',light_first=False,light_last=True)
        value.skeleton=parse_skeleton(packed(proposal(expected)),expected,id_prefix=value.id_prefix)
        result=build(value);validate_document(result.document)
        proposed=[i for i in result.document['items']if i['schedule']['start']['day_index']==1
            and i['id']in result.proposed_subjects and i['kind']in ('sight','meal')]
        self.assertEqual(proposed[0]['kind'],'meal')
        self.assertEqual(next(a for a in result.order_activities if a.item_id==proposed[0]['id']).meal_period,'lunch')
        actual=next(i for i in result.document['items']if i['id']==locked['item_id'])
        self.assertEqual(actual['schedule']['start']['time'],locked['start']['time'])
        self.assertEqual(actual['schedule']['end']['time'],locked['end']['time'])
        self.assertTrue(all(leg['state']=='unconfirmed'and leg['source']is None for leg in result.document['legs']))

    def test_complete_post_lookup_graph_keeps_preflight_ids_and_all_hotel_pairs(self):
        value=prepared();before=preflight_document(value.skeleton,value.projection,value.edges,
            id_prefix=value.id_prefix,locale='en')
        result=build(value);validate_document(result.document)
        self.assertEqual(representation_size(result.document)[:2],representation_size(before)[:2])
        self.assertEqual({i['id']for i in result.document['items']},{i['id']for i in before['items']})
        self.assertEqual(result.document['calendar'],{'state':'undated'})
        self.assertTrue(all('date'not in day for day in result.document['days']))
        self.assertEqual({a.item_id for a in result.order_activities},{i['id']for i in result.document['items']})
        self.assertEqual({a.item_id for a in result.schedule_activities},{i['id']for i in result.document['items']})
        self.assertTrue(all(s==['party']for s in result.proposed_subjects.values()))

    def test_source_fixed_clock_and_lock_stay_exact_in_both_solver_phases(self):
        item=fixed()
        for edge,time in (('start','09:00'),('end','10:00')):
            item[edge]['time']={'state':'known','value':time}
            item[edge]['timezone']={'state':'known','value':'Asia/Shanghai'}
        value=prepared({'fixed_items':[item]});before=deepcopy(value.projection.fields)
        result=build(value)
        actual=next(i for i in result.document['items']if i['id']==item['item_id'])
        self.assertEqual(actual['fixed'],{'state':'known','value':True})
        self.assertEqual(actual['schedule']['start']['day_index'],2)
        self.assertEqual(actual['schedule']['start']['time'],item['start']['time'])
        self.assertEqual(actual['schedule']['end']['time'],item['end']['time'])
        for group in (result.order_activities,result.schedule_activities):
            bound=next(a for a in group if a.item_id==item['item_id'])
            self.assertEqual([(w.start,w.end)for w in bound.windows],[(86400+9*3600,86400+10*3600)])
        self.assertEqual(value.projection.fields,before)

    def test_verified_original_fixed_endpoint_keeps_the_locked_clock_and_enables_routes(self):
        place=deepcopy(next(i['place']for i in CASES['matched']['content']['items']if i['place']['state']=='matched'))
        item=fixed()
        for edge,time in (('start','09:00'),('end','10:00')):
            item[edge]['time']={'state':'known','value':time}
            item[edge]['timezone']={'state':'known','value':'Asia/Shanghai'}
            item[edge]['place']={'state':'known','value':place['name_zh']}
        value=prepared({'fixed_items':[item]})
        lookups={s.item_id:None for s in value.skeleton.stops}
        lookups[item['item_id']]=place
        result=compile_retrieved(value,lookups,(None,None),checks=checks(3),subjects=('party',),locale='en',retained=None)
        actual=next(i for i in result.document['items']if i['id']==item['item_id'])
        self.assertEqual(actual['place'],place)
        self.assertEqual(actual['fixed'],{'state':'known','value':True})
        self.assertEqual(actual['schedule']['start']['time'],item['start']['time'])
        self.assertEqual(actual['schedule']['end']['time'],item['end']['time'])

    def test_endpoint_lookup_uses_only_explicit_names_and_keeps_transfer_time_unknown(self):
        place=deepcopy(next(i['place']for i in CASES['matched']['content']['items']if i['place']['state']=='matched'))
        generic=fixed(); known=fixed(); known['item_id']='named-fixed'; moved=fixed();moved['item_id']='moving-fixed'
        for edge in ('start','end'):
            generic[edge]['place']={'state':'known','value':'酒店'}
            known[edge]['place']={'state':'known','value':place['name_zh']}
        moved['start']['place']={'state':'known','value':'北京首都国际机场'}
        moved['end']['place']={'state':'known','value':'北京站'}
        fields=dict(fixed_items=[generic,known,moved],arrival=dict(place=dict(state='known',value=place['name_zh'])),
                    departure=dict(place=dict(state='known',value='机场')))
        expected=(('named-fixed',place['name_zh']),('compile-data-arrival-transfer',place['name_zh']))
        self.assertEqual(declared_endpoint_names(fields,id_prefix='compile-data',retained=None,city_names=()),expected)
        self.assertEqual(declared_endpoint_names(fields,id_prefix='compile-data',
            retained={'items':[{'id':'named-fixed'}]},city_names=()),expected[1:])
        value=prepared(fields)
        lookups={s.item_id:None for s in value.skeleton.stops}
        lookups['compile-data-arrival-transfer']=place
        result=compile_retrieved(value,lookups,(None,None),checks=checks(3),subjects=('party',),locale='en',retained=None)
        actual={i['id']:i for i in result.document['items']}
        arrival=actual['compile-data-arrival-transfer']
        self.assertEqual(arrival['place'],place)
        self.assertEqual(arrival['schedule']['start']['time'],{'state':'unknown'})
        self.assertIn('booking are unconfirmed',arrival['note'])
        self.assertEqual(actual['compile-data-departure-transfer']['place']['state'],'unconfirmed')

    def test_known_airport_event_clocks_bind_both_route_anchor_windows(self):
        fields = {
            'arrival': {'place': {'state': 'known', 'value': '北京大兴机场'},
                        'time': {'state': 'known', 'value': '06:30'},
                        'date': {'state': 'known', 'value': '2026-11-22'},
                        'timezone': {'state': 'known', 'value': 'Asia/Shanghai'}},
            'departure': {'place': {'state': 'known', 'value': '北京首都机场'},
                          'time': {'state': 'known', 'value': '18:00'},
                          'date': {'state': 'known', 'value': '2026-11-24'},
                          'timezone': {'state': 'known', 'value': 'Asia/Shanghai'}},
        }
        original = deepcopy(fields)
        value = prepared(fields)
        value.projected = value.projection = projection(fields, start='2026-11-22')
        result = compile_retrieved(value, {stop.item_id: None for stop in value.skeleton.stops},
                                   (None, None), checks=checks(3, dated=True), subjects=('party',),
                                   locale='en', retained=None)
        validate_document(result.document)
        transported = {item['id']: item for item in result.document['items'] if item['kind'] == 'transport'}
        for edge, clock, day, point in (('arrival', '06:30', 1, 23400), ('departure', '18:00', 3, 237600)):
            key = 'compile-data-'+edge+'-transfer'
            item = transported[key]
            self.assertEqual(item['schedule']['start'], item['schedule']['end'])
            event = item['schedule']['start']
            self.assertEqual(event['day_index'], day)
            self.assertEqual(event['time'], {'state': 'known', 'value': clock})
            self.assertEqual(event['timezone'], {'state': 'known', 'value': 'Asia/Shanghai'})
            self.assertEqual(event['utc_offset'], {'state': 'unknown'})
            self.assertEqual(item['fixed'], {'state': 'known', 'value': False})
            self.assertIn('booking', item['note'])
            for activities in (result.order_activities, result.schedule_activities):
                window, = next(activity.windows for activity in activities if activity.item_id == key)
                self.assertEqual((window.start, window.end), (point, point))
        self.assertEqual(fields, original)

    def test_transfer_clock_with_a_different_calendar_day_or_zone_stays_unconfirmed(self):
        for extra in ({'date': {'state': 'known', 'value': '2026-11-23'}},
                      {'timezone': {'state': 'known', 'value': 'UTC'}}):
            with self.subTest(extra=extra):
                fields = {'arrival': dict({'place': {'state': 'known', 'value': '北京大兴机场'},
                                           'time': {'state': 'known', 'value': '06:30'}}, **extra)}
                value = prepared(fields)
                value.projection = projection(fields, start='2026-11-22')
                result = compile_retrieved(value, {stop.item_id: None for stop in value.skeleton.stops},
                                           (None, None), checks=checks(3, dated=True), subjects=('party',),
                                           locale='en', retained=None)
                item, = (row for row in result.document['items'] if row['kind'] == 'transport')
                self.assertEqual(item['schedule']['start']['time'], {'state': 'unknown'})
                self.assertEqual(next(a.windows for a in result.order_activities if a.item_id == item['id']), ())

    def test_explicitly_undecided_departure_date_cannot_become_a_last_day_clock(self):
        for text,start,clock,place,mode,uncertain in (
                ('从2026-11-22开始。我的航班18:00起飞。我从北京首都机场出发。离境日期还没定。',
                 '从2026-11-22开始','18:00','北京首都机场','航班','离境日期还没定'),
                ('Start my trip on 2026-11-22. My flight leaves at 6 pm. I leave from Beijing Capital Airport. '
                 'My departure date is undecided.', 'Start my trip on 2026-11-22','6 pm',
                 'Beijing Capital Airport','flight','My departure date is undecided')):
            for date_state in ('unknown','uncertain'):
                with self.subTest(text=text,date_state=date_state):
                    turns=(PlanningTurn(text,date(2026,11,21)),PlanningTurn('Plan now',date(2026,11,21)))
                    packet=dict(version=PLAN_UNDERSTANDING,current_source_index=1,companions=[],fixed_items=[],
                        temporary_conditions=[],observations=[dict(field=field,state=state,value=value,note=uncertain if state=='uncertain' else None,
                            sources=[dict(source_index=0,quote=quote)]) for field,state,value,quote in (
                                ('start_date','known','2026-11-22',start),('departure.time','known','18:00',clock),
                                ('departure.place','known',place,place),('departure.mode','known','flight',mode),
                                ('departure.date',date_state,None,uncertain))])
                    projected=prepare_plan_fields(parse_plan_understanding(packed(packet),turns),turns)
                    original_date={'state':date_state}
                    if date_state=='uncertain':original_date['note']=uncertain
                    self.assertEqual(projected.fields['departure']['date'],original_date)
                    value=prepared()
                    value.projected=value.projection=projected
                    result=compile_retrieved(value,{stop.item_id:None for stop in value.skeleton.stops},
                        (None,None),checks=checks(3,dated=True),subjects=('party',),locale='en',retained=None)
                    item,=(row for row in result.document['items'] if row['kind']=='transport')
                    self.assertEqual(item['schedule']['start']['time'],{'state':'unknown'})
                    for activities in (result.order_activities,result.schedule_activities):
                        self.assertEqual(next(a.windows for a in activities if a.item_id==item['id']),())


    def test_city_names_do_not_become_a_transfer_or_fixed_poi(self):
        item=fixed()
        for edge in ('start','end'):
            item[edge]['place']={'state':'known','value':'北京市'}
        fields=dict(fixed_items=[item],arrival=dict(place=dict(state='known',value='Beijing')),
                    departure=dict(place=dict(state='known',value='北京首都国际机场')))
        self.assertEqual(declared_endpoint_names(fields,id_prefix='compile-data',retained=None,
            city_names=('北京','北京市','beijing')), (('compile-data-departure-transfer','北京首都国际机场'),))

    def test_retained_rich_original_title_fields_and_source_rows_are_not_rewritten(self):
        original=deepcopy(CASES['protected_fixed']['content']);before=deepcopy(original)
        result=build(prepared(),retained=original)
        self.assertEqual(result.document['title'],original['title'])
        self.assertEqual(result.document['sources'],original['sources'])
        by_id={i['id']:i for i in result.document['items']}
        for item in original['items']:self.assertEqual(by_id[item['id']],item)
        self.assertEqual(original,before)

    def test_observed_hotel_source_is_an_explicit_estimate_not_a_user_booking(self):
        hotel=deepcopy(next(i['place']for i in CASES['matched']['content']['items']if i['place']['state']=='matched'))
        before=deepcopy(hotel);result=build(prepared(),hotel=hotel)
        anchors=[i for i in result.document['items']if i['kind']=='hotel']
        self.assertEqual(len(anchors),6)
        for item in anchors:
            self.assertEqual(item['place'],hotel)
            self.assertIn('no stay or booking is confirmed',item['note'])
            self.assertEqual(item['fixed'],{'state':'known','value':False})
        order={a.item_id:a for a in result.order_activities}
        schedule={a.item_id:a for a in result.schedule_activities}
        self.assertTrue(all(order[i['id']].windows!=schedule[i['id']].windows for i in anchors))
        self.assertEqual(hotel,before)

    def test_no_observed_lodging_marks_edge_days_for_disclosure_on_their_anchors(self):
        # JT 2026-11-25 (via coordination, "照样保存并提示"): without an observed
        # lodging point the first/last day are saved with a visible hint instead
        # of refusing. An observed hotel keeps the original proximity evidence.
        hints={'zh':('抵达时间未定，首日活动建议安排在住处附近；补充酒店位置后可再调整。',
                     '离开时间未定，末日活动建议安排在住处附近；补充酒店位置后可再调整。'),
               'en':('Arrival time is not set, so keep day-1 activities near where you stay; you can adjust after adding your hotel.',
                     'Departure time is not set, so keep last-day activities near where you stay; you can adjust after adding your hotel.')}
        hotel=deepcopy(next(i['place']for i in CASES['matched']['content']['items']if i['place']['state']=='matched'))
        for locale,(first,last) in hints.items():
            for observed in (None,hotel):
                with self.subTest(locale=locale,observed=observed is not None):
                    value=prepared()
                    result=compile_retrieved(value,{s.item_id:None for s in value.skeleton.stops},(observed,None),
                        checks=checks(3),subjects=('party',),locale=locale,retained=None)
                    self.assertIs(result.lodging_unconfirmed,observed is None)
                    notes={i['id']:i['note']for i in result.document['items']if i['kind']=='hotel'}
                    self.assertEqual(len(notes),6)
                    for key,note in notes.items():
                        self.assertIn('未确认入住或预订'if locale=='zh'else'no stay or booking is confirmed',note)
                        expected=(first if key=='compile-data-lodging-d1-out'else
                                  last if key=='compile-data-lodging-d3-back'else None)
                        for hint in (first,last):
                            self.assertEqual(hint in note,observed is None and hint==expected,(key,note))

    def test_unknown_coordinates_do_not_become_nearby_and_meal_period_remains_typed(self):
        value=prepared();result=build(value)
        by_id={a.item_id:a for a in result.order_activities}
        for stop in value.skeleton.stops:
            self.assertIsNone(by_id[stop.item_id].nearby)
            self.assertEqual(by_id[stop.item_id].meal_period,stop.period)

    def test_dated_retained_calendar_is_preserved_without_inventing_clear_date_checks(self):
        original=deepcopy(CASES['dated']['content']);value=prepared()
        result=compile_retrieved(value,{s.item_id:None for s in value.skeleton.stops},(None,None),
            checks=checks(3,dated=True),subjects=('self',),locale='zh',retained=original)
        self.assertEqual(result.document['calendar'],original['calendar'])
        self.assertTrue(all(row['state']=='unknown'for row in result.document['date_checks']))
        self.assertEqual(result.document['days'][0]['date'],original['calendar']['start_date'])

    def test_capacity_refusal_never_truncates_or_mutates_original_trip(self):
        original=deepcopy(CASES['unconfirmed']['content'])
        template=original['items'][0]
        original['items']=[dict(deepcopy(template),id='old-item-'+str(i))for i in range(60)]
        before=deepcopy(original)
        with self.assertRaises(CapacityExceeded):build(prepared(),retained=original)
        self.assertEqual(original,before)

    def test_confirmed_city_metadata_is_not_an_explicit_airport_or_station_transfer(self):
        value=prepared()
        value.projection=projection({edge:dict(place=dict(state='known',value='北京市'))
            for edge in ('arrival','departure')})
        result=build(value)
        self.assertFalse(any(item['kind']=='transport'for item in result.document['items']))
        self.assertEqual(representation_size(result.document)[:2],(14,11))


if __name__=='__main__':unittest.main()
