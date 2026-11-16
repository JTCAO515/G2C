"""Route allocation controls; mocked operation output is not source/PG proof."""
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest

from cj_api.local_lio_pipeline_calls import PipelineCalls
from cj_api.local_lio_pipeline_routes import retrieve_routes
from test_lio_pipeline_places import reply,item,matched_place


def document(*,transit=False):
    points=('116.4,39.9','116.42,39.9')if transit else('116.4,39.9','116.401,39.9','116.402,39.9','116.403,39.9')
    items=[item('p'+str(n),1,matched_place('地点'+str(n),reply('地点'+str(n),'B'+str(n),point)))for n,point in enumerate(points)]
    legs=[dict(day_index=1,from_item_id=a['id'],to_item_id=b['id'],state='unconfirmed',mode=None,
        duration_seconds=None,distance_m=None,source=None,time_semantics='provider_estimate_at_query_time',future_guaranteed=False)
        for a,b in zip(items,items[1:])]
    return dict(days=[dict(day_index=1)],items=items,legs=legs)


class RouteBudget(unittest.TestCase):
    def setup_calls(self,used,*,transit_unavailable=False,unknown=False):
        sends=[];capture=object();binding=SimpleNamespace(run_id='original-run')
        def stream(actual,key,registration,argument,**kwargs):
            sends.append(argument);yield ''
            if unknown:raise OSError('original outcome unknown')
            if transit_unavailable and argument.query.mode=='transit':value=dict(status='unavailable',items=[])
            else:value=dict(status='ok',items=[dict(route=dict(mode=argument.query.mode,duration_seconds=60,distance_m=120),
                source=dict(provider='amap',kind='route',reference=argument.request_ref,sha256='0'*64))])
            yield json.dumps(value)
        calls=PipelineCalls(SimpleNamespace(_registered_stream=stream,lio_memory=None),binding);calls.gaode=used
        providers=SimpleNamespace(capture=lambda b:capture)
        return calls,SimpleNamespace(binding=binding),providers,capture,sends

    def test_remaining_budget_retains_complete_graph_and_unqueried_legs_without_fake_outcomes(self):
        data=document();before=deepcopy(data)
        calls,origin,providers,capture,sends=self.setup_calls(43)
        result,actual=retrieve_routes(data,calls=calls,city='北京',origin=origin,providers=providers)
        self.assertIs(actual,capture);self.assertEqual(calls.gaode,45);self.assertEqual(len(sends),2)
        self.assertEqual(data,before);self.assertEqual(result['items'],before['items']);self.assertEqual(len(result['legs']),3)
        self.assertEqual([leg['state']for leg in result['legs']],['estimated','estimated','unconfirmed'])
        self.assertEqual(result['legs'][-1],before['legs'][-1])
        self.assertEqual({leg['source']['reference']for leg in result['legs']if leg['state']=='estimated'},
            {packet.request_ref for packet in sends})

    def test_zero_remaining_budget_makes_no_new_attempt_or_fact(self):
        data=document();calls,origin,providers,_,sends=self.setup_calls(45)
        result,_=retrieve_routes(data,calls=calls,city='北京',origin=origin,providers=providers)
        self.assertEqual(result,data);self.assertEqual(sends,[]);self.assertEqual(calls.gaode,45)

    def test_taxi_alternative_is_optional_only_after_original_unavailable_and_fits_remaining_budget(self):
        for used,count in ((44,1),(43,2)):
            data=document(transit=True);calls,origin,providers,_,sends=self.setup_calls(used,transit_unavailable=True)
            result,_=retrieve_routes(data,calls=calls,city='北京',origin=origin,providers=providers)
            self.assertEqual(len(sends),count);self.assertEqual(calls.gaode,45)
            self.assertEqual([packet.query.mode for packet in sends],['transit']if count==1 else['transit','taxi'])
            self.assertEqual(result['legs'][0]['state'],'unconfirmed'if count==1 else'estimated')

    def test_unknown_propagates_without_taxi_retry_or_budget_refund(self):
        data=document();calls,origin,providers,_,sends=self.setup_calls(43,unknown=True)
        with self.assertRaisesRegex(OSError,'original outcome unknown'):
            retrieve_routes(data,calls=calls,city='北京',origin=origin,providers=providers)
        self.assertEqual(len(sends),2);self.assertEqual(calls.gaode,45)


if __name__=='__main__':unittest.main()
