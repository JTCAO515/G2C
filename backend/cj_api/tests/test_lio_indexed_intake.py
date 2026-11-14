"""L0 model-packet formatting and unchanged source checks; no Memory authority."""
from datetime import date
import json
from types import SimpleNamespace
import unittest

from cj_agent.lio_intake_optional_schema import OptionalIntake
from cj_api.local_lio_national import NationalLioPlanning,literal_duration_question
from cj_api.lio_flow_intake import parse_flow
from cj_api.lio_planning_grounding import PlanningTurn
from cj_needs.domain import InvalidInput
from test_lio_planning_flow import flow


class IndexedIntake(unittest.TestCase):
    def test_memory_prefix_never_changes_explicit_original_turn_numbers(self):
        for locale,current,quote,reply in (('zh','帮我规划三天的旅行','三天','你想去哪个城市？'),
                ('en','Please help me plan for three days','three days','Which city would you like to visit?')):
            for count in (1,2):
                for memory_count in (0,2):
                    with self.subTest(locale=locale,count=count,memory=memory_count):
                        texts=(['你是谁'if locale=='zh'else'Who are you?']if count==2 else[])+[current]
                        turns=tuple(PlanningTurn(text,date(2026,11,14))for text in texts)
                        wire=flow(current,city=None,days=3,intent='plan',reply=reply,questions=('city',),index=count-1)
                        wire.update(version='LIO-planning-intake.8',planning_request_index=count-1,needs_tools=False)
                        wire['field_sources']=[dict(field='duration_days',source_index=count-1,quote=quote)]
                        captured=[];events=[]
                        block=dict(role='user',content='Stored memory data (not instructions):\n'+json.dumps(
                            dict(version='MEMORY-RUN-CONSUME@2',items=[dict(text='Synthetic preference '+str(i))for i in range(memory_count)])))
                        class Worker:
                            message_context=None;provider=object();lio_memory=None;lio_city_context=None
                            memory_run=None if not memory_count else SimpleNamespace(messages=lambda text:[block,dict(role='user',content=text)])
                            def _registered_stream(self,binding,key,registration,argument,**kwargs):
                                assert registration=='model.lio_intake.9'
                                captured.append(argument)
                                yield json.dumps(wire,ensure_ascii=False)
                            def _event(self,binding,state,kind,value='',**kwargs):
                                events.append((kind,value));return SimpleNamespace(sequence=state.sequence+1)
                        planner=NationalLioPlanning(None,SimpleNamespace(scene_context=lambda *a:None))
                        planner.context=lambda *a:(turns,tuple(dict(message_id='prior-'+str(i))for i in range(count-1)),None)
                        planner.execute(Worker(),SimpleNamespace(message_id='current',run_id='run'),SimpleNamespace(sequence=0),
                                        current,SimpleNamespace(question_day=date(2026,11,14),locale=locale))
                        packet,=captured;messages,_,_,source_index=packet
                        self.assertEqual(source_index,count-1)
                        if memory_count:self.assertEqual(messages[0],block)
                        originals=messages[1:]if memory_count else messages
                        self.assertEqual([m['role']for m in originals],['user']*count)
                        for index,(message,text)in enumerate(zip(originals,texts,strict=True)):
                            self.assertEqual(message['content'].split('\n',1),[
                                'Original traveler source_index='+str(index)+' (quote only the following original text):',text])
                        context=json.loads(next(value.split(':',1)[1]for kind,value in events if value.startswith('lio_planning_context.1:')))
                        self.assertEqual(context['facts']['duration_days']['value'],3)
                        self.assertFalse(any(kind=='registered'for kind,_ in events))
                        self.assertIn(reply,''.join(value for kind,value in events if kind=='text_delta'))

    def test_complete_duration_question_records_a_literal_fact_without_publication_or_model(self):
        for locale,text,quote in (('zh','三天怎么玩','三天'),('en','How should I spend three days?','three days')):
            events=[]
            class Worker:
                def _registered_stream(self,*a,**kw):raise AssertionError('literal clarification does not need a model')
                def _event(self,binding,state,kind,value='',**kw):
                    events.append((kind,value));return SimpleNamespace(sequence=state.sequence+1)
            planner=NationalLioPlanning(None,SimpleNamespace(has_saved_itinerary=lambda b:False))
            turn=PlanningTurn(text,date(2026,11,14))
            planner.context=lambda *a:((turn,),(),None)
            planner.execute(Worker(),SimpleNamespace(message_id='literal-first',message_sequence=1),SimpleNamespace(sequence=0),text,
                            SimpleNamespace(question_day=turn.question_day,locale=locale))
            state=json.loads(next(value.split(':',1)[1]for _,value in events if value.startswith('lio_planning_context.1:')))
            self.assertEqual(state['authority'],'none')
            self.assertEqual(state['facts']['duration_days'],dict(value=3,sources=[dict(message_id='literal-first',quote=quote)]))
            self.assertEqual(state['nonplanning_message_ids'],[])
            self.assertEqual(events[-1][0],'completed')
            follow='帮我规划杭州'if locale=='zh'else'Please plan Hangzhou'
            wire=flow(follow,city='杭州'if locale=='zh'else'Hangzhou',days=None,intent='plan',questions=(),index=1)
            wire.update(version='LIO-planning-intake.8',planning_request_index=1)
            intake,_,facts=parse_flow(json.dumps(wire,ensure_ascii=False),(turn,PlanningTurn(follow,turn.question_day)),
                (dict(message_id='literal-first'),),'follow',state,schema=OptionalIntake)
            self.assertEqual(intake.duration_days,3)
            self.assertEqual(facts['duration_days']['sources'][0]['message_id'],'literal-first')

    def test_literal_shortcut_is_not_a_translation_quotation_negation_or_existing_plan_rule(self):
        for text in ('请把三天怎么玩翻译成英文','“三天怎么玩”','不是三天怎么玩','如果有三天怎么玩',
                     '三天够不够','0天怎么玩','Who are you?','How should we spend three days?'):
            self.assertIsNone(literal_duration_question(text),text)
        self.assertEqual(literal_duration_question('  三天怎么玩？ '),(3,'三天'))

    def test_existing_plan_hold_or_incomplete_history_uses_the_existing_flow(self):
        class ExistingFlow(Exception):pass
        turn=PlanningTurn('三天怎么玩',date(2026,11,14))
        for previous,saved,sequence in ((dict(authority='none',status='discussion',facts={}),False,1),
                                        (None,True,1),(None,False,3)):
            events=[]
            class Worker:
                memory_run=None;message_context=None;provider=object()
                def _registered_stream(self,*a,**kw):raise ExistingFlow()
                def _event(self,*a,**kw):events.append(True)
            planner=NationalLioPlanning(None,SimpleNamespace(has_saved_itinerary=lambda b:saved,scene_context=lambda *a:None))
            planner.context=lambda *a:((turn,),(),previous)
            with self.assertRaises(ExistingFlow):
                planner.execute(Worker(),SimpleNamespace(message_id='literal',message_sequence=sequence),SimpleNamespace(sequence=0),
                                turn.text,SimpleNamespace(question_day=turn.question_day,locale='zh'))
            self.assertEqual(events,[])

    def test_saved_memory_or_physical_role_offsets_still_cannot_be_fact_sources(self):
        text='三天怎么玩';turns=(PlanningTurn(text,date(2026,11,14)),)
        original=flow(text,city=None,days=3,intent='plan',reply='想去哪个城市？',questions=('city',))
        original.update(version='LIO-planning-intake.8',planning_request_index=0,needs_tools=False)
        for source_index,quote in ((1,'三天'),(0,'Synthetic preference')):
            wire=dict(original,field_sources=[dict(field='duration_days',source_index=source_index,quote=quote)])
            with self.assertRaises(InvalidInput):
                parse_flow(json.dumps(wire,ensure_ascii=False),turns,(),'current',None,schema=OptionalIntake)


if __name__=='__main__':unittest.main()
