"""Query layout only; a DTO/candidate list does not grant a provider source."""
from types import SimpleNamespace
import unittest

from cj_api.local_lio_pipeline import retrieve_skeleton
from cj_api.local_lio_pipeline_search import sight_and_hotel_calls,meal_calls
from cj_api.lio_pipeline_skeleton import recipes,parse_skeleton
from cj_place.gaode_v2 import TextSearch,Nearby
from cj_place.models import Coordinate
from cj_trip.domain import packed
from test_lio_pipeline_skeleton import proposal


class PipelineSearch(unittest.TestCase):
    def skeleton(self,days):
        expected=recipes(days,'moderate',light_first=True,light_last=True)
        return parse_skeleton(packed(proposal(expected)),expected,id_prefix='source-code')

    def test_all_days_stops_and_hotels_have_single_bounded_queries(self):
        for days in (3,4,5):
            with self.subTest(days=days):
                skeleton=self.skeleton(days)
                origin=SimpleNamespace(binding=SimpleNamespace(run_id='original-run'))
                provider=object()
                first=sight_and_hotel_calls(skeleton.stops,skeleton.hotels,city='北京',origin=origin,sources=provider)
                meals=meal_calls(skeleton.stops,city='北京',centers={},origin=origin,sources=provider)
                calls=first+meals
                targets=[call.argument.targets[0]for call in calls]
                self.assertEqual(set(targets),{s.item_id for s in skeleton.stops}|
                    {'lodging-candidate-0','lodging-candidate-1'})
                self.assertEqual(len(targets),len(skeleton.stops)+2)
                self.assertEqual(len(set(targets)),len(targets))
                self.assertTrue(all(type(call.argument.query)is TextSearch for call in calls))
                self.assertTrue(all(call.argument.query.page_size==3 for call in calls))
                self.assertTrue(all(call.argument.origin is origin and call.argument.sources is provider for call in calls))

    def test_nearby_uses_lossless_provider_coordinate_and_no_hidden_second_query(self):
        skeleton=self.skeleton(3)
        meals=[s for s in skeleton.stops if s.kind=='meal']
        point=Coordinate('116.400000,39.900000')
        origin=SimpleNamespace(binding=SimpleNamespace(run_id='original-run'))
        calls=meal_calls(skeleton.stops,city='北京',centers={meals[0].item_id:point},origin=origin,sources=object())
        query=calls[0].argument.query
        self.assertIs(type(query),Nearby)
        self.assertEqual(query.center.raw,point.raw)
        self.assertEqual(query.radius_m,1500)
        self.assertEqual(len(calls),len(meals))
        other=meal_calls(skeleton.stops,city='北京',centers={meals[0].item_id:Coordinate('116.4000001,39.9000001')},
                         origin=origin,sources=object())
        self.assertIs(type(other[0].argument.query),TextSearch)
        self.assertEqual(len(other),len(meals))

    def test_request_refs_are_stable_bound_and_do_not_batch_keywords(self):
        skeleton=self.skeleton(3);provider=object()
        def calls(run):return sight_and_hotel_calls(skeleton.stops,skeleton.hotels,city='北京',
            origin=SimpleNamespace(binding=SimpleNamespace(run_id=run)),sources=provider)
        first=calls('original-run');same=calls('original-run');other=calls('other-run')
        self.assertEqual([c.argument.request_ref for c in first],[c.argument.request_ref for c in same])
        self.assertTrue(all(a.argument.request_ref!=b.argument.request_ref for a,b in zip(first,other,strict=True)))
        self.assertEqual(len({c.argument.request_ref for c in first}),len(first))
        self.assertTrue(all('|'not in c.argument.query.keyword for c in first))

    def test_named_endpoints_preserve_the_budget_for_transit_and_taxi(self):
        skeleton=self.skeleton(3)
        required=len(skeleton.stops)+len(skeleton.hotels)
        leg_count=15
        binding=SimpleNamespace(run_id='original-run',message_id='original-message')
        worker=SimpleNamespace(messages=SimpleNamespace(query=lambda _:None))
        source=SimpleNamespace(providers=object(),profiles=SimpleNamespace(database=object()),binding=binding,worker=worker,
            seal=lambda:None,places=lambda plan,_,**kwargs:({stop.item_id:None for stop in plan.stops},()))
        endpoint=('fixed-meetup','北京饭店')

        for spare,requested in ((0,False),(1,True)):
            with self.subTest(spare=spare):
                seen=[]
                calls=SimpleNamespace(gaode_slots_left=required+2*leg_count+spare,
                    parallel=lambda batch:seen.extend(call.argument.targets[0]for call in batch))
                prepared=SimpleNamespace(skeleton=skeleton,sources=source,city=SimpleNamespace(adcode='110000'),
                    calls=calls,preflight_size=(18,leg_count,10000),endpoint_names=(endpoint,))
                retrieve_skeleton(prepared)
                self.assertEqual(endpoint[0] in seen,requested)
                self.assertEqual(len(seen),required+spare)


if __name__=='__main__':unittest.main()
