"""Code-owned lower declarations, without changing original run configuration."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from cj_usage.registered_exit import RegisteredExit,Registration,InvocationInput
from cj_usage.core import Config
from cj_usage.metered_exit import BudgetUnknown


class ToolBounds(unittest.TestCase):
    def prepare(self,limit=None,*,kind='tool',final=False):
        cfg=Config('provider_call',800,0,1000,24,12,65536,600)
        original=InvocationInput(b'original-input',lambda:lambda:iter(('result',)),tool_output_limit=limit)
        exit=RegisteredExit(cfg,None,clock=lambda:100,output_limits=dict(model=12000,tool=48000,memory=12000),
            environment='local',registrations={'tool.bound.1':Registration(kind,lambda argument:original)})
        captured=[]
        def create(binding,key,registration,kind,raw,output_limit):
            captured.append((raw,output_limit));return SimpleNamespace(binding=binding)
        with patch('cj_usage.registered_exit.OperationStore')as store:
            store.return_value.create.side_effect=create
            exit.prepare_operation(SimpleNamespace(valid=lambda _:True),object(),'op','tool.bound.1',{},stage='answer',reserve_final_model=final)
        return captured

    def test_default_preserves_original_input_and_48000(self):
        self.assertEqual(self.prepare(),[(b'original-input',48000)])
    def test_smaller_declaration_is_recorded_in_original_command(self):
        self.assertEqual(self.prepare(8192),[(b'original-input',8192)])
    def test_invalid_declarations_fail_before_materialization(self):
        for value in (True,0,-1,1.5,'8192'):
            with self.subTest(value=value),self.assertRaises(ValueError):self.prepare(value)
    def test_no_increase_above_original_profile(self):
        with self.assertRaises(BudgetUnknown):self.prepare(48001)
    def test_models_and_memory_cannot_select_tool_bound(self):
        for kind in ('model','memory'):
            with self.subTest(kind=kind),self.assertRaises(BudgetUnknown):self.prepare(8192,kind=kind)
