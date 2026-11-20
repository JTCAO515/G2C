"""Pure lookup/route data; not a provider/source permission or save test."""
from copy import deepcopy
from types import SimpleNamespace
import unittest

from cj_api.local_lio_pipeline_places import matched_place,route_calls,apply_routes,taxi_fallback_calls,lookup_selected_places,PlaceSelectionBlocked


def reply(name='故宫博物院',pid='B001',point='116.4,39.9'):
    return dict(status='ok',items=[dict(place=dict(amap_id=pid,name_zh=name,
        coordinate=dict(raw=point,longitude=point.split(',')[0],latitude=point.split(',')[1],crs='GCJ-02'),
        coordinate_role='poi_center',address=None),source=dict(provider='amap',kind='place',reference='actual-query:'+pid,
        sha256='0'*64))])


def item(key,day,place):return dict(id=key,schedule=dict(start=dict(day_index=day)),place=place)


class PipelinePlaces(unittest.TestCase):
    def test_exact_unique_observation_keeps_raw_fields_and_uses_pinyin_without_name_source(self):
        value=reply();place=matched_place('故宫博物院',value)
        self.assertEqual(place['amap_id'],'B001')
        self.assertEqual(place['coordinate'],value['items'][0]['place']['coordinate'])
        self.assertEqual(place['source'],value['items'][0]['source'])
        self.assertEqual(place['name_en'],'gu gong bo wu yuan')
        self.assertIsNone(place['name_en_source'])
        place['coordinate']['raw']='changed'
        self.assertEqual(value['items'][0]['place']['coordinate']['raw'],'116.4,39.9')

    def test_missing_unavailable_ambiguous_or_similar_name_never_selects_first_result(self):
        for value in (None,dict(status='unavailable',items=[]),reply('故宫停车场'),
                      dict(status='ok',items=reply()['items']+reply(pid='B002')['items'])):
            self.assertIsNone(matched_place('故宫博物院',value))
        value=reply();value['items'][0]['place']['address']='x'*501
        self.assertIsNone(matched_place('故宫博物院',value))

    def test_initial_route_uses_actual_roles_raw_points_and_counts_unique_exact_query_once(self):
        a=matched_place('故宫博物院',reply())
        b=matched_place('天安门',reply('天安门','B002','116.42,39.9'))
        document=dict(days=[dict(day_index=day)for day in (1,2)],items=[
            item('a1',1,a),item('b1',1,b),item('a2',2,deepcopy(a)),item('b2',2,deepcopy(b))])
        origin=SimpleNamespace(binding=SimpleNamespace(run_id='original-run'));source=object()
        calls,refs=route_calls(document,city='北京',origin=origin,sources=source)
        self.assertEqual(len(calls),1)
        self.assertEqual(refs[(1,'a1','b1')],refs[(2,'a2','b2')])
        argument=calls[0].argument
        self.assertEqual(argument.query.mode,'transit')
        self.assertEqual(argument.query.origin.coordinate.raw,'116.4,39.9')
        self.assertEqual(argument.query.destination.coordinate.raw,'116.42,39.9')
        self.assertIs(argument.origin,origin);self.assertIs(argument.sources,source)
        b['coordinate_role']='entrance'
        document['items'][1]['place']=b
        calls,_=route_calls(document,city='北京',origin=origin,sources=source)
        self.assertEqual(len(calls),2) # role differs: this is not an exact eligible cache hit

    def test_no_cross_day_route_unconfirmed_endpoint_or_rounded_point_is_invented(self):
        a=matched_place('故宫博物院',reply(point='116.400000,39.9'))
        b=matched_place('天安门',reply('天安门','B002','116.4001,39.9'))
        document=dict(days=[dict(day_index=day)for day in (1,2)],
            items=[item('a',1,a),item('b',1,b),item('unknown',2,dict(state='unconfirmed'))])
        calls,refs=route_calls(document,city='北京',origin=SimpleNamespace(binding=SimpleNamespace(run_id='original-run')),sources=object())
        self.assertEqual(set(refs),{(1,'a','b')})
        self.assertEqual(calls[0].argument.query.mode,'walking')
        self.assertEqual(calls[0].argument.query.origin.coordinate.raw,'116.400000,39.9')
        document['items'][0]['place']=matched_place('故宫博物院',reply(point='116.400000000001,39.9'))
        calls,refs=route_calls(document,city='北京',origin=SimpleNamespace(binding=SimpleNamespace(run_id='original-run')),sources=object())
        self.assertEqual(calls,());self.assertIsNone(refs[(1,'a','b')])
        self.assertEqual(document['items'][0]['place']['coordinate']['raw'],'116.400000000001,39.9')
        document['items'][1]['place']=dict(state='unconfirmed')
        calls,refs=route_calls(document,city='北京',origin=SimpleNamespace(binding=SimpleNamespace(run_id='original-run')),sources=object())
        self.assertEqual(calls,());self.assertIsNone(refs[(1,'a','b')])

    def test_taxi_alternative_uses_same_original_endpoints_and_retains_both_attempts(self):
        from cj_api.local_lio_pipeline_calls import PipelineCalls,PipelineCapacity
        a=matched_place('故宫博物院',reply())
        b=matched_place('天安门',reply('天安门','B002','116.42,39.9'))
        document=dict(days=[dict(day_index=d)for d in (1,2)],items=[
            item('a1',1,a),item('b1',1,b),item('a2',2,a),item('b2',2,b)])
        origin=SimpleNamespace(binding=SimpleNamespace(run_id='original-run'));sources=object()
        initial,refs=route_calls(document,city='北京',origin=origin,sources=sources)
        before=deepcopy(refs);old=initial[0].argument
        alternative,updated=taxi_fallback_calls(initial,refs,{old.request_ref:dict(status='unavailable',items=[])})
        self.assertEqual(refs,before);self.assertEqual(len(alternative),1)
        new=alternative[0].argument
        self.assertEqual(new.query.mode,'taxi');self.assertEqual(old.query.mode,'transit')
        self.assertEqual((new.query.origin,new.query.destination),(old.query.origin,old.query.destination))
        self.assertEqual(new.target,old.target);self.assertIs(new.origin,origin);self.assertIs(new.sources,sources)
        self.assertNotEqual(new.request_ref,old.request_ref)
        self.assertEqual(set(updated.values()),{new.request_ref})
        sends=[]
        def stream(binding,key,registration,argument,**kwargs):
            sends.append((key,argument.query.mode));yield 'original completed observation'
        budget=PipelineCalls(SimpleNamespace(_registered_stream=stream,lio_memory=None),origin.binding)
        budget.parallel(initial);budget.parallel(alternative)
        self.assertEqual(budget.gaode,2);self.assertEqual([mode for _,mode in sends],['transit','taxi'])
        self.assertEqual(len({key for key,_ in sends}),2)
        budget.gaode=45;before=list(sends)
        with self.assertRaises(PipelineCapacity):budget.parallel(alternative)
        self.assertEqual(sends,before)
        repeated,_=taxi_fallback_calls(alternative,updated,{new.request_ref:dict(status='unavailable',items=[])})
        self.assertEqual(repeated,())

    def test_success_unknown_and_walking_do_not_trigger_a_taxi_request(self):
        a=matched_place('故宫博物院',reply());b=matched_place('天安门',reply('天安门','B002','116.42,39.9'))
        document=dict(days=[dict(day_index=1)],items=[item('a',1,a),item('b',1,b)])
        origin=SimpleNamespace(binding=SimpleNamespace(run_id='original-run'))
        initial,refs=route_calls(document,city='北京',origin=origin,sources=object())
        for status in ('ok','unknown'):
            calls,unchanged=taxi_fallback_calls(initial,refs,{initial[0].argument.request_ref:dict(status=status,items=[])})
            self.assertEqual(calls,());self.assertEqual(unchanged,refs)
        with self.assertRaises(KeyError):taxi_fallback_calls(initial,refs,{})
        document['items'][1]['place']=matched_place('天安门',reply('天安门','B002','116.4001,39.9'))
        walking,refs=route_calls(document,city='北京',origin=origin,sources=object())
        calls,_=taxi_fallback_calls(walking,refs,{walking[0].argument.request_ref:dict(status='unavailable',items=[])})
        self.assertEqual(calls,())

    def test_issued_selection_is_formatted_without_a_second_matching_rule(self):
        from unittest.mock import patch
        from cj_draft.rich_place_selection import RichPlaceSelectionContextSource
        payload=reply()['items'][0]['place'];ref=reply()['items'][0]['source']
        selected=dict(status='matched',selected_record=dict(ref,payload=payload))
        calls=[]
        class Source:
            place_selection=RichPlaceSelectionContextSource.place_selection
            def selection_results(self,binding,capture):
                calls.append((binding,capture))
                return [dict(selected,target='stop',query_keyword='故宫博物院'),
                        dict(status='unavailable',target='lodging-candidate-0',query_keyword='候选酒店')]
        skeleton=SimpleNamespace(stops=(SimpleNamespace(item_id='stop',name_zh='故宫博物院'),),hotels=(('候选酒店','hotel'),))
        binding=object();capture=object()
        with patch('cj_api.local_lio_pipeline_places.matched_place',side_effect=AssertionError('second match forbidden')):
            places,hotels=lookup_selected_places(skeleton,Source(),binding,capture)
        self.assertEqual(places['stop']['source'],ref);self.assertEqual(places['stop']['coordinate'],payload['coordinate'])
        self.assertEqual(hotels,(None,));self.assertEqual(calls,[(binding,capture)])
        places['stop']['coordinate']['raw']='changed';self.assertEqual(payload['coordinate']['raw'],'116.4,39.9')

    def test_ambiguous_unrepresentable_or_refused_selection_never_becomes_fallback(self):
        from cj_needs.revision_lease import LeaseUnavailable
        from cj_draft.rich_place_selection import RichPlaceSelectionContextSource
        skeleton=SimpleNamespace(stops=(SimpleNamespace(item_id='stop',name_zh='故宫博物院'),),hotels=())
        class Source:
            place_selection=RichPlaceSelectionContextSource.place_selection
            def selection_results(self,*args):return [dict(result,target='stop',query_keyword='故宫博物院')]
        for result in (dict(status='ambiguous'),dict(status='matched',selected_record=dict(
                reply()['items'][0]['source'],payload=dict(reply()['items'][0]['place'],address='x'*501)))):
            with self.assertRaises(PlaceSelectionBlocked):lookup_selected_places(skeleton,Source(),object(),object())
        class Closed:
            place_selection=RichPlaceSelectionContextSource.place_selection
            def selection_results(self,*args):raise LeaseUnavailable('actual holder closed')
        with self.assertRaises(LeaseUnavailable):lookup_selected_places(skeleton,Closed(),object(),object())

    def test_optional_fixed_route_endpoint_does_not_block_usable_sight_selection(self):
        source_row = reply()['items'][0]
        class Source:
            def selection_results(self, *args):
                ordinary = dict(source_row['source'], payload=source_row['place'])
                long_address = dict(source_row['source'],
                                    payload=dict(source_row['place'], name_zh='北京饭店', address='x'*501))
                return [dict(target='sight', query_keyword='故宫博物院', status='matched', selected_record=ordinary),
                        dict(target='fixed', query_keyword='北京饭店', status='matched', selected_record=long_address)]
        skeleton = SimpleNamespace(stops=(SimpleNamespace(item_id='sight', name_zh='故宫博物院'),), hotels=())
        places, _ = lookup_selected_places(skeleton, Source(), object(), object(),
                                          endpoint_names=(('fixed', '北京饭店'),))
        self.assertIsNone(places['fixed'])
        self.assertEqual(places['sight']['source'], source_row['source'])

    def test_batch_target_and_original_keyword_binding_are_still_required(self):
        from cj_needs.revision_lease import LeaseUnavailable
        from cj_draft.rich_place_selection import RichPlaceSelectionContextSource
        skeleton=SimpleNamespace(stops=(SimpleNamespace(item_id='stop',name_zh='故宫博物院'),),hotels=())
        class Source:
            place_selection=RichPlaceSelectionContextSource.place_selection
            def selection_results(self,*args):return rows
        for rows in ([],[dict(target='another',query_keyword='故宫博物院',status='unavailable')],
                     [dict(target='stop',query_keyword='另一个地点',status='unavailable')]):
            with self.subTest(rows=rows),self.assertRaises(LeaseUnavailable):
                lookup_selected_places(skeleton,Source(),object(),object())

    def test_only_an_original_observed_route_can_fill_a_leg_and_input_is_preserved(self):
        leg=dict(day_index=1,from_item_id='a',to_item_id='b',state='unconfirmed',mode=None,
            duration_seconds=None,distance_m=None,source=None,time_semantics='provider_estimate_at_query_time',future_guaranteed=False)
        document=dict(legs=[leg]);before=deepcopy(document)
        source=dict(provider='amap',kind='route',reference='actual-attempt:route',sha256='1'*64)
        reply=dict(status='ok',items=[dict(route=dict(mode='transit',duration_seconds=900,distance_m=2000),source=source)])
        value=apply_routes(document,{(1,'a','b'):'original-query'},{'original-query':reply})
        self.assertEqual(document,before)
        result,=value['legs']
        self.assertEqual(result['duration_seconds'],900);self.assertEqual(result['distance_m'],2000)
        self.assertEqual(result['source'],source);self.assertEqual(result['state'],'estimated')
        self.assertFalse(result['future_guaranteed'])
        for refs,replies in (({(1,'a','b'):None},{}),({(1,'a','b'):'original-query'},
                {'original-query':dict(status='unavailable',items=[])})):
            self.assertEqual(apply_routes(document,refs,replies),before)


if __name__=='__main__':unittest.main()
