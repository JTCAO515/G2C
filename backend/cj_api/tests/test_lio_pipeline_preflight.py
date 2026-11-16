"""Pure complete-graph sizing, never a provider or source-authority fixture."""
from copy import deepcopy
from pathlib import Path
import json
import unittest

from cj_api.lio_plan_understanding import PlanFieldProjection
from cj_api.lio_pipeline_preflight import preflight_document,fixed_day_map
from cj_api.lio_pipeline_document import representation_size
from cj_api.lio_pipeline_skeleton import recipes,parse_skeleton,CapacityExceeded
from cj_feasibility.rich_edges import activity_windows
from cj_needs.domain import InvalidInput
from cj_trip.domain import packed
from cj_trip.structured_v4 import validate_document
from test_lio_pipeline_skeleton import proposal

ROOT=Path(__file__).resolve().parents[3]
RETAINED=json.loads((ROOT/'contracts/trip/structured-examples.4.json').read_bytes())['cases']['protected_fixed']['content']


def projection(fields=None,start=None):
    return PlanFieldProjection({}if fields is None else fields,{},
        dict(state='missing')if start is None else dict(state='known',value=start),{})


def fixed():
    def event():return dict(date=dict(state='missing'),time=dict(state='unknown'),
        timezone=dict(state='missing'),place=dict(state='missing'))
    return dict(item_id='fixed-data-fixture',kind='appointment',description='第二天固定集合',
        applies_to=['self'],locked=dict(state='known',value=True),booking_status=dict(state='missing'),
        start=event(),end=event())


class CompleteGraphPreflight(unittest.TestCase):
    def build(self,days=3,fields=None,*,start=None,retained=None):
        edges=activity_windows(days)
        expected=recipes(days,'moderate',light_first=edges.first_unknown_recipe,light_last=edges.last_unknown_morning)
        skeleton=parse_skeleton(packed(proposal(expected)),expected,id_prefix='full-preflight')
        return preflight_document(skeleton,projection(fields,start),edges,id_prefix='full-preflight',
            locale='en',retained=retained)

    def test_full_graph_counts_every_hotel_anchor_and_never_invents_a_city_zone_or_calendar(self):
        value=self.build();validate_document(value)
        self.assertEqual(representation_size(value)[:2],(14,11))
        self.assertEqual(sum(item['kind']=='hotel'for item in value['items']),6)
        self.assertEqual(value['calendar'],dict(state='undated'))
        self.assertTrue(all('date'not in day for day in value['days']))
        self.assertTrue(all(item['schedule']['start']['timezone']==dict(state='unknown')for item in value['items']))
        self.assertTrue(all(item['place']['state']=='unconfirmed'for item in value['items']))

    def test_both_explicit_transfer_endpoints_are_counted_without_pickup_time_or_booking_defaults(self):
        fields={edge:dict(place=dict(state='known',value=name))for edge,name in
            (('arrival','北京首都机场'),('departure','北京南站'))}
        before=deepcopy(fields);value=self.build(fields=fields)
        self.assertEqual(representation_size(value)[:2],(16,13))
        transfers=[item for item in value['items']if item['kind']=='transport']
        self.assertEqual([item['place']['name_zh']for item in transfers],['北京首都机场','北京南站'])
        self.assertTrue(all(item['schedule']['start']['time']==dict(state='unknown')for item in transfers))
        self.assertTrue(all(item['fixed']==dict(state='known',value=False)for item in transfers))
        self.assertEqual(fields,before)
        for state in ('missing','unknown','uncertain'):
            fields={'arrival':dict(place=dict(state=state,**({'note':'待定'}if state=='uncertain'else{})))}
            self.assertEqual(representation_size(self.build(fields=fields))[:2],(14,11))

    def test_complete_fixed_row_is_decorated_and_keeps_its_original_unknowns(self):
        item=fixed();before=deepcopy(item);value=self.build(fields={'fixed_items':[item]})
        self.assertEqual(representation_size(value)[:2],(15,12))
        actual=next(row for row in value['items']if row['id']==item['item_id'])
        self.assertEqual(actual['schedule']['start']['day_index'],2)
        self.assertEqual(actual['schedule']['start']['timezone'],dict(state='missing'))
        self.assertEqual(actual['schedule']['start']['time'],dict(state='unknown'))
        self.assertEqual(actual['kind'],'free_time')
        self.assertIn('place',actual);self.assertIn('reason_refs',actual)
        self.assertEqual(item,before)

    def test_retained_rich_metadata_and_multibyte_bytes_are_measured_without_stripping(self):
        retained=deepcopy(RETAINED);retained['items'][0]['note']='汉'*500
        before=packed(retained);validate_document(retained)
        value=self.build(days=2,retained=retained)
        by_id={item['id']:item for item in value['items']}
        for original in retained['items']:self.assertEqual(by_id[original['id']],original)
        self.assertEqual(len(value['items']),len(retained['items'])+7)
        self.assertEqual(value['sources'],retained['sources'])
        self.assertEqual(value['title'],retained['title'])
        self.assertGreater(len(packed(value)),len(packed(value).decode()))
        self.assertEqual(representation_size(value)[2],len(packed(value)))
        self.assertEqual(packed(retained),before)

    def test_skeleton_that_fits_alone_is_refused_when_the_complete_hotel_graph_exceeds_60(self):
        with self.assertRaises(CapacityExceeded):self.build(days=10)
        retained=deepcopy(RETAINED);before=packed(retained)
        with self.assertRaises(CapacityExceeded):self.build(days=9,retained=retained)
        self.assertEqual(packed(retained),before)

    def test_fixed_day_mapping_has_no_day_one_date_or_out_of_window_fallback(self):
        item=fixed();self.assertEqual(fixed_day_map({'fixed_items':[item]},3,None),{item['item_id']:(2,2)})
        item['description']='固定集合'
        with self.assertRaises(InvalidInput):fixed_day_map({'fixed_items':[item]},3,None)
        for edge in ('start','end'):item[edge]['date']=dict(state='known',value='2026-12-02')
        item['description']='2026-12-02固定集合'
        self.assertEqual(fixed_day_map({'fixed_items':[item]},3,'2026-12-01'),{item['item_id']:(2,2)})
        with self.assertRaises(InvalidInput):fixed_day_map({'fixed_items':[item]},3,'2026-12-03')


if __name__=='__main__':unittest.main()
