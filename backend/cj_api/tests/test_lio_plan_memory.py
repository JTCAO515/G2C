"""Remembered preferences in a plan reply (#2010, M-5 server): the filter, the guidance, the used ids; all behind a switch."""
from datetime import date
import json
import os
from types import SimpleNamespace
import unittest
from unittest import mock

from cj_api.local_lio_planning import PlanningTurn, discuss
from cj_message import lio_plan_memory as pm
from cj_run.core import Binding, State
from test_lio_itinerary_preview import DiscussionWorker

PREFIX = pm.MEMORY_PREFIX


def memory_message(*texts):
    items = [dict(subject='self', slot='travel.pace', text=t, kind='preference', extent='long_term', source_id=f's{i}', version=1)
             for i, t in enumerate(texts)]
    return dict(role='user', content=PREFIX + json.dumps(dict(version='MEMORY-RUN-CONSUME@1', items=items), ensure_ascii=False, separators=(',', ':')))


class Shape(unittest.TestCase):
    def test_ordinary_messages_pass_and_a_clean_memory_message_stays(self):
        plain = dict(role='user', content='三天怎么玩')
        out, used = pm.shape([plain, memory_message('我喜欢慢节奏的旅行')], True)
        self.assertTrue(used)
        self.assertEqual(out[0], plain)
        self.assertEqual(json.loads(out[1]['content'][len(PREFIX):])['items'][0]['text'], '我喜欢慢节奏的旅行')

    def test_health_and_religion_items_are_removed_before_the_model_sees_them(self):
        out, used = pm.shape([memory_message('我喜欢慢节奏的旅行', '我对花生过敏', 'I keep kosher', 'I like museums')], True)
        texts = [i['text'] for i in json.loads(out[0]['content'][len(PREFIX):])['items']]
        self.assertEqual(texts, ['我喜欢慢节奏的旅行', 'I like museums'])
        self.assertTrue(used)
        out, used = pm.shape([memory_message('我对花生过敏', '我是穆斯林')], True)
        self.assertEqual((out, used), ([], False))

    def test_when_the_account_may_not_use_its_memory_the_message_is_gone(self):
        out, used = pm.shape([dict(role='user', content='x'), memory_message('我喜欢慢节奏的旅行')], False)
        self.assertEqual((out, used), ([dict(role='user', content='x')], False))

    def test_an_unreadable_memory_message_is_dropped_not_passed(self):
        for content in (PREFIX + 'not json', PREFIX + '{}', PREFIX + '{"items":5}', PREFIX + '{"items":[7,"x"]}'):
            self.assertEqual(pm.shape([dict(role='user', content=content)], True), ([], False))

    def test_a_memory_message_with_non_string_content_is_dropped(self):
        weird = dict(role='user', content=[dict(type='text', text=PREFIX + '{"items":[]}')])
        self.assertEqual(pm.shape([weird, dict(role='user', content='x')], True), ([dict(role='user', content='x')], False))

    def test_the_guidance_does_not_limit_the_places(self):
        self.assertIn('do not assume preferences that are not listed', pm.GUIDANCE)
        self.assertNotIn('use nothing', pm.GUIDANCE)

    def test_the_switch_is_off_by_default_and_strict(self):
        with mock.patch.dict(os.environ):
            os.environ.pop('CJ_LIO_PLAN_MEMORY', None)
            self.assertFalse(pm.enabled())
            os.environ['CJ_LIO_PLAN_MEMORY'] = 'on'
            self.assertTrue(pm.enabled())
            for bad in ('', '1', 'ON'):
                os.environ['CJ_LIO_PLAN_MEMORY'] = bad
                with self.assertRaises(ValueError):
                    pm.enabled()


class MemoryRun:
    def __init__(self, texts):
        self.texts = texts
        items = [SimpleNamespace(command=SimpleNamespace(source_id=f's{i}', item_id=f'mem-{i}', text=t)) for i, t in enumerate(texts)]
        self.snapshot = SimpleNamespace(items=tuple(items), epoch=1)
        self.payload = json.dumps(dict(items=[dict(source_id=f's{i}', text=t) for i, t in enumerate(texts)])).encode()

    def messages(self, text):
        return [memory_message(*self.texts), dict(role='user', content=text)]


class Worker(DiscussionWorker):
    def __init__(self, packet, memory_run, lio_memory=None):
        super().__init__(packet)
        self.memory_run = memory_run
        self.lio_memory = lio_memory
        self.messages = None

    def _registered_stream(self, binding, key, registration, argument, **kwargs):
        self.messages = argument[0]
        return super()._registered_stream(binding, key, registration, argument, **kwargs)


class Discussion(unittest.TestCase):
    TEXTS = ('我喜欢慢节奏的旅行', '我对花生过敏', 'I like museums')

    def setUp(self):
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        for name in ('CJ_LIO_PLAN_MEMORY', 'CJ_LIO_MEMORY_USED', 'CJ_LIO_MEMORY_CONSENT_REQUIRED'):
            os.environ.pop(name, None)

    def run_discussion(self, lio_memory=None, texts=TEXTS):
        binding = Binding('scope', 'conversation', 'generation', 'message', 'run', 1)
        packet = dict(answer='可以这样安排。', days=[dict(day_index=1, activities=[dict(place_name='故宫博物院', verb='visit', period='morning')])])
        worker = Worker(packet, MemoryRun(list(texts)), lio_memory)
        state = discuss(worker, binding, State(binding, status='running'), 'zh', (PlanningTurn('北京一日游', date(2026, 11, 28)),), (),
                        day_count=1, destination='北京')
        return worker, state

    def memory_texts(self, worker):
        memory = [m for m in worker.messages if m['content'].startswith(PREFIX)]
        return [i['text'] for m in memory for i in json.loads(m['content'][len(PREFIX):])['items']]

    def test_off_by_default_the_reply_is_made_exactly_as_before(self):
        worker, state = self.run_discussion()
        self.assertEqual(self.memory_texts(worker), list(self.TEXTS))            # nothing filtered
        self.assertNotIn(pm.GUIDANCE, worker.prompt)
        self.assertFalse(any(e.startswith('lio_memory_used:') for e in state.effects))

    def test_with_the_switch_on_the_model_gets_clean_memory_and_the_guidance(self):
        os.environ['CJ_LIO_PLAN_MEMORY'] = 'on'
        worker, state = self.run_discussion()
        self.assertEqual(self.memory_texts(worker), ['我喜欢慢节奏的旅行', 'I like museums'])
        self.assertIn(pm.GUIDANCE, worker.prompt)

    def test_the_used_ids_exclude_what_was_filtered_and_need_their_own_switch(self):
        os.environ.update(CJ_LIO_PLAN_MEMORY='on', CJ_LIO_MEMORY_USED='on')
        _, state = self.run_discussion()
        used = [e for e in state.effects if e.startswith('lio_memory_used:')]
        self.assertEqual(json.loads(used[0].removeprefix('lio_memory_used:')), dict(item_ids=['mem-0', 'mem-2'], total=2))
        self.assertLess(state.effects.index(used[0]), state.effects.index('lio_planning_discussion'))
        os.environ['CJ_LIO_MEMORY_USED'] = 'off'
        _, state = self.run_discussion()
        self.assertFalse(any(e.startswith('lio_memory_used:') for e in state.effects))

    def test_consent_decides_whether_memory_reaches_the_plan(self):
        os.environ.update(CJ_LIO_PLAN_MEMORY='on', CJ_LIO_MEMORY_CONSENT_REQUIRED='1', CJ_LIO_MEMORY_USED='on')
        for granted, expected in ((True, ['我喜欢慢节奏的旅行', 'I like museums']), (False, [])):
            lio_memory = SimpleNamespace(plan_memory_allowed=lambda scope, granted=granted: granted)
            worker, state = self.run_discussion(lio_memory)
            self.assertEqual(self.memory_texts(worker), expected)
            self.assertEqual(pm.GUIDANCE in worker.prompt, bool(expected))
            self.assertEqual(any(e.startswith('lio_memory_used:') for e in state.effects), bool(expected))
        worker, _ = self.run_discussion(None)                                        # switch on, no consent store: no memory
        self.assertEqual(self.memory_texts(worker), [])

    def test_a_consent_check_that_fails_means_no_memory_but_the_reply_is_still_made(self):
        os.environ.update(CJ_LIO_PLAN_MEMORY='on', CJ_LIO_MEMORY_CONSENT_REQUIRED='1')

        def broken(scope):
            raise RuntimeError('consent store down')
        worker, state = self.run_discussion(SimpleNamespace(plan_memory_allowed=broken))
        self.assertEqual(self.memory_texts(worker), [])
        self.assertEqual(state.status, 'completed')

    def test_two_memory_messages_are_each_filtered(self):
        out, used = pm.shape([memory_message('我对花生过敏'), dict(role='user', content='x'), memory_message('我喜欢慢节奏的旅行')], True)
        self.assertTrue(used)
        self.assertEqual(len(out), 2)
        self.assertEqual(json.loads(out[1]['content'][len(PREFIX):])['items'][0]['text'], '我喜欢慢节奏的旅行')

    def test_nothing_clean_left_means_no_guidance_and_no_used(self):
        os.environ.update(CJ_LIO_PLAN_MEMORY='on', CJ_LIO_MEMORY_USED='on')
        worker, state = self.run_discussion(texts=('我对花生过敏', '我是穆斯林'))
        self.assertEqual(self.memory_texts(worker), [])
        self.assertNotIn(pm.GUIDANCE, worker.prompt)
        self.assertFalse(any(e.startswith('lio_memory_used:') for e in state.effects))


if __name__ == '__main__':
    unittest.main()
