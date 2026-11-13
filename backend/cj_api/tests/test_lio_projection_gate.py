"""Projection orchestration; native custody is exercised in lio_projection_pg."""
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from cj_api.lio_dialogue_routes import _timeline
from cj_message.lio_timeline import TimelinePage,TimelineMessage


class ProjectionGate(unittest.TestCase):
    def exercise(self,status,*,memory=True):
        item=TimelineMessage('original-message','original-run',1,'Synthetic question','en')
        page=TimelinePage('conversation','generation',(item,),None)
        state=SimpleNamespace(status=status,effects=frozenset())
        events=[];counts=[]
        class Context:
            scope='original-owner'
            active=False
            def lio_timeline(self,*args,**kwargs):return page
            def with_lio_timeline_projection(self,operation):
                events.append('protected');self.active=True
                try:return operation()
                finally:self.active=False
        context=Context()
        class Boundary:
            def with_history_context(self,token,operation):return operation(context)
        class Repository:
            def lio_timeline(self,bindings):
                counts.append(len(bindings))
                if len(counts)>1:raise AssertionError('gate and compose must not resample RUN state')
                return [(state,False)]
        class Memory:
            def project(self,ctx,*args):
                if not ctx.active:raise AssertionError('completed Memory read lacks original custody')
                events.append('memory');return {'tags':[]}
        with patch('cj_api.lio_dialogue_routes._message',side_effect=lambda *args,**kwargs:dict(status=status)):
            response=_timeline(Boundary(),lambda _:Repository(),None,Memory()if memory else None,
                               'synthetic','conversation',None,True)
        self.assertEqual(response.status_code,200)
        self.assertEqual(json.loads(response.body)['messages'],[dict(status=status)])
        self.assertEqual(counts,[1]);return events

    def test_noncompleted_pages_do_not_gain_original_lock_or_memory_projection(self):
        for status in ('queued','running','failed','unknown','cancelled'):
            with self.subTest(status=status):self.assertEqual(self.exercise(status),[])

    def test_completed_memory_uses_one_protected_frame_and_same_run_snapshot(self):
        self.assertEqual(self.exercise('completed'),['protected','memory'])

    def test_without_memory_even_completed_page_keeps_original_path(self):
        self.assertEqual(self.exercise('completed',memory=False),[])
