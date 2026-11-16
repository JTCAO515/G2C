"""Complete post-retrieval data for C's assembler; no source lease or save."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from cj_api.lio_pipeline_compilation import compile_retrieved
from cj_api.lio_pipeline_document import representation_size
from cj_api.lio_pipeline_preflight import preflight_document
from cj_api.lio_pipeline_skeleton import recipes,parse_skeleton,CapacityExceeded
from cj_feasibility.rich_edges import activity_windows
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
