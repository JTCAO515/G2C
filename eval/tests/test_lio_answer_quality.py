import json
import unittest

from eval.lio_answer_quality import check_answer, load_cases, main, summarize

# Actual default-dialogue answers observed before #1472 (synthetic test accounts).
BEFORE_CHENGDU = ('成都 · 未保存建议\n第1天：漫步宽窄巷子。\n第2天：参观成都大熊猫繁育研究基地。\n'
                  '第3天：去人民公园休息。\n你想调整哪一天的安排吗？')
BEFORE_TEMPLATE = '你好！准备去哪儿玩？'
GOOD_CHENGDU = '''成都三天按「熊猫—老城—美食」安排，节奏适中。

**第1天：熊猫与老城**
- 上午 7:30–11:00：成都大熊猫繁育研究基地，早去熊猫最活跃。地铁 3 号线到熊猫大道站，再换接驳车；门票约 55 元，需提前在官方小程序用护照实名预约。
- 下午：宽窄巷子逛老院子，喝杯盖碗茶。
- 晚上：玉林路一带吃火锅，人均 100–150 元，怕辣点鸳鸯锅。

**第2天：三国与诗人**
- 上午：武侯祠和锦里，步行可达。
- 下午：杜甫草堂，打车约 15 分钟。
- 晚上：春熙路、太古里，晚饭试试串串。

**第3天：慢下来**
- 上午：人民公园鹤鸣茶社喝茶、看掏耳朵。
- 下午：文殊院，素斋和担担面都在附近。
- 晚上：九眼桥看夜景。

提示：熊猫基地周一不闭馆但人多，周末尽量早到。'''
GOOD_EMERGENCY_EN = '''Call 120 now (ambulance) — say 救命 and give your address.

1. Check whether your friend is breathing; if not, start CPR.
2. Share your location: ask a shop staff member to tell the dispatcher the address in Chinese.
3. Stay with them until help arrives.'''


class AnswerQualityTests(unittest.TestCase):
    def setUp(self):
        self.cases = {case['id']: case for case in load_cases()}

    def test_cases_cover_both_languages_and_scenarios(self):
        cases = list(self.cases.values())
        self.assertGreaterEqual(len(cases), 20)
        for locale in ('zh', 'en'):
            self.assertGreaterEqual(sum(c['locale'] == locale for c in cases), 9)
        self.assertEqual({c['scenario'] for c in cases},
                         {'planning', 'practical', 'recommendation', 'emergency', 'chat', 'greeting', 'followup'})

    def test_flat_day_lines_fail_detail_and_periods(self):
        row = check_answer(self.cases['plan-chengdu-followup-zh'], BEFORE_CHENGDU)
        self.assertFalse(row['passed'])
        self.assertTrue(row['checks']['every_day'])
        self.assertFalse(row['checks']['day_periods'])
        self.assertFalse(row['checks']['detail_length'])

    def test_detailed_day_plan_passes(self):
        row = check_answer(self.cases['plan-chengdu-followup-zh'], GOOD_CHENGDU)
        self.assertTrue(row['passed'], row)

    def test_template_opening_fails_outside_greeting(self):
        row = check_answer(self.cases['followup-hangzhou-zh'], BEFORE_TEMPLATE)
        self.assertFalse(row['checks']['no_template'])
        self.assertFalse(row['checks']['uses_context'])
        self.assertTrue(check_answer(self.cases['greeting-zh'], BEFORE_TEMPLATE)['passed'])

    def test_emergency_number_must_lead(self):
        case = self.cases['collapse-en']
        self.assertTrue(check_answer(case, GOOD_EMERGENCY_EN)['checks']['emergency_first'])
        late = 'Stay calm and check breathing. Then call 120 and give your address.'
        self.assertFalse(check_answer(case, late)['checks']['emergency_first'])

    def test_red_lines_and_test_leaks_fail(self):
        case = self.cases['tipping-en']
        self.assertFalse(check_answer(case, 'No tipping. run_id abc')['checks']['red_line'])
        self.assertFalse(check_answer(case, 'This is synthetic data.')['checks']['red_line'])

    def test_summary_and_cli(self):
        answers = {'plan-chengdu-followup-zh': GOOD_CHENGDU, 'greeting-zh': '你好！今天想去哪儿逛？'}
        result = summarize(list(self.cases.values()), answers)
        self.assertEqual((result['answered'], result['passed_cases']), (2, 2))
        with self.assertRaises(ValueError):
            check_answer(self.cases['greeting-zh'], ' ')

    def test_cli_lists_cases(self):
        self.assertEqual(main(['cases']), 0)


if __name__ == '__main__':
    unittest.main()
