"""Explicit native4 generator injection leaves the old preview dependency optional."""
from datetime import date
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cj_api.local_lio_exploration import ExplorationPlanning


class GenerationWiring(unittest.TestCase):
    def test_plan_now_delegates_to_the_explicit_generator_without_preview_model(self):
        calls=[];events=[];result=object()
        class Generation:
            def plan(self,host,worker,binding,view,*,locale,effective,prior_model_calls):
                calls.append((host,worker,binding,view,locale,effective,prior_model_calls));return result
        planner=ExplorationPlanning(None,SimpleNamespace(),generation=Generation())
        def event(binding,state,kind,value):events.append((kind,value));return state
        worker=SimpleNamespace(_event=event);view=SimpleNamespace(profile={})
        self.assertIs(planner._plan(worker,'binding','state',view,'en',prior_model_calls=1),result)
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][4],'en');self.assertEqual(calls[0][-1],1)
        self.assertTrue(any('planning_started'in value for _,value in events))

    def test_rollback_dispatch_never_enters_new_plan_now_generation(self):
        import json,os
        from cj_api.local_lio_exploration import ExplorationDispatch,exploration_enabled
        from cj_api.local_lio_exploration_profile import ProfileView
        from cj_api.lio_exploration_profile import Original
        from cj_message.demo_dialogue import LIO_VERSION_V4
        rows=(('zh','直接出方案'),('en','Plan now'),
              ('zh','节奏改为：轻松。 直接出方案。'),
              ('en','Change my travel pace to relaxed. Plan now.'))
        for flag in ('0','1'):
            for locale,text in rows:
                with self.subTest(flag=flag,locale=locale,text=text),patch.dict(os.environ,{'CJ_LIO_EXPLORATION_ENABLED':flag}):
                    generated=[];legacy_calls=[];events=[]
                    legacy=SimpleNamespace(execute=lambda *args:legacy_calls.append(args)or'legacy')
                    class Generation:
                        def plan(self,*args,**kwargs):generated.append((args,kwargs));return'generated'
                    planner=ExplorationPlanning(None,legacy,enabled=exploration_enabled(),generation=Generation())
                    view=ProfileView((Original('current',1,text),),(),{},'0'*64)
                    planner.profiles=SimpleNamespace(read=lambda *args:view,
                        accept=lambda worker,binding,state,*args,**kwargs:(state,{}))
                    planner._phase=lambda _:None
                    planner._model=lambda *args,**kwargs:json.dumps(dict(version='LIO-exploration-understanding.1',
                        intent='plan',current_source_index=0,updates=[]))
                    worker=SimpleNamespace(runs=SimpleNamespace(snapshot=lambda _:object()),
                        _event=lambda binding,state,kind,value:events.append((kind,value))or state)
                    original=SimpleNamespace(protocol=LIO_VERSION_V4,locale=locale)
                    result=ExplorationDispatch(legacy,planner).execute(worker,'binding','state',text,original)
                    self.assertEqual(result,'generated'if flag=='1'else'legacy')
                    self.assertEqual(len(generated),int(flag))
                    self.assertEqual(len(legacy_calls),1-int(flag))
                    if flag=='0':
                        self.assertIs(legacy_calls[0][-1],original)
                        self.assertEqual(events,[])

    def test_saved_rich_calendar_phase_uses_the_explicit_reader(self):
        class Generation:
            def current(self,host,binding):
                return SimpleNamespace(trip=SimpleNamespace(content=b'{"content_version":"structured.4","calendar":{"state":"undated"},"days":[{"day_index":1}]}'))
        legacy=SimpleNamespace(calendar=SimpleNamespace(current=lambda _:self.fail('legacy reader used for S4')))
        planner=ExplorationPlanning(None,legacy,generation=Generation())
        self.assertEqual(planner._phase('binding'),'undated')


    def test_unknown_edge_proximity_asks_for_evidence_without_publication(self):
        from cj_api.local_lio_pipeline_generation import PipelineGeneration
        import cj_api.local_lio_pipeline_generation as generation
        for locale,question in (('zh','能补充酒店的具体位置吗？'),
                                ('en','Can you provide the exact hotel location?')):
            for retained in (False,True):
                with self.subTest(locale=locale,retained=retained):
                    events=[]
                    host=SimpleNamespace(current=lambda _:object()if retained else None,
                        _finish=lambda worker,binding,state,body,scene,lang:body)
                    worker=SimpleNamespace(runs=SimpleNamespace(snapshot=lambda _:object()),
                        _event=lambda binding,state,kind,value:events.append((kind,value))or state)
                    prepared=SimpleNamespace(projection=SimpleNamespace(fields={'party_size':{'state':'known','value':1}}))
                    capture=SimpleNamespace(basis=SimpleNamespace(day_count=3,start_date=None))
                    with patch.multiple(generation,prepare_generation=unittest.mock.DEFAULT,
                            retrieve_skeleton=unittest.mock.DEFAULT,compile_retrieved_plan=unittest.mock.DEFAULT,
                            order_retrieved_plan=unittest.mock.DEFAULT,route_ordered_plan=unittest.mock.DEFAULT,
                            publish_retrieved_plan=unittest.mock.DEFAULT)as stages:
                        stages['prepare_generation'].return_value=prepared
                        stages['retrieve_skeleton'].return_value=({},(),capture)
                        stages['order_retrieved_plan'].return_value=SimpleNamespace(content=None,
                            status='UNKNOWN',reason='EDGE_DAY_PROXIMITY_UNCONFIRMED')
                        body=PipelineGeneration().plan(host,worker,'binding','view',locale=locale,
                            effective={},prior_model_calls=1)
                        self.assertIn(question,body)
                        self.assertIn('附近'if locale=='zh'else'near the hotel',body)
                        self.assertEqual(('原行程保留'if locale=='zh'else'original itinerary is kept')in body,retained)
                        stages['route_ordered_plan'].assert_not_called()
                        stages['publish_retrieved_plan'].assert_not_called()
                        self.assertEqual(len(events),1)


    def test_saved_plan_discloses_unconfirmed_edge_day_proximity(self):
        # JT 2026-11-25 (via coordination, "照样保存并提示"): a plan saved without an
        # observed lodging point says so in the reply; other saves are unchanged.
        from cj_api.local_lio_pipeline_generation import PipelineGeneration
        import cj_api.local_lio_pipeline_generation as generation
        hints={'zh':'首末日的抵达或离开时间未定，已建议把活动安排在住处附近；补充酒店位置后可以再调整',
               'en':'Arrival or departure times are not set, so first- and last-day activities are kept near where you stay; you can adjust after adding your hotel'}
        for locale,hint in hints.items():
            for edges in ((),('stop-1','stop-9')):
                with self.subTest(locale=locale,edges=edges):
                    host=SimpleNamespace(current=lambda _:None,_finish=lambda worker,binding,state,body,scene,lang:body)
                    worker=SimpleNamespace(runs=SimpleNamespace(snapshot=lambda _:object()),
                        _event=lambda binding,state,kind,value:self.fail('saved plan emitted a refusal event'))
                    prepared=SimpleNamespace(projection=SimpleNamespace(fields={'party_size':{'state':'known','value':1}}))
                    capture=SimpleNamespace(basis=SimpleNamespace(day_count=3,start_date=None))
                    with patch.multiple(generation,prepare_generation=unittest.mock.DEFAULT,
                            retrieve_skeleton=unittest.mock.DEFAULT,compile_retrieved_plan=unittest.mock.DEFAULT,
                            order_retrieved_plan=unittest.mock.DEFAULT,route_ordered_plan=unittest.mock.DEFAULT,
                            schedule_retrieved_plan=unittest.mock.DEFAULT,word_retrieved_plan=unittest.mock.DEFAULT,
                            publish_retrieved_plan=unittest.mock.DEFAULT)as stages:
                        stages['prepare_generation'].return_value=prepared
                        stages['retrieve_skeleton'].return_value=({},(),capture)
                        stages['order_retrieved_plan'].return_value=SimpleNamespace(content='{}',status='CONDITIONAL_SCHEDULE',reason='')
                        stages['route_ordered_plan'].return_value=({},capture)
                        stages['schedule_retrieved_plan'].return_value=SimpleNamespace(content='{}',status='CONDITIONAL_SCHEDULE',reason='')
                        stages['word_retrieved_plan'].return_value=SimpleNamespace(summary='Summary.',unknown_transfers=(),
                            edge_proximity_unconfirmed=edges)
                        stages['publish_retrieved_plan'].return_value=(None,SimpleNamespace(proposal_id='p'))
                        body=PipelineGeneration().plan(host,worker,'binding','view',locale=locale,
                            effective={},prior_model_calls=1)
                        self.assertIn('行程已保存'if locale=='zh'else'The itinerary is saved',body)
                        self.assertEqual(hint in body,bool(edges),body)


    def test_refusals_log_stage_and_error_class_without_content(self):
        # HK run -42 (2026-11-25): "直接出方案" twice ended in the generic refusal with no log line.
        # Each refusal now names its stage, error class and content-free details only.
        from pydantic import BaseModel,ValidationError
        from cj_api.local_lio_pipeline_generation import PipelineGeneration
        import cj_api.local_lio_pipeline_generation as generation
        from cj_api.lio_pipeline_skeleton import SkeletonUnavailable,CapacityExceeded
        from cj_api.lio_pipeline_model import WordingUnavailable
        from cj_api.local_lio_pipeline_places import PlaceSelectionBlocked
        from cj_trip.structured import SourceRejected
        from cj_agent.draft import DraftRejected
        secret='春熙路附近的秘密酒店'
        class Day(BaseModel):
            ordinal:int
        try:Day.model_validate({'ordinal':secret})
        except ValidationError as error:validation=error
        def skeleton_failure():
            try:raise validation
            except ValidationError as error:
                try:raise SkeletonUnavailable('complete typed skeleton required')from error
                except SkeletonUnavailable as wrapped:return wrapped
        cases=(('retrieve',skeleton_failure(),'SkeletonUnavailable',('cause=ValidationError','cause_errors=*:int_parsing')),
               ('compile',PlaceSelectionBlocked('place selection is ambiguous; '+secret),'PlaceSelectionBlocked',()),
               ('word',WordingUnavailable('exact wording batch item set required'),'WordingUnavailable',()),
               ('publish',SourceRejected('days.0.items.2.place','quote_in_original'),'SourceRejected',
                ('field=days.0.items.2.place','rule=quote_in_original')),
               ('schedule',DraftRejected(secret),'DraftRejected',()),
               ('retrieve',CapacityExceeded('too many'),'CapacityExceeded',('capacity=1',)))
        order={'prepare':'prepare_generation','retrieve':'retrieve_skeleton','compile':'compile_retrieved_plan',
               'order':'order_retrieved_plan','route':'route_ordered_plan','schedule':'schedule_retrieved_plan',
               'word':'word_retrieved_plan','publish':'publish_retrieved_plan'}
        for stage,error,name,details in cases+(('order',None,None,('reason=EXPLICIT_CONSTRAINTS_INFEASIBLE',)),):
            with self.subTest(stage=stage,error=name):
                host=SimpleNamespace(current=lambda _:None,_finish=lambda worker,binding,state,body,scene,lang:body)
                worker=SimpleNamespace(runs=SimpleNamespace(snapshot=lambda _:object()),
                    _event=lambda binding,state,kind,value:state)
                prepared=SimpleNamespace(projection=SimpleNamespace(fields={}))
                capture=SimpleNamespace(basis=SimpleNamespace(day_count=3,start_date=None))
                with patch.multiple(generation,**{f:unittest.mock.DEFAULT for f in order.values()})as stages:
                    stages['prepare_generation'].return_value=prepared
                    stages['retrieve_skeleton'].return_value=({},(),capture)
                    stages['order_retrieved_plan'].return_value=SimpleNamespace(content='{}',status='OK',reason='')
                    stages['route_ordered_plan'].return_value=({},capture)
                    stages['schedule_retrieved_plan'].return_value=SimpleNamespace(content='{}',status='OK',reason='')
                    if error is None:
                        stages['order_retrieved_plan'].return_value=SimpleNamespace(content=None,status='REFUSED',
                            reason='EXPLICIT_CONSTRAINTS_INFEASIBLE')
                    else:
                        stages[order[stage]].side_effect=error
                    with self.assertLogs('cj_usage.audit','INFO')as logs:
                        PipelineGeneration().plan(host,worker,SimpleNamespace(run_id='run-42'),'view',locale='zh',
                            effective={},prior_model_calls=1)
                line=[l for l in logs.output if 'LIO_PIPELINE_REFUSED'in l]
                self.assertEqual(len(line),1,logs.output)
                self.assertIn('run_id=run-42',line[0])
                self.assertIn('stage='+stage,line[0])
                if name:self.assertIn('error='+name,line[0])
                for detail in details:self.assertIn(detail,line[0])
                self.assertNotIn(secret,line[0])
                self.assertNotIn('春熙路',line[0])



    def test_refusal_log_keeps_only_schema_field_names_in_error_locations(self):
        # #1654 review: pydantic locations can carry model-written keys (extra keys, dict keys).
        from cj_api.local_lio_pipeline_generation import _log_refusal
        from cj_api.lio_pipeline_skeleton import SkeletonUnavailable
        from cj_message.lio_pipeline_schema import Skeleton
        from cj_message.lio_plan_input_schema import PlanUnderstanding
        def wrapped(model,value):
            try:model.model_validate(value)
            except Exception as error:
                try:raise SkeletonUnavailable('complete typed skeleton required')from error
                except SkeletonUnavailable as outer:return outer
            self.fail('expected a validation error')
        extra=wrapped(Skeleton,{'version':'x','days':[{'30.6578:104.0812':1}]})
        uncertain=wrapped(PlanUnderstanding,{'fixed_items':[{'uncertain_fields':{'Chunxi_Road_Atour_Hotel':1}}]})
        for error in (extra,uncertain):
            with self.subTest(error=str(error.__cause__)[:40]),self.assertLogs('cj_usage.audit','INFO')as logs:
                _log_refusal(SimpleNamespace(run_id='run-1'),'retrieve',error)
            line=logs.output[0]
            self.assertIn('cause_errors=',line)
            for leaked in ('30.6578','104.0812','Chunxi','Atour'):self.assertNotIn(leaked,line)
        with self.assertLogs('cj_usage.audit','INFO')as logs:
            _log_refusal(SimpleNamespace(run_id='run-1'),'retrieve',extra)
        self.assertRegex(logs.output[0],r'days\.0\.\*:extra_forbidden')

    def test_refusal_log_never_raises(self):
        from cj_api.local_lio_pipeline_generation import _log_refusal
        class Broken(Exception):
            def __str__(self):raise RuntimeError('broken')
        _log_refusal(SimpleNamespace(run_id='run-1'),'word',Broken())


    def saved_reply(self,locale,far):
        from cj_api.local_lio_pipeline_generation import PipelineGeneration
        import cj_api.local_lio_pipeline_generation as generation
        host=SimpleNamespace(current=lambda _:None,_finish=lambda worker,binding,state,body,scene,lang:body)
        worker=SimpleNamespace(runs=SimpleNamespace(snapshot=lambda _:object()),_event=lambda binding,state,kind,value:state)
        capture=SimpleNamespace(basis=SimpleNamespace(day_count=3,start_date=None))
        with patch.multiple(generation,prepare_generation=unittest.mock.DEFAULT,retrieve_skeleton=unittest.mock.DEFAULT,
                compile_retrieved_plan=unittest.mock.DEFAULT,order_retrieved_plan=unittest.mock.DEFAULT,
                route_ordered_plan=unittest.mock.DEFAULT,schedule_retrieved_plan=unittest.mock.DEFAULT,
                word_retrieved_plan=unittest.mock.DEFAULT,publish_retrieved_plan=unittest.mock.DEFAULT)as stages:
            stages['prepare_generation'].return_value=SimpleNamespace(projection=SimpleNamespace(fields={}))
            stages['retrieve_skeleton'].return_value=({},(),capture)
            stages['order_retrieved_plan'].return_value=SimpleNamespace(content='{}',status='CONDITIONAL_SCHEDULE',reason='')
            stages['route_ordered_plan'].return_value=({},capture)
            stages['schedule_retrieved_plan'].return_value=SimpleNamespace(content='{}',status='CONDITIONAL_SCHEDULE',reason='')
            stages['word_retrieved_plan'].return_value=SimpleNamespace(summary='Summary.',unknown_transfers=(),
                edge_proximity_unconfirmed=(),edge_far=far)
            stages['publish_retrieved_plan'].return_value=(None,SimpleNamespace(proposal_id='p'))
            return PipelineGeneration().plan(host,worker,SimpleNamespace(run_id='r'),'view',locale=locale,
                effective={},prior_model_calls=1)

    def test_far_edge_days_are_disclosed_on_anchors_and_in_the_saved_reply(self):
        # JT 2026-11-26 (coordination thread, "照样保存并提示（推荐）"): a located hotel with a
        # first/last-day stop outside walking range saves; the anchor note and the reply say so.
        from cj_api.local_lio_pipeline import disclose_far_edges, FAR_EDGE_HINTS
        from cj_api.local_lio_pipeline_generation import PipelineGeneration
        import cj_api.local_lio_pipeline_generation as generation
        document=dict(items=[dict(id='p-lodging-d1-out',kind='hotel',note='Hotel estimate.'),
                             dict(id='p-lodging-d3-back',kind='hotel',note='Hotel estimate.'),
                             dict(id='p-stop-1',kind='sight',note='Fine.')])
        for locale in ('zh','en'):
            for far,(first,last) in (((),(False,False)),(((1,'p-stop-1'),),(True,False)),(((3,'p-stop-9'),),(False,True)),
                                     (((1,'a'),(3,'b')),(True,True))):
                with self.subTest(locale=locale,far=far):
                    value=disclose_far_edges(document,far,id_prefix='p',day_count=3,locale=locale)
                    notes={i['id']:i['note']for i in value['items']}
                    self.assertEqual(FAR_EDGE_HINTS[locale][0]in notes['p-lodging-d1-out'],first)
                    self.assertEqual(FAR_EDGE_HINTS[locale][1]in notes['p-lodging-d3-back'],last)
                    self.assertEqual(notes['p-stop-1'],'Fine.')
                    self.assertEqual(document['items'][0]['note'],'Hotel estimate.')  # input not mutated
        for locale,last_hint in (('zh','最后一天的景点离酒店有一段距离'),('en',"the last day's sights are some distance from the hotel")):
            body=self.saved_reply(locale,((1,'a'),(3,'b')))
            self.assertIn(last_hint,body.lower()if locale=='en'else body)
            self.assertIn(last_hint,(self.saved_reply(locale,((3,'b'),))).lower()if locale=='en'else self.saved_reply(locale,((3,'b'),)))
        for locale,hint in (('zh','第一天的景点离酒店有一段距离，到达后建议打车过去；想换近一点的可以告诉我'),
                            ('en',"Day 1's sights are some distance from the hotel; take a taxi after you arrive, or tell me to swap in somewhere closer")):
            for far in ((),((1,'p-stop-1'),)):
                with self.subTest(reply=locale,far=far):
                    host=SimpleNamespace(current=lambda _:None,_finish=lambda worker,binding,state,body,scene,lang:body)
                    worker=SimpleNamespace(runs=SimpleNamespace(snapshot=lambda _:object()),
                        _event=lambda binding,state,kind,value:self.fail('saved plan emitted a refusal event'))
                    prepared=SimpleNamespace(projection=SimpleNamespace(fields={}))
                    capture=SimpleNamespace(basis=SimpleNamespace(day_count=3,start_date=None))
                    with patch.multiple(generation,prepare_generation=unittest.mock.DEFAULT,
                            retrieve_skeleton=unittest.mock.DEFAULT,compile_retrieved_plan=unittest.mock.DEFAULT,
                            order_retrieved_plan=unittest.mock.DEFAULT,route_ordered_plan=unittest.mock.DEFAULT,
                            schedule_retrieved_plan=unittest.mock.DEFAULT,word_retrieved_plan=unittest.mock.DEFAULT,
                            publish_retrieved_plan=unittest.mock.DEFAULT)as stages:
                        stages['prepare_generation'].return_value=prepared
                        stages['retrieve_skeleton'].return_value=({},(),capture)
                        stages['order_retrieved_plan'].return_value=SimpleNamespace(content='{}',status='CONDITIONAL_SCHEDULE',reason='')
                        stages['route_ordered_plan'].return_value=({},capture)
                        stages['schedule_retrieved_plan'].return_value=SimpleNamespace(content='{}',status='CONDITIONAL_SCHEDULE',reason='')
                        stages['word_retrieved_plan'].return_value=SimpleNamespace(summary='Summary.',unknown_transfers=(),
                            edge_proximity_unconfirmed=(),edge_far=far)
                        stages['publish_retrieved_plan'].return_value=(None,SimpleNamespace(proposal_id='p'))
                        body=PipelineGeneration().plan(host,worker,SimpleNamespace(run_id='r'),'view',locale=locale,
                            effective={},prior_model_calls=1)
                    self.assertIn('行程已保存'if locale=='zh'else'The itinerary is saved',body)
                    self.assertEqual(hint in body,bool(far),body)

    def test_remaining_refusals_name_their_reason(self):
        # Coordination 2026-11-26: a plan that still cannot be saved says why, not just "没能保存".
        from cj_api.local_lio_pipeline_generation import PipelineGeneration
        import cj_api.local_lio_pipeline_generation as generation
        from cj_api.local_lio_pipeline import DestinationUnresolved
        from cj_api.local_lio_pipeline_places import PlaceSelectionBlocked
        from cj_api.lio_pipeline_model import WordingUnavailable
        from cj_trip.structured import SourceRejected
        # #1681 review: only reasons with one sure cause name it; ambiguous ones stay generic or neutral.
        cases=((dict(reason='KNOWN_OPENING_CONFLICT'),'有景点在安排的那天不开放','a stop is closed on its planned day'),
               (dict(reason='EXPLICIT_CONSTRAINTS_INFEASIBLE'),'有一天的时间排不开','one of the days could not fit in time'),
               (dict(reason='FIRST_DAY_LIGHT_RECIPE_REQUIRED'),'到达时间未定，第一天只能轻松安排','with no arrival time, day 1 must stay light'),
               (dict(reason='EDGE_WINDOWS_CONFLICT'),'到达或离开的时间和安排对不上','your arrival or departure time clashes with the plan'),
               (dict(error=DestinationUnresolved({})),'目的地还没能确认是哪座城市','I could not confirm which city you mean'),
               (dict(error=PlaceSelectionBlocked('x')),'有几个地点没能确认是哪一处','I could not confirm which place some stops are'),
               (dict(error=WordingUnavailable('x')),'整理行程文字时出了问题','something went wrong while writing up the plan'),
               (dict(error=SourceRejected('f','r')),None,None),
               (dict(reason='SOMETHING_NEW'),None,None))
        for spec,zh,en in cases:
            for locale,detail in (('zh',zh),('en',en)):
                with self.subTest(spec=str(spec),locale=locale):
                    host=SimpleNamespace(current=lambda _:None,_finish=lambda worker,binding,state,body,scene,lang:body)
                    worker=SimpleNamespace(runs=SimpleNamespace(snapshot=lambda _:object()),
                        _event=lambda binding,state,kind,value:state)
                    prepared=SimpleNamespace(projection=SimpleNamespace(fields={}))
                    capture=SimpleNamespace(basis=SimpleNamespace(day_count=3,start_date=None))
                    with patch.multiple(generation,prepare_generation=unittest.mock.DEFAULT,
                            retrieve_skeleton=unittest.mock.DEFAULT,compile_retrieved_plan=unittest.mock.DEFAULT,
                            order_retrieved_plan=unittest.mock.DEFAULT,route_ordered_plan=unittest.mock.DEFAULT)as stages:
                        stages['prepare_generation'].return_value=prepared
                        stages['retrieve_skeleton'].return_value=({},(),capture)
                        if 'reason' in spec:
                            stages['order_retrieved_plan'].return_value=SimpleNamespace(content=None,status='CONFLICT',reason=spec['reason'])
                        else:
                            stages['compile_retrieved_plan'].side_effect=spec['error']
                        body=PipelineGeneration().plan(host,worker,SimpleNamespace(run_id='r'),'view',locale=locale,
                            effective={},prior_model_calls=1)
                    self.assertIn('这次没能把完整方案保存'if locale=='zh'else'I could not save a complete plan',body)
                    if detail:self.assertIn(detail,body)
                    else:
                        for wrong in ('之前保存','固定安排在时间','saved arrangements','fixed arrangements do not fit'):
                            self.assertNotIn(wrong,body)


if __name__=='__main__':unittest.main()
