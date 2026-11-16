"""Actual registered route receipt over actual POI2 results; fixture sockets."""
import asyncio
from copy import copy
from hashlib import sha256
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'backend/cj_api/tests'),str(ROOT/'backend/place/tests')]
from cj_api.local_lio_exploration import ExplorationPlanning
from cj_api.local_lio_rich_source import RichProfileSource
from cj_api.local_lio_provider_sources import RegisteredProviderSources,POI2_REGISTRATION,ROUTE_REGISTRATION
from cj_api.local_lio_pipeline_calls import PipelineCalls
from cj_api.local_lio_pipeline_search import sight_and_hotel_calls
from cj_api.local_lio_pipeline_places import matched_place,route_calls
from cj_api.local_lio_pipeline_routes import retrieve_routes
from cj_api.lio_pipeline_skeleton import Stop
from cj_api.lio_plan_understanding import original_plan_turns
from cj_api.lio_poi2_tool import POI2Input,registration as poi_registration
from cj_api.lio_route_tool import registration as route_registration
from cj_memory.runtime import RuntimeDenied
from cj_message.lio_wire import ExplorationOrigin
from cj_message.lio_exploration_schema import RESPONSE
from cj_needs.revision_lease import LeaseUnavailable
from cj_place.gaode_v2 import TextSearch
from cj_place.models import Coordinate,Endpoint
from cj_place import https_transport
from cj_trip.domain import packed
from cj_trip.rich_source import capture as rich_capture
from cj_usage.metered_exit import BudgetUnknown
from test_poi2_transport import Writer
import lio_exploration_flow_pg as native


class ReplyWriter(Writer):
    def __init__(self,reader,body,send_check):
        super().__init__();self.reader,self.body,self.send_check=reader,body,send_check
    def write(self,raw):
        self.send_check();super().write(raw)
        self.reader.feed_data(b'HTTP/1.1 200 OK\r\nContent-Length: '+str(len(self.body)).encode()+b'\r\n\r\n'+self.body)
        self.reader.feed_eof()


def main():
    actual_model=ExplorationPlanning._model
    completed=[];writers=[]
    def model(host,worker,binding,view,profile,system,extra):
        if profile==RESPONSE and extra.get('scene')=='plan_now_preview':
            originals=original_plan_turns(host.database,worker,binding,view)
            assert tuple(t.text for t in originals)==tuple(o.text for o in view.originals)
            assert all(t.question_day is not None for t in originals)
            profiles=RichProfileSource(host.database)
            profiles.record_plan_now(worker,binding,worker.runs.snapshot(binding))
            sources=RegisteredProviderSources(worker,binding)
            origin=ExplorationOrigin(host.database,binding,worker.messages.query(binding.message_id))
            bodies=[];phases=[]
            def send_check():
                worker.memory_run.check();worker.message_context.active_original(binding)
                phases.append('send-held')
            async def dial():
                reader=asyncio.StreamReader();writer=ReplyWriter(reader,bodies.pop(0),send_check)
                writers.append(writer);return reader,writer
            actual_read=https_transport._read_response
            async def receive(*args):
                try:worker.memory_run.check()
                except RuntimeDenied:pass
                else:raise AssertionError('route IO retained Memory frame')
                try:worker.message_context.active_original(binding)
                except LeaseUnavailable:pass
                else:raise AssertionError('route IO retained MESSAGE frame')
                phases.append('receive-unheld');return await actual_read(*args)
            calls=PipelineCalls(worker,binding);places=[]
            with patch.object(https_transport,'_connect',dial),patch.object(https_transport,'_read_response',receive):
                stops=[]
                for index,point in enumerate(('116.4,39.9','116.42,39.9')):
                    name='合成起点'if index==0 else'合成终点'
                    bodies.append(packed(dict(status='1',infocode='10000',count='1',pois=[dict(
                        id='SYNTH_ROUTE_'+str(index),name=name,cityname='北京市',adcode='110101',location=point)])))
                    stops.append(Stop('stop-'+str(index),1,'sight',None,name,'Synthetic point'))
                lookups=sight_and_hotel_calls(tuple(stops),(),city='北京',origin=origin,sources=sources)
                # Both original requests must be admitted before either reply
                # drains. Two legacy48000 reservations would exceed this RUN's
                # unchanged65536 output ceiling; two explicit8192 slots fit.
                for stop,raw in zip(stops,calls.parallel(tuple(lookups)),strict=True):
                    places.append(matched_place(stop.name_zh,json.loads(raw)))
                assert all(place is not None for place in places)
                endpoints=tuple(Endpoint(row['amap_id'],Coordinate(row['coordinate']['raw']),row['coordinate_role'])for row in places)
                document=dict(days=[dict(day_index=1)],items=[dict(id=stop.item_id,
                    schedule=dict(start=dict(day_index=1)),place=place)for stop,place in zip(stops,places,strict=True)])
                document['legs']=[dict(day_index=1,from_item_id=stops[0].item_id,to_item_id=stops[1].item_id,
                    state='unconfirmed',mode=None,duration_seconds=None,distance_m=None,source=None,
                    time_semantics='provider_estimate_at_query_time',future_guaranteed=False)]
                planned,route_refs=route_calls(document,city='北京',origin=origin,sources=sources)
                call,=planned;packet=call.argument;query=packet.query
                assert query.mode=='transit'and query.origin==endpoints[0]and query.destination==endpoints[1]
                assert route_refs[(1,stops[0].item_id,stops[1].item_id)]==packet.request_ref
                bodies.append(packed(dict(status='1',infocode='10000',count='1',route=dict(
                    origin=endpoints[0].coordinate.raw,destination=endpoints[1].coordinate.raw,
                    transits=[dict(duration='900',segments=[dict(bus=dict(buslines=[dict(distance='2000',
                        polyline=endpoints[0].coordinate.raw+';'+endpoints[1].coordinate.raw)]))])]))))
                before=len(writers)
                for wrong in (dict(query=query),POI2Input(TextSearch('博物馆','北京',1),'wrong-kind',origin,sources)):
                    try:worker.tools.registrations[ROUTE_REGISTRATION].prepare_input(wrong)
                    except BudgetUnknown:pass
                    else:raise AssertionError('untyped/wrong tool input reached route dispatch')
                assert len(writers)==before
                observed_document,captured=retrieve_routes(document,calls=calls,city='北京',origin=origin,providers=sources)
            record,=[row for row in captured.records if row['kind']=='route']
            route=record['payload']
            leg,=observed_document['legs']
            assert leg['state']=='estimated'and leg['duration_seconds']==900 and leg['distance_m']==2000
            assert document['legs'][0]['state']=='unconfirmed'
            assert route['duration_seconds']==900 and route['distance_m']==2000 and route['mode']=='transit'
            assert route['from_coordinate']==places[0]['coordinate']and route['to_coordinate']==places[1]['coordinate']
            assert calls.gaode==3 and phases==['send-held','send-held','receive-unheld','receive-unheld',
                                              'send-held','receive-unheld']and not bodies
            assert len(captured.records)==3 and len(captured.outcomes)==3
            assert captured.outcomes[-1]['registration']==ROUTE_REGISTRATION
            assert captured.outcomes[-1]['targets']==[packet.target]
            late=[]
            def verify():
                with worker.message_context.hold_for_effect(binding)as message:
                    plan=profiles.capture_for_plan(worker,binding,message,expected_profile=view.profile)
                    with profiles.hold_for_plan(worker,binding,plan,message),sources.hold(binding,captured,message)as held:
                        value=dict(version='TRIP-rich-source.1',original=plan.original,plan_now=plan.plan_now,
                                   policy=plan.policy,profile_states=plan.profile_states,records=captured.records)
                        rich=rich_capture(packed(value),expected_original=plan.original,expected_plan_now=plan.plan_now,
                            expected_policy=plan.policy,accepted_profile_states=plan.profile_states,eligible_records=captured.records)
                        assert rich.observation(leg['source'],'route')==route
                        assert rich.observation(leg['source'],'route')==route
                        held.check();late.append(held)
                        try:
                            with sources.hold(binding,copy(captured),message):pass
                        except RuntimeDenied:pass
                        else:raise AssertionError('copied provider capture admitted')
            worker._step(binding,verify)
            try:late[0].check()
            except RuntimeDenied:pass
            else:raise AssertionError('expired route source remained active')
            completed.append(binding.run_id)
            print('PASS native4 registered POI2→transit source/Meter/original financial proof '+binding.message_id+' RUN '+binding.run_id+'; Trip0',flush=True)
        return actual_model(host,worker,binding,view,profile,system,extra)
    with patch.object(ExplorationPlanning,'_model',model):native.main()
    assert len(completed)==6 and len(writers)==18 and all(w.closed and len(w.writes)==1 for w in writers)
    print('PASS ZH3/EN3 concurrent bounded POI2 -> registered route observations; 18 fixture attempts, original65536 ceiling unchanged, 0 real supplier/Trip; full pipeline and G6 UNRUN',flush=True)


if __name__=='__main__':main()
