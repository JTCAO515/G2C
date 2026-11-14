from dataclasses import replace
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

from cj_agent.provider import M4_BASE, M4_MODEL
from cj_api.runtime_actor import ActorSpecification, ActorInput, actor_registration
from cj_run.core import Binding
from cj_strict_json import compact
from cj_usage.metered_exit import BudgetUnknown
from cj_usage.registered_exit import InvocationInput


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))


class ActorTest(unittest.TestCase):
    def setUp(self):
        from eval.lio_simulated_user.core import SIMULATOR_SYSTEM, actor_output_schema
        dataset = (ROOT/'eval/lio_simulated_user/profiles.v1.json').read_bytes()
        self.profile = json.loads(dataset)['profiles'][0]
        self.model = dict(endpoint=M4_BASE, id=M4_MODEL, parameters=dict(stream=True,
            stream_options={'include_usage': True}, enable_thinking=False,
            max_tokens=1024, response_format={'type': 'json_object'}))
        card = compact(dict(code_sha='a'*40, image_digest='sha256:'+'b'*64, model=self.model))
        self.spec = ActorSpecification(dataset, SIMULATOR_SYSTEM,
            compact(actor_output_schema(), sort_keys=True), card)
        self.history = [dict(speaker='user', text=self.profile['opening']),
                        dict(speaker='assistant', text='What are your interests?')]
        messages = [dict(role='system', content=SIMULATOR_SYSTEM), dict(role='user',
            content=compact(dict(profile=self.profile, history=self.history, attempt=1)).decode())]
        self.binding = Binding('same-owner', 'actor-cid', 'actor-generation', 'actor-mid', 'actor-run', 1)
        source = dict(scope_sha256=sha256(b'same-owner').hexdigest(), conversation_id='dut-cid',
            generation='dut-generation', message_id='dut-mid', run_id='dut-run', input_sha256='c'*64,
            observer_ref='original-dut-observation', answer_sha256=sha256(self.history[-1]['text'].encode()).hexdigest(),
            history_sha256=sha256(compact(self.history, sort_keys=True)).hexdigest())
        self.checks = []
        self.argument = ActorInput(self.binding, self.profile['id'], 1, 1, compact(messages),
            compact(source), self.spec, lambda: self.checks.append('original-source'))

    def test_fixed_inputs_and_choice_schema(self):
        self.assertEqual(self.spec.decode_choice(b'{"answers":["pace"],"action":"continue"}'),
                         dict(answers=['pace'], action='continue'))
        for raw in (b'{"answers":[],"action":"continue","extra":0}',
                    b'{"answers":["pace","pace"],"action":"continue"}',
                    b'{"answers":["unknown"],"action":"continue"}',
                    b'{"answers":[],"action":"continue","action":"direct"}',
                    b'{"answers":[NaN],"action":"continue"}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):self.spec.decode_choice(raw)
        with self.assertRaises(ValueError):replace(self.spec, system='Changed system')

    def test_hidden_input_is_only_the_actor_operation(self):
        inputs = []
        config = SimpleNamespace(base_url=M4_BASE, model_id=M4_MODEL, max_output_tokens=1536)
        def prepare(value):
            inputs.append(value)
            return InvocationInput(b'inner', lambda: None,
                bind_operation=lambda operation, guard: lambda: guard())
        tools = SimpleNamespace(services=SimpleNamespace(model=SimpleNamespace(config=config)), _model_input=prepare)
        registration = actor_registration(tools, self.spec)
        prepared = registration.prepare_input(self.argument)
        self.assertEqual(registration.kind, 'model')
        source = json.loads(prepared.original_bytes)
        self.assertEqual(source['purpose'], 'simulator_actor')
        self.assertEqual(source['dut_source']['run_id'], 'dut-run')
        self.assertEqual(inputs[0][1], self.spec.system)
        self.assertEqual(inputs[0][2], tools.services.model)
        self.assertNotIn('Memory', inputs[0][1])
        self.assertIn('hidden_answers', inputs[0][0][0]['content'])
        self.assertNotIn('hidden_answers', compact(self.history).decode())
        operation = SimpleNamespace(binding=self.binding)
        stream = prepared.bind_operation(operation, lambda: True)
        self.assertTrue(stream())
        self.assertEqual(len(self.checks), 3)
        with self.assertRaises(BudgetUnknown):
            prepared.bind_operation(SimpleNamespace(binding=replace(self.binding, run_id='other')), lambda: True)

    def test_source_owner_history_and_dut_cid_are_not_caller_defaults(self):
        source = json.loads(self.argument.source)
        for key, value in (('scope_sha256', 'f'*64), ('conversation_id', self.binding.conversation_id),
                           ('run_id', self.binding.run_id), ('answer_sha256', 'f'*64),
                           ('history_sha256', 'f'*64)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                replace(self.argument, source=compact({**source, key: value}))
        with self.assertRaises(ValueError):replace(self.argument, round=2)
        with self.assertRaises(ValueError):replace(self.argument, attempt=True)

    def test_changed_actual_model_is_rejected_before_preparation(self):
        config = SimpleNamespace(base_url=M4_BASE, model_id='other-model', max_output_tokens=1536)
        tools = SimpleNamespace(services=SimpleNamespace(model=SimpleNamespace(config=config)))
        with self.assertRaises(ValueError):actor_registration(tools, self.spec)


if __name__ == '__main__':unittest.main()
