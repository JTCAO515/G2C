"""#1475: a detailed day-by-day answer is shown when it matches the structured days."""
from dataclasses import replace
from datetime import date
import json
import unittest

from cj_api.local_lio_planning import PlanningTurn, discuss, read_itinerary_preview
from cj_run.core import Binding, State


class Worker:
    memory_run = None
    message_context = None
    provider = None

    def __init__(self, packet):
        self.packet, self.prompt = packet, None

    def _registered_stream(self, binding, key, registration, argument, **kwargs):
        self.prompt = argument[1]
        return iter((json.dumps(self.packet, ensure_ascii=False),))

    def _event(self, binding, state, kind, value=''):
        if kind == 'text_delta':
            return replace(state, text=state.text + value)
        if kind == 'effect_committed':
            return replace(state, effects=(*state.effects, value))
        return replace(state, status=kind)


DAYS = [dict(day_index=1, activities=[dict(place_name='成都大熊猫繁育研究基地', verb='visit', period='morning'),
                                      dict(place_name='宽窄巷子', verb='walk', period='afternoon')]),
        dict(day_index=2, activities=[dict(place_name='武侯祠', verb='visit', period='morning'),
                                      dict(place_name='杜甫草堂', verb='visit', period='afternoon')])]
RICH = ('**第1天：参观成都大熊猫繁育研究基地，漫步宽窄巷子**\n'
        '- 上午 7:30：成都大熊猫繁育研究基地，地铁 3 号线到熊猫大道站；门票约 55 元，用护照在官方渠道预约。\n'
        '- 下午：宽窄巷子喝盖碗茶，打车约 20 分钟。\n'
        '- 晚上：玉林路吃火锅，人均约 100–150 元。\n\n'
        '**第2天：参观武侯祠和杜甫草堂**\n'
        '- 上午：武侯祠，旁边就是锦里。\n'
        '- 下午：杜甫草堂，打车约 15 分钟。\n\n'
        '想把第2天换成更轻松的安排吗？')
RICH_EN = ('**Day 1: Visit the Panda Base and walk Kuanzhai Alley**\n'
           '- Morning: Chengdu Research Base of Giant Panda Breeding (**成都大熊猫繁育研究基地**), Metro Line 3.\n'
           '- Afternoon: Kuanzhai Alley (**宽窄巷子**) for tea.\n\n'
           '**Day 2: Visit Wuhou Shrine and Du Fu Thatched Cottage**\n'
           '- Morning: Wuhou Shrine (**武侯祠**).\n'
           '- Afternoon: Du Fu Thatched Cottage (**杜甫草堂**), about 15 minutes by taxi.')


class PlanDetail(unittest.TestCase):
    def discuss(self, packet, locale='zh', question='成都两天'):
        binding = Binding('scope', 'conversation', 'generation', 'message', 'run', 1)
        worker = Worker(packet)
        state = discuss(worker, binding, State(binding, status='running'), locale,
                        (PlanningTurn(question, date(2026, 11, 24)),), (), day_count=2,
                        destination='成都' if locale == 'zh' else 'Chengdu')
        return worker, state

    def test_detailed_answer_matching_days_is_shown_with_its_preview(self):
        for locale, answer in (('zh', RICH), ('en', RICH_EN)):
            with self.subTest(locale=locale):
                _, state = self.discuss(dict(answer=answer, days=DAYS, follow_up=None), locale)
                self.assertTrue(state.text.endswith(answer))
                self.assertEqual([[a['place_name'] for a in d['activities']]
                                  for d in read_itinerary_preview(state, locale)['days']],
                                 [['成都大熊猫繁育研究基地', '宽窄巷子'], ['武侯祠', '杜甫草堂']])

    def test_answer_that_drops_a_place_or_day_falls_back_to_rendered_days(self):
        for answer in (RICH.replace('杜甫草堂', '青城山'), RICH.split('**第2天')[0],
                       RICH.replace('第1天', '第2天', 1)):
            with self.subTest(answer=answer[:30]):
                _, state = self.discuss(dict(answer=answer, days=DAYS, follow_up=None))
                self.assertIn('第1天：上午参观成都大熊猫繁育研究基地，下午漫步宽窄巷子。', state.text)
                self.assertNotIn('玉林路', state.text)
                self.assertIsNotNone(read_itinerary_preview(state, 'zh'))

    def test_answer_with_internal_text_falls_back(self):
        _, state = self.discuss(dict(answer=RICH + '\nrun_id', days=DAYS, follow_up=None))
        self.assertNotIn('run_id', state.text)
        self.assertIn('第1天：上午参观', state.text)

    def test_display_wording_is_normalized_instead_of_hiding_the_detail(self):
        answer = RICH.replace('用护照在官方渠道预约', '用护照在官方渠道查询并核实预约')
        _, state = self.discuss(dict(answer=answer, days=DAYS, follow_up=None))
        self.assertIn('用护照在官方渠道查看并确认预约', state.text)
        self.assertIn('玉林路', state.text)
        self.assertIsNotNone(read_itinerary_preview(state, 'zh'))

    def test_non_idempotent_display_rewrite_keeps_the_flat_lines_and_preview(self):
        # A technical host glued to an identifier only becomes visible as internal after one rewrite.
        _, state = self.discuss(dict(answer=RICH + '\nrestapi.amap.comrun_id', days=DAYS, follow_up=None))
        self.assertIn('第1天：上午参观', state.text)
        self.assertNotIn('run_id', state.text)
        self.assertIsNotNone(read_itinerary_preview(state, 'zh'))

    def test_fallback_is_logged_with_a_fixed_reason(self):
        with self.assertLogs('cj_usage.audit', level='INFO') as logs:
            self.discuss(dict(answer=RICH.replace('杜甫草堂', '青城山'), days=DAYS, follow_up=None))
        self.assertTrue(any('LIO_DISCUSSION_DETAIL_WITHHELD' in line and 'reason=day_activity' in line
                            for line in logs.output), logs.output)
        self.assertFalse(any('青城山' in line for line in logs.output))

    def test_prompt_asks_for_periods_transport_and_tips_not_one_line(self):
        worker, _ = self.discuss(dict(answer=RICH, days=DAYS, follow_up=None))
        for clause in ('morning, afternoon and evening', 'how to get there',
                       'Use exactly the same full place names in the answer and in days',
                       'The answer is the full day-by-day plan shown to the traveler'):
            with self.subTest(clause=clause):
                self.assertIn(clause, worker.prompt)
        for clause in ('Use one concise line per day', 'Keep the answer a concise, complete plain-text fallback'):
            with self.subTest(clause=clause):
                self.assertNotIn(clause, worker.prompt)


if __name__ == '__main__':
    unittest.main()
