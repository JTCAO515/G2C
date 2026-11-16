"""A rejected draft has a usable answer, without inventing a saved Trip."""
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest

from cj_api.lio_dialogue_routes import _message
from cj_api.local_lio_calendar import LioCalendar
from cj_api.local_lio_planning import PlanningDetails
from cj_message.lio_timeline import TimelineMessage


MARKER='lio_unsaved_plan_answer.1'


class UnsavedAnswer(unittest.TestCase):
    def test_explicit_unsaved_answer_is_readable_but_native_draft_failure_is_preserved(self):
        text='I could not confirm a saved plan. Would you like an unsaved day-by-day suggestion?'
        original=SimpleNamespace(status='completed',text=text,draft_outcome='validation_failed',
            effects=(MARKER,),budget_exhausted_stage='none')
        item=TimelineMessage('draft-message','draft-run',1,'Plan three days in Beijing.','en')
        result=_message(item,original)
        self.assertEqual(result['status'],'completed')
        self.assertEqual(result['answer'],text)
        self.assertIsNone(result['trip'])
        self.assertEqual(original.draft_outcome,'validation_failed')
        for status in ('unknown','failed'):
            original.status=status
            self.assertEqual(_message(item,original)['status'],'failed')
        original.status='completed'
        self.assertEqual(_message(item,original,expired=True)['status'],'failed')
        original.effects=()
        self.assertEqual(_message(item,original)['status'],'failed')

    def test_calendar_draft_rejection_returns_a_next_step_without_retry_or_changing_trip(self):
        for locale in ('zh','en'):
            for retained in (False,True):
                with self.subTest(locale=locale,retained=retained):
                    events=[];drafts=[];old=object()
                    context=(SimpleNamespace(trip=SimpleNamespace(version=3,content=json.dumps(dict(
                        content_version='structured.3',calendar={'state':'undated'},items=[{'id':'locked'}]))))
                        if retained else None)
                    before=deepcopy(context)
                    class Calendar(LioCalendar):
                        def __init__(self):self.database=None
                        def current(self,*args):return context
                        def _publisher(self,*args,**kwargs):return object()
                    class Worker:
                        message_context=None
                        def __init__(self):
                            self.drafts=old
                            self.messages=SimpleNamespace(query=lambda _:SimpleNamespace(raw=b'{"text":"synthetic plan"}'))
                        def _draft(self,binding,state,*args):drafts.append(True);return state,None
                        def _event(self,binding,state,kind,value='',**kwargs):
                            events.append((kind,value));return SimpleNamespace(sequence=state.sequence+1)
                    worker=Worker();binding=SimpleNamespace(message_id='draft-message')
                    Calendar().plan(worker,binding,SimpleNamespace(sequence=0),
                        PlanningDetails('Beijing',{'fixed_items':[]},None,()),locale,day_count=3,start_date=None)
                    body=''.join(value for kind,value in events if kind=='text_delta')
                    self.assertTrue(body.strip())
                    self.assertIn('？'if locale=='zh'else'?',body)
                    self.assertIn(('effect_committed',MARKER),events)
                    self.assertEqual(drafts,[True])
                    self.assertIs(worker.drafts,old)
                    self.assertEqual(context,before)
                    self.assertEqual(events[-1][0],'completed')


if __name__=='__main__':unittest.main()
