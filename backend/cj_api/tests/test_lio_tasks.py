"""W2-8 (#1738): tasks[] from one extra call, validated in code; at most one question."""
import json
import os
import unittest
from unittest.mock import patch

from cj_api import lio_tasks
from cj_api.lio_tasks import QUESTION_ORDER, check_plan, guidance_text, skip_reason, tasks_enabled
from cj_api.scene_pack_config import Switches


def plan(*tasks, index=0):
    return json.dumps(dict(version='LIO-tasks.1', current_source_index=index, tasks=list(tasks)), ensure_ascii=False)


def task(pack, topic, quote, *, flow=None, missing=(), source_index=0):
    return dict(pack=pack, topic=topic, flow=flow, missing=list(missing),
                source=dict(source_index=source_index, quote=quote))


def switches(business=False, guangzhou=False):
    return Switches(scene_packs={'travel': True, 'business': business},
                    cities={'business': {'guangzhou': guangzhou}}, human_service=False, payments=False, medical=False)


class Tasks(unittest.TestCase):
    def test_switch_is_off_by_default_and_accepts_only_zero_or_one(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('CJ_LIO_TASKS', None)
            self.assertFalse(tasks_enabled())
        with patch.dict(os.environ, {'CJ_LIO_TASKS': '1'}):
            self.assertTrue(tasks_enabled())
        with patch.dict(os.environ, {'CJ_LIO_TASKS': 'on'}), self.assertRaises(ValueError):
            tasks_enabled()

    def test_short_single_intent_follow_ups_and_plan_requests_skip_the_call(self):
        # Coordinator condition 2: the skip rules are tested.
        for text, reason in (('好的', 'short_reply'), ('谢谢！', 'short_reply'), ('ok', 'short_reply'),
                             ('第二个怎么去', 'short_single'), ('How far is it?', 'short_single'),
                             ('帮我规划北京三天的行程', 'plan_request'), ('Plan 3 days in Chengdu for me please', 'plan_request')):
            with self.subTest(text=text):
                self.assertEqual(skip_reason(text), reason)
        self.assertEqual(skip_reason('什么都行', chip=True), 'chip')
        for text in ('我下周去广州参加广交会，顺便想去长隆玩，需要准备什么？',
                     'How do I pay in China, and can I use Google there?', '支付宝怎么开通，另外地铁怎么坐'):
            with self.subTest(text=text):
                self.assertIsNone(skip_reason(text))

    def test_tasks_must_quote_the_travelers_words(self):
        text = '支付宝怎么开通，另外地铁怎么坐'
        with patch.object(lio_tasks, 'load_switches', return_value=switches()):
            guidance = check_plan(plan(task('travel', '开通支付宝', '支付宝怎么开通'),
                                       task('travel', '编造的任务', '没有这句话')), [text])
        self.assertEqual([row.topic for row in guidance.tasks], ['开通支付宝'])
        with patch.object(lio_tasks, 'load_switches', return_value=switches()):
            self.assertIsNone(check_plan(plan(task('travel', 'x', '没有这句话')), [text]))
            self.assertIsNone(check_plan('{"version":"wrong"}', [text]))
            self.assertIsNone(check_plan(plan(task('travel', '开通支付宝', '支付宝怎么开通'), index=1), [text]))

    def test_business_tasks_need_the_pack_and_a_named_city_switched_on(self):
        text = '我下周去广州参加广交会，顺便想去长隆玩'
        raw = plan(task('business', '广交会参展准备', '我下周去广州参加广交会', flow='trade-fair-preparation', missing=['dates']),
                   task('travel', '长隆游玩', '想去长隆玩'))
        for state, expected_pack, has_flow in ((switches(), 'travel', False), (switches(business=True), 'travel', False),
                                               (switches(business=True, guangzhou=True), 'business', True)):
            with self.subTest(state=state):
                with patch.object(lio_tasks, 'load_switches', return_value=state):
                    guidance = check_plan(raw, [text])
                self.assertEqual(guidance.tasks[0].pack, expected_pack)
                self.assertEqual(guidance.tasks[0].flow is not None, has_flow)
        with patch.object(lio_tasks, 'load_switches', return_value=switches(business=True, guangzhou=True)):
            elsewhere = check_plan(plan(task('business', '上海展会', '去上海参展', flow='trade-fair-preparation')), ['去上海参展'])
        self.assertEqual((elsewhere.tasks[0].pack, elsewhere.tasks[0].flow), ('travel', None))

    def test_at_most_one_question_chosen_in_code(self):
        text = '支付宝怎么开通，另外酒店附近有什么好吃的'
        with patch.object(lio_tasks, 'load_switches', return_value=switches()):
            guidance = check_plan(plan(task('travel', '开通支付宝', '支付宝怎么开通', missing=['nationality']),
                                       task('travel', '附近美食', '酒店附近有什么好吃的', missing=['hotel', 'city'])), [text])
        self.assertEqual(guidance.question, (1, 'city'))
        self.assertEqual(QUESTION_ORDER[0], 'city')
        prompt = guidance_text(guidance, 'zh')
        self.assertIn('1. [travel] 开通支付宝.', prompt)
        self.assertIn('Ask exactly one question, at the end, about task 2: 你要去哪个城市？', prompt)
        self.assertEqual(prompt.count('Ask exactly one question'), 1)
        with patch.object(lio_tasks, 'load_switches', return_value=switches()):
            none = check_plan(plan(task('travel', '开通支付宝', '支付宝怎么开通')), [text])
        self.assertIn('Do not ask the traveler any question.', guidance_text(none, 'en'))
        self.assertEqual(guidance_text(None, 'zh'), '')

    def test_flow_steps_from_the_pack_are_quoted_in_the_guidance(self):
        text = '我下周去广州参加广交会'
        with patch.object(lio_tasks, 'load_switches', return_value=switches(business=True, guangzhou=True)):
            guidance = check_plan(plan(task('business', '广交会参展准备', text, flow='trade-fair-preparation')), [text])
        self.assertIn('Useful steps: 按主办方信息确认展期和场馆地址。', guidance_text(guidance, 'zh'))

    def test_pending_reads_are_taken_once(self):
        lio_tasks.put_pending('run-x', 'reader')
        self.assertEqual(lio_tasks.take_pending('run-x'), 'reader')
        self.assertIsNone(lio_tasks.take_pending('run-x'))


if __name__ == '__main__':
    unittest.main()
