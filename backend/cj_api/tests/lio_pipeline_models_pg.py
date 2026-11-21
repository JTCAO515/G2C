"""Native signed models and complete selected saves; supplier HTTP is a fixture."""
from contextlib import ExitStack
from pathlib import Path
from threading import Event
from datetime import date,timedelta
from dataclasses import replace
import asyncio
import json
import sys
from urllib.parse import urlsplit,parse_qs
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'backend/cj_api/tests')]
import httpx
from fastapi.testclient import TestClient
from cj_api.local_lio_exploration import ExplorationPlanning
from cj_api.local_lio_pipeline_calls import PipelineCalls,model_call
from cj_api.local_lio_pipeline_inputs import understand_constraints,planning_edges
from cj_api.local_lio_pipeline_search import sight_and_hotel_calls
from cj_api.local_lio_pipeline_places import PlaceSelectionBlocked
from cj_api.local_lio_provider_sources import POI2_REGISTRATION
from cj_api.local_lio_planning import register,PlanningDetails
from cj_api.local_lio_rich_source import RichProfileSource
from cj_api.local_lio_rich_calendar_source import RichCalendarSource
from cj_api.lio_city import CityReference
from cj_api.lio_pipeline_model import SKELETON_SYSTEM,WORDING_SYSTEM,skeleton_data,parse_wording
from cj_api.lio_pipeline_skeleton import recipes,parse_skeleton,DayRecipe
from cj_api.lio_pipeline_preflight import preflight_document
from cj_api.lio_pipeline_document import representation_size
from cj_message.lio_exploration_schema import UNDERSTANDING,RESPONSE,response_format
from cj_message.lio_plan_input_schema import PLAN_UNDERSTANDING
from cj_message.lio_wire import ExplorationOrigin
from cj_message.lio_pipeline_schema import SKELETON,WORDING
from cj_needs.revision_lease import LeaseUnavailable
from cj_memory.runtime import RuntimeDenied
from cj_place import https_transport
from cj_trip.domain import packed
from cj_trip.postgres import Repository as TripRepository
from cj_draft.rich_calendar_source import RichCalendarContextSource
from cj_message.lio_plan_needs import original_needs
from test_lio_pipeline_skeleton import proposal
from lio_provider_sources_pg import FixtureWriter
import lio_exploration_flow_pg as native


def full_provider_join(prepared,*,early_departure,saved_runs):
    """Both lookup phases, ordering, routes, scheduling, sole save and readback."""
    from cj_api.local_lio_pipeline import retrieve_skeleton,compile_retrieved_plan,order_retrieved_plan,schedule_retrieved_plan,route_ordered_plan
    bundle=prepared.sources;worker,binding=bundle.worker,bundle.binding
    writers=[];phases=[];queries=[];captures=[]
    def send_check():
        worker.memory_run.check()
        assert worker.message_context.active_original(binding).receipt.message_id==binding.message_id
        phases.append('send-held')
    class Writer(FixtureWriter):
        def __init__(self,reader):super().__init__(reader,send_check)
        def write(self,raw):
            target=raw.split(b'\r\n',1)[0].split(b' ')[1].decode('ascii')
            parsed=urlsplit(target);query=parse_qs(parsed.query);queries.append((parsed.path,query))
            self.path=parsed.path;self.query=query
            self.keyword=query.get('keywords',[''])[0]
            self.provider_id='SYNTH_FULL_'+str(len(queries))
            super().write(raw)
        def response_value(self):
            if self.path.startswith('/v3/direction/'):
                a=self.query['origin'][0];b=self.query['destination'][0]
                return dict(status='1',infocode='10000',count='1',route=dict(origin=a,destination=b,
                    paths=[dict(distance='120',duration='60',steps=[dict(polyline=a+';'+b)])]))
            return dict(status='1',infocode='10000',count='1',pois=[dict(
                id=self.provider_id,name=self.keyword,cityname='北京市',adcode='110101',location='116.4,39.9')])
    async def dial():
        reader=asyncio.StreamReader();writer=Writer(reader);writers.append(writer);return reader,writer
    actual_read=https_transport._read_response
    async def receive(*args):
        try:worker.memory_run.check()
        except RuntimeDenied:pass
        else:raise AssertionError('whole lookup retained Memory over response IO')
        try:worker.message_context.active_original(binding)
        except LeaseUnavailable:pass
        else:raise AssertionError('whole lookup retained MESSAGE over response IO')
        phases.append('receive-unheld');return await actual_read(*args)
    seal=bundle.seal
    def captured():
        value=seal();captures.append(value);return value
    with patch.object(https_transport,'_connect',dial),patch.object(https_transport,'_read_response',receive), \
            patch.object(bundle,'seal',side_effect=captured):
        places,hotels,complete=retrieve_skeleton(prepared)
    sights=sum(stop.kind=='sight'for stop in prepared.skeleton.stops)+len(prepared.skeleton.hotels)
    meals=sum(stop.kind=='meal'for stop in prepared.skeleton.stops)
    assert len(writers)==sights+meals and all(w.closed and len(w.writes)==1 for w in writers)
    assert phases==['send-held']*sights+['receive-unheld']*sights+['send-held']*meals+['receive-unheld']*meals
    assert [path for path,_ in queries]==['/v5/place/text']*sights+['/v5/place/around']*meals
    assert all(query['location']==['116.4,39.9']and query['radius']==['1500']for _,query in queries[sights:])
    assert places.keys()=={stop.item_id for stop in prepared.skeleton.stops}
    assert all(place is not None for place in places.values())and all(place is not None for place in hotels)
    assert len(captures)==2 and complete is captures[1]
    rows=[dict(kind=kind,state='unknown',day_indices=list(range(1,complete.basis.day_count+1)),
        item_ids=[],reason='date_evidence_not_collected',evidence_refs=[])for kind in ('weather','day_opening')]
    # Explicit unknown check DATA for the compilation component, not issued
    # checks or authority to publish. Final genuine checks/publisher are UNRUN.
    compiled=compile_retrieved_plan(prepared,places,hotels,complete,checks=rows,subjects=('party',),locale='en')
    assert representation_size(compiled.document)[:2]==prepared.preflight_size[:2]
    assert len(compiled.order_activities)==len(compiled.schedule_activities)==len(compiled.document['items'])
    snapshot,_=complete.records()
    fixed,=snapshot.fields['fixed_items']
    original=next(item for item in compiled.document['items']if item['id']==fixed['item_id'])
    assert original['fixed']==fixed['locked'] and original['schedule']['start']['time']==fixed['start']['time']
    assert compiled.document['calendar']==dict(state='dated',start_date=complete.basis.start_date)
    from cj_api.local_lio_rich_checks import RichUncollectedChecks
    checks_reader=RichUncollectedChecks(bundle.source)
    def held_checks():
        with bundle.source.hold_for_publication(binding):
            issued=checks_reader.capture(binding,complete,compiled.document)
            assert issued.checks==rows and all(row['state']=='unknown'for row in issued.checks)
            with bundle.source.message_context.hold_for_effect(binding)as message, \
                    checks_reader.hold(binding,issued,message)as check:
                check(compiled.document)
                altered=json.loads(packed(compiled.document))
                altered['items'][0]['schedule']['start']['time']=dict(state='known',value='23:59')
                try:check(altered)
                except LeaseUnavailable:pass
                else:raise AssertionError('changed candidate clock retained issued date checks')
        try:check(compiled.document)
        except LeaseUnavailable:pass
        else:raise AssertionError('issued date-check frame remained open')
    worker._step(binding,held_checks)
    ordered=order_retrieved_plan(prepared,compiled,complete,locale='en',stop=Event())
    assert ordered.status=='CONDITIONAL_SCHEDULE'and ordered.content is not None,ordered
    assert ordered.date_checks_must_be_recomputed
    route_start=len(writers)
    with patch.object(https_transport,'_connect',dial),patch.object(https_transport,'_read_response',receive):
        routed,final_capture=route_ordered_plan(prepared,json.loads(ordered.content))
    assert any(leg['state']=='estimated'for leg in routed['legs'])
    assert all(leg['state']=='unconfirmed'or leg['future_guaranteed']is False for leg in routed['legs'])
    assert len(writers)-route_start==len({leg['source']['reference']for leg in routed['legs']if leg['state']=='estimated'})
    scheduled=schedule_retrieved_plan(prepared,compiled,final_capture,routed,locale='en',stop=Event())
    assert scheduled.status=='CONDITIONAL_SCHEDULE'and scheduled.content is not None,scheduled
    assert [row['id']for row in json.loads(scheduled.content)['items']]==[row['id']for row in json.loads(ordered.content)['items']]
    if early_departure:
        assert not any(stop.day_index==3 and stop.period=='dinner'for stop in prepared.skeleton.stops)
        value=json.loads(ordered.content)
        for item in value['items']:
            event=item['schedule']['end']
            if event['day_index']==3:assert event['time']['value']<='15:00'
    try:compile_retrieved_plan(prepared,places,hotels,captures[0],checks=rows,subjects=('party',),locale='en')
    except LeaseUnavailable:pass
    else:raise AssertionError('old provider seal compiled after new attempts')
    try:bundle.places(prepared.skeleton,captures[0])
    except LeaseUnavailable:pass
    else:raise AssertionError('pre-meal provider seal remained eligible after new attempts')
    assert prepared.calls.gaode==1+len(writers) # actual city included
    from cj_api.local_lio_pipeline import publish_retrieved_plan
    previous=worker.drafts
    _,receipt=publish_retrieved_plan(prepared,compiled,final_capture,scheduled)
    saved=bundle.repository.detail(receipt.trip_id)
    assert saved is not None and saved.version==1
    final=json.loads(saved.content)
    assert final['content_version']=='structured.4' and final['calendar']==compiled.document['calendar']
    assert final['items']==json.loads(scheduled.content)['items']
    actual=next(i for i in final['items']if i['id']==fixed['item_id'])
    assert actual==next(i for i in compiled.document['items']if i['id']==fixed['item_id'])
    assert all(row['state']=='unknown'for row in final['date_checks'])
    assert worker.drafts is previous
    saved_runs[binding.message_id]=binding.run_id
    print('PASS actual complete retrieved/scheduled sole writer '+binding.message_id+' RUN '+binding.run_id,flush=True)
    return sights+meals


def selected_provider_join(host,worker,binding,bundle,skeleton,calls,scenario):
    """Original registered POI2 -> C-issued selection -> L display, not save."""
    # Two exact code targets exercise the join without claiming that this test
    # has generated, looked up, scheduled or published the complete itinerary.
    selected=replace(skeleton,stops=skeleton.stops[:1],hotels=skeleton.hotels[:1])
    origin=ExplorationOrigin(host.database,binding,worker.messages.query(binding.message_id))
    planned=sight_and_hotel_calls(selected.stops,selected.hotels,city='北京',origin=origin,sources=bundle.providers)
    bodies=[];writers=[];phases=[]
    for index,call in enumerate(planned):
        name=call.argument.query.keyword
        names=([name+'旁边']if scenario==0 else[name]if scenario==1 else[name,name])if index==0 else[name]
        rows=[dict(id='SYNTH_SELECTION_'+str(index)+'_'+str(n),name=value,cityname='北京市',
            adcode='110101',location='116.4,39.9')for n,value in enumerate(names)]
        bodies.append(dict(status='1',infocode='10000',count=str(len(rows)),pois=rows))
    def send_check():
        worker.memory_run.check()
        assert worker.message_context.active_original(binding).receipt.message_id==binding.message_id
        phases.append('send-held')
    class Writer(FixtureWriter):
        def __init__(self,reader,value):
            super().__init__(reader,send_check);self.value=value
        def response_value(self):return self.value
    async def dial():
        reader=asyncio.StreamReader();writer=Writer(reader,bodies.pop(0));writers.append(writer)
        return reader,writer
    actual_read=https_transport._read_response
    async def receive(*args):
        try:worker.memory_run.check()
        except RuntimeDenied:pass
        else:raise AssertionError('selection response retained Memory frame')
        try:worker.message_context.active_original(binding)
        except LeaseUnavailable:pass
        else:raise AssertionError('selection response retained MESSAGE frame')
        phases.append('receive-unheld');return await actual_read(*args)
    with patch.object(https_transport,'_connect',dial),patch.object(https_transport,'_read_response',receive):
        replies=tuple(json.loads(raw)for raw in calls.parallel(planned))
    assert not bodies and len(writers)==2 and all(writer.closed and len(writer.writes)==1 for writer in writers)
    assert phases==['send-held','send-held','receive-unheld','receive-unheld']
    assert all(reply['status']=='ok'and reply['items']for reply in replies)
    captured=bundle.seal()
    def prove():
        with bundle.source.hold_for_publication(binding):
            result=bundle.source.place_selection(binding,captured,selected.stops[0].item_id,
                keyword=selected.stops[0].name_zh)
            assert result['status']==('unavailable','matched','ambiguous')[scenario]
            outcomes=bundle.source.provider_outcomes(binding,captured)
            assert all(row['status']=='ok'and row['item_count']>0 for row in outcomes)
    worker._step(binding,prove)
    if scenario==2:
        try:bundle.places(selected,captured)
        except PlaceSelectionBlocked:pass
        else:raise AssertionError('ambiguous observed POIs became a selected or unavailable place')
    else:
        places,hotels=bundle.places(selected,captured)
        if scenario==0:assert places[selected.stops[0].item_id]is None
        else:assert places[selected.stops[0].item_id]['amap_id']=='SYNTH_SELECTION_0_0'
        assert hotels[0]['amap_id']=='SYNTH_SELECTION_1_0'
    # Publication data/selection cannot be read after the real holder closes.
    try:bundle.source.place_selection(binding,captured,selected.stops[0].item_id,keyword=selected.stops[0].name_zh)
    except LeaseUnavailable:pass
    else:raise AssertionError('issued selection outlived its MESSAGE/Memory frame')
    return len(writers)


def fixed_meetup(locale, named):
    if locale=='zh':
        site='北京饭店进行' if named else ''
        return '第一天我9:00–10:00要在'+site+'酒店集合，这项安排已确定，保持不变'
    meetup='a fixed hotel meetup at Beijing Hotel' if named else 'a hotel meetup'
    return f'On day 1 I have {meetup} from 9:00 to 10:00. Keep this arrangement unchanged.'


def main(*,natural_direct=False,early_departure=True,production=False,cases=(0,1,2),followups=True,duration_days=3,travel_pace='relaxed',provider_available=True,failed_kind=None,refusal_question=None):
    original_model=ExplorationPlanning._model
    original_http=httpx.MockTransport.handle_request
    original_post=TestClient.post
    wires=[];completed=[];lookups=[];posted={};saved_runs={};active={};supplier_wires=[];all_saved={}
    duration_quote=('三','四','五')[duration_days-3]+'天'
    pace_quote={'relaxed':'轻松','moderate':'适中','packed':'紧凑'}[travel_pace]
    named_route_case=(2 if production and early_departure and provider_available
                      and duration_days==3 and travel_pace=='relaxed'
                      and failed_kind is None and refusal_question is None else None)
    def post(api,url,**kwargs):
        if url=='/v4/lio/messages':
            value=json.loads(kwargs['content'])
            named=named_route_case is not None and value['message_id'].startswith(f"flow4-{value['locale']}-{named_route_case}-")
            if natural_direct and value['text']in ('直接出方案','Plan now'):
                value['text']=('节奏改为：轻松。 直接出方案。'if value['locale']=='zh'else
                    'Pace: relaxed. Please give me a plan now.')
                kwargs['content']=packed(value)
            if travel_pace!='relaxed'and value['text']in ('节奏改为：轻松','Change my travel pace to relaxed'):
                value['text']='节奏改为：'+pace_quote if value['locale']=='zh'else'Change my travel pace to '+travel_pace
                kwargs['content']=packed(value)
            if value['text']in ('我想去中国玩几天','I want to explore China'):
                if duration_days!=3:value['text']+=('。'+duration_quote if value['locale']=='zh'else'. '+str(duration_days)+' days')
                zh=value['locale']=='zh'
                value['text']+=('。明天出发。两个人。' if zh else '. Start my trip tomorrow. Two people. ')+fixed_meetup(value['locale'],named)
                if early_departure:
                    value['text']+='。我的航班18:00起飞'if zh else'. My flight leaves at 6 pm'
                if named:
                    value['text']+=('。我06:30到达。北京大兴机场。我从北京首都机场出发' if zh else
                                    '. I arrive at 6:30 am. Beijing Daxing Airport. I leave from Beijing Capital Airport')
                value['text']+='。第一天就排满'if zh else'. Fill the first day.'
                kwargs['content']=packed(value)
            posted.update(text=value['text'],locale=value['locale'],named=named)
        return original_post(api,url,**kwargs)
    def response(transport,request):
        body=json.loads(request.content)
        version=body.get('response_format',{}).get('json_schema',{}).get('schema',{}).get('properties',{}).get('version',{}).get('const')
        natural=(natural_direct and version==UNDERSTANDING and
            posted['text'].endswith(('直接出方案。','Please give me a plan now.')))
        duration_update=(production and duration_days!=3 and version==UNDERSTANDING and
            posted['text'].startswith(('我想去中国玩几天','I want to explore China')))
        pace_update=(production and travel_pace!='relaxed'and version==UNDERSTANDING and
            posted['text']in ('节奏改为：'+pace_quote,'Change my travel pace to '+travel_pace))
        if version not in (PLAN_UNDERSTANDING,SKELETON,WORDING)and not(natural or duration_update or pace_update):return original_http(transport,request)
        extra=json.loads(body['messages'][-1]['content'])
        assert body['response_format']==response_format(version)
        assert 1<=body['max_tokens']<=1536
        if duration_update or pace_update:
            factor='duration_days'if duration_update else'pace'
            proposal_value=duration_days if duration_update else travel_pace
            quote=(duration_quote if posted['locale']=='zh'else str(duration_days)+' days')if duration_update else(pace_quote if posted['locale']=='zh'else travel_pace)
            value=dict(version=UNDERSTANDING,intent='explore',current_source_index=extra['current_source_index'],updates=[
                dict(factor_key=factor,state='known',value=proposal_value,sources=[dict(source_index=extra['current_source_index'],quote=quote)])])
        elif natural:
            value=dict(version=UNDERSTANDING,intent='plan',current_source_index=extra['current_source_index'],
                updates=[dict(factor_key='pace',state='known',value='relaxed',sources=[dict(
                    source_index=extra['current_source_index'],quote='节奏改为：轻松。'if posted['locale']=='zh'else'Pace: relaxed.')])])
        elif version==PLAN_UNDERSTANDING:
            zh=extra['locale']=='zh'
            named=posted['named']
            quote=fixed_meetup(extra['locale'],named)
            site=('北京饭店'if zh else'Beijing Hotel')if named else None
            beginning=(date.fromisoformat(extra['original_question_days'][0])+timedelta(days=1)).isoformat()
            value=dict(version=version,current_source_index=extra['current_source_index'],observations=[
                dict(field='start_date',state='known',value=beginning,note=None,
                     sources=[dict(source_index=0,quote='明天出发'if zh else'Start my trip tomorrow')]),
                dict(field='party_size',state='known',value=2,note=None,
                     sources=[dict(source_index=0,quote='两个人'if zh else'Two people')]),
                dict(field='departure.time',state='known',value='18:00',note=None,
                     sources=[dict(source_index=0,quote='18:00'if zh else'6 pm')]),
                dict(field='departure.mode',state='known',value='flight',note=None,
                     sources=[dict(source_index=0,quote='航班'if zh else'flight')]),
                dict(field='first_day_full',state='known',value=True,note=None,
                     sources=[dict(source_index=0,quote='第一天就排满'if zh else'Fill the first day')])],
                companions=[],fixed_items=[dict(label='酒店集合'if zh else'hotel meetup',source_index=0,quote=quote,
                    detail_refs=[],kind='appointment',applies_to=['self'],locked=True,booking_evidence=None,
                    start_date=None,start_time='09:00',start_timezone=None,start_place=site,
                    end_date=None,end_time='10:00',end_timezone=None,end_place=site,
                    unknown_fields=[],uncertain_fields={})],temporary_conditions=[])
            if named:
                value['observations'].append(dict(field='arrival.time',state='known',value='06:30',note=None,
                    sources=[dict(source_index=0,quote='06:30'if zh else'6:30 am')]))
                for field,name in (('arrival.place','北京大兴机场'if zh else'Beijing Daxing Airport'),
                                   ('departure.place','北京首都机场'if zh else'Beijing Capital Airport')):
                    value['observations'].append(dict(field=field,state='known',value=name,note=None,
                        sources=[dict(source_index=0,quote=name)]))
            if not early_departure:
                value['observations']=[row for row in value['observations']if row['field']not in ('departure.time','departure.mode')]
        elif version==SKELETON:
            value=proposal(tuple(DayRecipe(row['day_index'],row['sights'],tuple(row['meals']))for row in extra['days']))
        else:value=dict(version=WORDING,items=[dict(item_id=item['item_id'],reason=None,reason_refs=[],tip=None)for item in extra['items']])
        wires.append((version,body['max_tokens']))
        identity=dict(id='pipeline-model-fixture-'+str(len(wires)),model=body['model'])
        chunks=[dict(**identity,choices=[dict(index=0,delta=dict(content=packed(value).decode()),finish_reason=None)]),
                dict(**identity,choices=[dict(index=0,delta={},finish_reason='stop')]),
                dict(**identity,choices=[],usage=dict(prompt_tokens=50,completion_tokens=100,total_tokens=150))]
        raw=''.join('data: '+json.dumps(chunk)+'\n\n'for chunk in chunks)+'data: [DONE]\n\n'
        return httpx.Response(200,stream=httpx.ByteStream(raw.encode()))
    def model(host,worker,binding,view,profile,system,extra):
        active.update(worker=worker,binding=binding)
        if profile==RESPONSE and extra.get('scene')=='plan_now_preview':
            from cj_api.local_lio_pipeline import prepare_generation
            assert extra['prior_model_calls']==int(natural_direct)
            prepared=prepare_generation(host,worker,binding,view,locale=extra['locale'],effective=extra['effective'],
                prior_model_calls=extra['prior_model_calls'])
            projection=prepared.projection;projected=prepared.projected
            fields=projection.fields;edges=prepared.edges
            calls=prepared.calls;skeleton=prepared.skeleton;bundle=prepared.sources
            assert prepared.preflight_size[:2]==((18,15)if early_departure else(16,13))
            assert calls.gaode==1
            assert projection.edge_options['departure.mode']==(dict(state='known',value='flight')if early_departure else dict(state='missing'))
            assert edges.windows[-1][0].end==(extra['duration_days']-1)*86400+(15 if early_departure else 12)*3600
            assert edges.override_explanations==('first_day_full_requested',)
            assert 'mode'not in fields['departure']and 'first_day_full'not in fields
            assert fields['party_size']==dict(state='known',value=2)
            fixed,=fields['fixed_items']
            assert projected.fields['fixed_items'][0]['item_id']==fixed['item_id']
            assert projected.fields['fixed_items'][0]['start']['timezone']==dict(state='missing')
            assert fixed['applies_to']==['self'] and fixed['locked']==dict(state='known',value=True)
            assert fixed['start']['date']==fields['arrival']['date']
            assert fixed['start']['time']==dict(state='known',value='09:00')
            assert fixed['end']['time']==dict(state='known',value='10:00')
            assert fixed['booking_status']==dict(state='missing')
            sealed=bundle.seal() # genuinely empty provider set; not failed lookup evidence
            def capture():
                snapshot,_=bundle.calendar_capture.records()
                assert snapshot.fields['fixed_items']==fields['fixed_items']
                assert snapshot.fields['party_size']==dict(state='known',value=2)
                assert bundle.calendar_capture.basis.day_indices()=={fixed['item_id']:(1,1)}
                with bundle.source.hold_for_publication(binding)as check:check()
            worker._step(binding,capture)
            try:bundle.places(skeleton,sealed)
            except LeaseUnavailable:pass
            else:raise AssertionError('no original provider operations became selection fallback')
            if len(completed)%3==1:lookups.append(full_provider_join(prepared,early_departure=early_departure,saved_runs=saved_runs))
            else:lookups.append(selected_provider_join(host,worker,binding,bundle,skeleton,calls,len(completed)%3))
            items=tuple(dict(item_id=stop.item_id,tip=None)for stop in skeleton.stops)
            # Two explicit wording requests share one original RUN. Every one
            # traverses the registered exit, financial journal and true4 origin.
            # The component harness still invokes the old preview afterwards.
            # Keep that extra fixture model inside the actual native6 ceiling;
            # production generation does not append a preview model after save.
            batches=(items,)if natural_direct else(items[::2],items[1::2])
            results=calls.parallel(tuple(model_call(host,worker,binding,view,WORDING,WORDING_SYSTEM,
                dict(locale=extra['locale'],items=batch))for batch in batches))
            for result,batch in zip(results,batches,strict=True):
                parse_wording(result.encode(),batch,allowed_reason_keys=set())
            # Includes actual constraint understanding/skeleton/wording, any
            # prior prefix extraction, and reserved final Memory. The fixture
            # leaves one slot for its separate historical preview model.
            assert worker.lio_memory is not None
            assert calls.model==5 and calls.model_slots_left==1
            completed.append(binding.run_id)
            print('PASS native4 sourced plan understanding -> original NEEDS/calendar/profile hold + skeleton + two registered wording calls '+binding.message_id+' RUN '+binding.run_id+('; sole writer saved'if binding.message_id in saved_runs else'; no Trip publication'),flush=True)
        return original_model(host,worker,binding,view,profile,system,extra)
    original_receipt=TripRepository.rich_plan_receipt
    def receipt(repository,binding):
        value=original_receipt(repository,binding)
        if value is not None:
            if not provider_available:
                saved=repository.detail(value.trip_id)
                document=json.loads(saved.content)
                suggestions=[item for item in document['items']if item['kind']in ('sight','meal')]
                assert suggestions and all(item['place']['state']=='unconfirmed'and item['place']['source']is None for item in suggestions)
                assert all(leg['state']=='unconfirmed'and leg['source']is None for leg in document['legs'])
            saved_runs[binding.message_id]=binding.run_id
            if binding.run_id not in completed:completed.append(binding.run_id)
        return value
    def send_check():
        active['worker'].memory_run.check()
        assert active['worker'].message_context.active_original(active['binding']).receipt.message_id==active['binding'].message_id
    class Writer(FixtureWriter):
        def __init__(self,reader):super().__init__(reader,send_check,available=provider_available)
        def write(self,raw):
            parsed=urlsplit(raw.split(b'\r\n',1)[0].split(b' ')[1].decode('ascii'))
            self.path=parsed.path;self.query=parse_qs(parsed.query)
            self.keyword=self.query.get('keywords',[''])[0]
            self.provider_id='SYNTH_FACTORY_'+str(len(supplier_wires));supplier_wires.append(self.path)
            super().write(raw)
        def response_value(self):
            if not provider_available:return super().response_value()
            # Explicit synthetic per-component failures; never manufacture an
            # unavailable source in the host after an ambiguous/unknown result.
            failed=(failed_kind=='hotel'and 'hotel'in self.keyword or
                failed_kind=='route'and self.path.startswith('/v3/direction/') or
                failed_kind=='sight'and 's'in self.keyword and 'hotel'not in self.keyword)
            if failed:return dict(status='0',infocode='10001',info='INVALID_USER_KEY')
            if self.path.startswith('/v3/direction/'):
                a=self.query['origin'][0];b=self.query['destination'][0]
                return dict(status='1',infocode='10000',count='1',route=dict(origin=a,destination=b,
                    paths=[dict(distance='120',duration='60',steps=[dict(polyline=a+';'+b)])]))
            return dict(status='1',infocode='10000',count='1',pois=[dict(id=self.provider_id,
                name=self.keyword,cityname='北京市',adcode='110101',location='116.4,39.9')])
    async def dial():
        reader=asyncio.StreamReader();writer=Writer(reader);return reader,writer
    with ExitStack()as stack:
        stack.enter_context(patch.object(TestClient,'post',post))
        stack.enter_context(patch.object(httpx.MockTransport,'handle_request',response))
        stack.enter_context(patch.object(ExplorationPlanning,'_model',model))
        if production:
            stack.enter_context(patch.object(https_transport,'_connect',dial))
            stack.enter_context(patch.object(TripRepository,'rich_plan_receipt',receipt))
        if production:
            # Each language is an independent fresh private fixture account.
            # Keep the original200 account budget; never reset/top up a live
            # ledger merely to run unrelated regression cases in one cohort.
            for language in ('zh','en'):
                saved_runs.clear()
                native.main(saved_runs=saved_runs,generation=True,languages=(language,),cases=cases,followups=followups,trip_days=duration_days,pace_labels=(pace_quote,travel_pace.title()),unconfirmed_places=not provider_available,refusal_question=refusal_question,named_route_case=named_route_case)
                assert len(saved_runs)==(0 if refusal_question is not None else len(cases))
                all_saved.update(saved_runs)
        else:native.main(saved_runs=saved_runs)

    if production and refusal_question is not None:
        assert not all_saved and not completed
        print('PASS production evidence-limited refusal ZH/EN, no sole-writer receipt/Trip/version; fixture HTTP/0 real',flush=True)
        return
    if production:
        assert len(all_saved)==len(completed)==2*len(cases) and sum(v in (PLAN_UNDERSTANDING,SKELETON,WORDING)for v,_ in wires)==(8 if natural_direct else 10)*len(cases)
        print('PASS default production factory '+str(len(cases))+'ZH/'+str(len(cases))+'EN complete skeleton/selected retrieval/order/routes/schedule/final wording/sole writer and actual timeline Card3; '+str(len(supplier_wires))+' fixture supplier calls; real/G6/G9 UNRUN',flush=True)
        return
    assert len(saved_runs)==2
    assert len(completed)==6 and len(wires)==24 and lookups==([2,13,2,2,13,2]if early_departure else[2,11,2,2,11,2])
    print('PASS source-held selected places and C ordering; '+str(sum(lookups))+' fixture lookups; two sole-writer saves preserve fixed clocks and original edge windows',flush=True)
    if natural_direct:print('PASS original natural direct with full-sentence prefix -> sourced profile/defaults -> issued PlanNow source; actual extra profile model retained in native6 budget, no rewritten original or renderer',flush=True)
    print('PASS ZH3/EN3 signed native4/four actual pipeline model registrations each plus fixture preview; real caps/schema/Meter, fixture HTTP only; local final publisher exercised; production factory/G6/G9 real UNRUN',flush=True)


if __name__=='__main__':main()
