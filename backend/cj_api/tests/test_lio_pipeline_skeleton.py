from copy import deepcopy
import json
import unittest

from cj_api.lio_pipeline_skeleton import recipes,parse_skeleton,CapacityExceeded,SkeletonUnavailable


def proposal(expected):
    def place(key):return dict(name_zh='合成'+key,name_en='Synthetic '+key)
    return dict(version='LIO-plan-skeleton.1',title='Proposed trip',days=[dict(day_index=r.day_index,area='合成街区',
        sights=[place(str(r.day_index)+'s'+str(n))for n in range(r.sights)],
        meals=[dict(period=p,place=place(str(r.day_index)+p))for p in r.meals])for r in expected],
        lodging=dict(area='合成住宿片区',recommendations=[place('hotel1'),place('hotel2')]))


class PipelineSkeleton(unittest.TestCase):
    def test_full_3_4_5_days_follow_code_pace_and_edge_recipes(self):
        for days in (3,4,5):
            for pace,count in (('relaxed',2),('moderate',3),('packed',4)):
                expected=recipes(days,pace,light_first=True,light_last=True)
                result=parse_skeleton(json.dumps(proposal(expected)).encode(),expected,id_prefix='p4')
                self.assertEqual(len(result.stops),3+(days-2)*(count+2))
                self.assertEqual({s.day_index for s in result.stops},set(range(1,days+1)))
                self.assertEqual(len({s.item_id for s in result.stops}),len(result.stops))
                self.assertEqual(len(result.hotels),2)

    def test_reordered_meals_are_code_ordered_without_changing_meaning(self):
        expected=recipes(3,'moderate',light_first=False,light_last=False)
        value=proposal(expected)
        value['days'][1]['meals'].reverse()
        result=parse_skeleton(json.dumps(value).encode(),expected,id_prefix='p4')
        self.assertEqual([s.period for s in result.stops if s.day_index==2 and s.kind=='meal'],['lunch','dinner'])

    def test_partial_days_counts_duplicate_meals_and_duplicate_names_are_rejected(self):
        expected=recipes(3,'moderate',light_first=False,light_last=False)
        original=proposal(expected)
        for mutation in (lambda v:v['days'].pop(),lambda v:v['days'][1].update(day_index=1),
                         lambda v:v['days'][1]['sights'].pop(),
                         lambda v:v['days'][1]['meals'][1].update(period='lunch'),
                         lambda v:v['days'][1]['sights'].__setitem__(1,deepcopy(v['days'][1]['sights'][0]))):
            value=deepcopy(original);mutation(value)
            with self.assertRaises(SkeletonUnavailable):parse_skeleton(json.dumps(value).encode(),expected,id_prefix='p4')

    def test_current_capacity_is_not_a_fake_day_limit_or_silent_truncation(self):
        expected=recipes(16,'moderate',light_first=True,light_last=True)
        value=proposal(expected)
        with self.assertRaises(CapacityExceeded):parse_skeleton(json.dumps(value).encode(),expected,id_prefix='p4')
        expected=recipes(5,'moderate',light_first=True,light_last=True)
        with self.assertRaises(CapacityExceeded):
            parse_skeleton(json.dumps(proposal(expected)).encode(),expected,id_prefix='p4',protected_item_count=50,transfer_item_count=5)

    def test_model_cannot_add_source_authority_or_hidden_query_batches(self):
        expected=recipes(3,'moderate',light_first=True,light_last=True)
        original=proposal(expected)
        for change in (lambda v:v.update(source={'provider':'amap'}),
                       lambda v:v['days'][0]['sights'][0].update(amap_id='invented'),
                       lambda v:v['days'][0]['sights'][0].update(name_zh='a|b')):
            value=deepcopy(original);change(value)
            with self.assertRaises(SkeletonUnavailable):parse_skeleton(json.dumps(value).encode(),expected,id_prefix='p4')
        with self.assertRaises(SkeletonUnavailable):parse_skeleton(json.dumps(original).encode()[:-1],expected,id_prefix='p4')

    def test_combined_one_day_edges_need_an_explicit_feasible_policy(self):
        with self.assertRaises(SkeletonUnavailable):recipes(1,'moderate',light_first=True,light_last=True)


if __name__=='__main__':unittest.main()
