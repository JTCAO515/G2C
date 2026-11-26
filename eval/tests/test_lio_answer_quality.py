import json
import unittest

from eval.lio_answer_quality import ONE_SCREEN, check_answer, load_cases, main, summarize

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


# One-screen structure (JT 2026-11-25 "全选 A", strategy/lio-answer-design.md): examples
# taken from the approved option A and the current long option B.
ONE_SCREEN_PAY_EN = dict(text="""Link your Visa to Alipay (**支付宝**) before you fly. It works almost everywhere, from taxis to street stalls.

1. Download Alipay and sign up with your own phone number.
2. Add your Visa and verify with your passport.
3. To pay, scan the shop's QR code or show yours.

Keep a little cash as backup. A few small shops can't take foreign cards.""",
    actions=['Open the payment setup guide'], chips=['What if it is declined?', 'Do I need WeChat too?'])
LONG_PAY_EN = """Foreign visitors can pay by phone in China once a card is linked. Here is the full setup.

1. **Download and register**: Get Alipay (**支付宝**) from your app store and sign up with your home phone number.
2. **Verify your identity**: Upload your passport photo page and complete the face check.
3. **Link your card**: Add your Visa as an international card. Mastercard also works.
4. **Pay by scanning**: Tap Scan, scan the merchant's QR code, then enter the amount.
5. **Pay by showing**: Tap Pay/Receive and let the cashier scan your code.
6. **Set up Weixin Pay too** (**微信支付**): Some shops only show a WeChat code, so a second option helps.
7. **Carry backup cash**: Useful at small stalls and markets. Large hotels and malls often take foreign cards directly.
8. **If a payment fails**: Check that your bank allows international payments, then try the other app. WeChat Pay works the same way.

Which cities are you visiting? I can tell you what is common there."""
ONE_SCREEN_PLAN_ZH = dict(text="""按第一次来、节奏轻松排了三天。先按 2 位成人、日期待定。

**第 1 天** 皇城中轴：天安门广场、故宫、景山看日落
**第 2 天** 慕田峪长城，回城在胡同里吃晚饭
**第 3 天** 上午天坛，午饭后颐和园

故宫要用护照实名预约，最多提前 7 天，周一闭馆。""",
    # The design example's 「放票时提醒我」 (remind_tickets) is not in the first whitelist.
    actions=[], chips=['再轻松点', '多加美食', '我有具体日期'])


class OneScreenTests(unittest.TestCase):
    def setUp(self):
        self.cases = {case['id']: case for case in load_cases()}

    def test_option_a_answer_fits_one_screen_answers_first_and_gives_an_action(self):
        row = check_answer(self.cases['visa-card-en'], ONE_SCREEN_PAY_EN, profile=ONE_SCREEN)
        for name in ('screen_budget', 'first_answer', 'has_action', 'red_line', 'no_template'):
            self.assertTrue(row['checks'][name], (name, row))
        self.assertNotIn('detail_length', row['checks'])
        plan = check_answer(self.cases['plan-beijing-3d-zh'], ONE_SCREEN_PLAN_ZH, profile=ONE_SCREEN)
        for name in ('screen_budget', 'first_answer', 'has_action', 'every_day'):
            self.assertTrue(plan['checks'][name], (name, plan))
        # One line per day is the approved shape; morning/afternoon periods are not required.
        self.assertNotIn('day_periods', plan['checks'])

    def test_long_list_fails_budget_and_late_elements_do_not_count(self):
        case = self.cases['visa-card-en']
        row = check_answer(case, LONG_PAY_EN, profile=ONE_SCREEN)
        self.assertFalse(row['checks']['screen_budget'])
        self.assertFalse(row['checks']['has_action'])
        # "WeChat Pay" only appears after the first screen of text.
        self.assertFalse(row['checks']['element_2'])
        self.assertTrue(check_answer(case, LONG_PAY_EN)['checks']['element_2'])
        self.assertLess(row['budget_units'], row['units'])

    def test_first_sentence_must_answer_not_ask_or_preface(self):
        case = self.cases['tipping-en']
        for text in ('Great question! Tipping is not expected in China.', 'Do you mean restaurants or hotels? Tipping is not expected.',
                     'Hi! Tipping is not expected in China.', "I'm Lio. Tipping is not expected."):
            with self.subTest(text=text):
                self.assertFalse(check_answer(case, dict(text=text, actions=['Open tipping guide']), profile=ONE_SCREEN)['checks']['first_answer'])
        good = dict(text='No, tipping is not expected in China. High-end hotels may add a service charge.', actions=['Open etiquette tips'])
        self.assertTrue(check_answer(case, good, profile=ONE_SCREEN)['checks']['first_answer'])

    def test_action_counts_follow_the_design(self):
        case = self.cases['alipay-zh']
        def has_action(actions, chips):
            return check_answer(case, dict(text='先把 Visa 卡绑到支付宝，用护照验证后扫码付款。', actions=actions, chips=chips),
                                profile=ONE_SCREEN)['checks']['has_action']
        self.assertTrue(has_action(['打开支付开通指南'], ['付不了怎么办']))
        self.assertTrue(has_action(['打开支付开通指南', '加入待办'], []))
        self.assertFalse(has_action([], ['付不了怎么办', '还要装微信吗']))
        self.assertFalse(has_action(['a', 'b', 'c'], []))
        self.assertFalse(has_action(['打开支付开通指南'], ['1', '2', '3', '4', '5']))
        self.assertFalse(has_action([' '], []))
        # "Where to go" answers may end with tappable follow-ups only (option A of the design).
        where = check_answer(self.cases['food-chengdu-zh'], dict(text='成都先吃火锅。', chips=['火锅', '小吃', '都想试']), profile=ONE_SCREEN)
        self.assertTrue(where['checks']['has_action'])

    def test_action_required_only_where_the_first_whitelist_has_one(self):
        # First whitelist (S contract, A confirmed 2026-11-25): open_guide payment-setup /
        # payment-troubleshooting / taxi, and view_trip for a saved trip. Elsewhere 2-3 chips suffice.
        from eval.lio_answer_quality import V1_ACTION_CASES
        # Default-dialogue plans are unsaved suggestions, so view_trip has no saved trip to open (#1638 review).
        self.assertEqual(V1_ACTION_CASES, {'alipay-zh', 'visa-card-en', 'taxi-foreigner-zh', 'uber-taxi-en'})
        def has_action(case_id, actions, chips):
            return check_answer(self.cases[case_id], dict(text='先坐机场线到东直门。', actions=actions, chips=chips),
                                profile=ONE_SCREEN)['checks']['has_action']
        for case_id in ('metro-airport-zh', 'collapse-en', 'tipping-en', 'followup-hangzhou-zh', 'plan-beijing-3d-zh'):
            with self.subTest(case=case_id):
                self.assertTrue(has_action(case_id, [], ['票价多少？', '要换乘几次？']))
                self.assertFalse(has_action(case_id, [], ['票价多少？']))
                # No first-version button exists here: a button alone does not replace the follow-ups.
                self.assertFalse(has_action(case_id, ['Open guide'], []))
        for case_id in sorted(V1_ACTION_CASES):
            with self.subTest(case=case_id):
                self.assertFalse(has_action(case_id, [], ['1', '2', '3']))
                self.assertTrue(has_action(case_id, ['Open guide'], ['1', '2']))

    def test_review_followups_chip_cap_filler_boundaries_and_pinyin_prefix(self):
        # #1638 review + S contract (at most 3 chips per answer, 2026-11-25).
        from eval.lio_answer_quality import _within_budget
        case = self.cases['alipay-zh']
        def has_action(actions, chips, case=case):
            return check_answer(case, dict(text='先把 Visa 卡绑到支付宝，用护照验证后扫码付款。', actions=actions, chips=chips),
                                profile=ONE_SCREEN)['checks']['has_action']
        self.assertTrue(has_action(['打开支付开通指南'], ['1', '2', '3']))
        self.assertFalse(has_action(['打开支付开通指南'], ['1', '2', '3', '4']))
        self.assertFalse(has_action([], ['1', '2', '3', '4'], self.cases['food-chengdu-zh']))
        tipping = self.cases['tipping-en']
        def first(text, case=tipping):
            return check_answer(case, dict(text=text, actions=['Open etiquette tips']), profile=ONE_SCREEN)['checks']['first_answer']
        for text in ('Of course not, tipping is not expected.', 'Hi-speed trains have no tipping either; tipping is not expected.',
                     'Sure-footed hikers tip guides, but tipping is not expected.'):
            with self.subTest(passes=text):self.assertTrue(first(text))
        for text in ('当然可以，把 Visa 绑到支付宝就能扫码付。', '没问题，外国游客可以直接用支付宝。', '你好像需要先绑卡，再扫码付款。',
                     '嗨皮的地方先放一放，先把 Visa 绑到支付宝。'):
            with self.subTest(passes=text):self.assertTrue(first(text, case))
        # Re-review of 15110e8d: a greeting followed by any word is still a greeting.
        for text in ('Sure! Tipping is not expected.', 'Absolutely. Tipping is not expected.', 'Of course! No tipping.',
                     'Hi there, tipping is not expected.', 'Hello there! Tipping is not expected.',
                     'Hi everyone, tipping is not expected.', 'Hello traveler, tipping is not expected.', 'Hi Sarah, no tipping.'):
            with self.subTest(fails=text):self.assertFalse(first(text))
        for text in ('当然可以！把 Visa 绑到支付宝。', '没问题。先绑卡。'):
            with self.subTest(fails=text):self.assertFalse(first(text, case))
        # Pinyin annotations only stop counting once closed; the cut keeps the longest fitting prefix.
        self.assertEqual(_within_budget('Try Peking duck (烤鸭 kao ya) today and tomorrow', 'en', 4),
                         'Try Peking duck (烤鸭 kao ya) today')
        self.assertEqual(_within_budget('成都火锅很辣', 'zh', 4), '成都火锅')

    def test_default_profile_still_rejects_non_text_answers_up_front(self):
        import tempfile, os
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'answers.json')
            with open(path, 'w') as handle:
                json.dump({'not-a-case': {'text': 'x'}}, handle)
            with self.assertRaises(SystemExit):
                main(['score', path])

    def test_greeting_and_emergency_budgets(self):
        greeting = check_answer(self.cases['greeting-zh'], '你好！准备去哪儿玩？', profile=ONE_SCREEN)
        self.assertTrue(greeting['passed'], greeting)
        self.assertNotIn('has_action', greeting['checks'])
        long_emergency = dict(text=GOOD_EMERGENCY_EN + '\n' + ' '.join(['Keep them warm and stay on the line.'] * 30),
                              actions=['Call 120'])
        row = check_answer(self.cases['collapse-en'], long_emergency, profile=ONE_SCREEN)
        self.assertTrue(row['checks']['screen_budget'])
        self.assertTrue(row['checks']['emergency_first'])

    def test_text_only_answers_still_score_and_cli_reads_structured_answers(self):
        import tempfile, os, io, contextlib
        result = summarize(list(self.cases.values()), {'visa-card-en': LONG_PAY_EN, 'plan-beijing-3d-zh': ONE_SCREEN_PLAN_ZH},
                           profile=ONE_SCREEN)
        # checks.3 since first_paragraph joined the one-screen profile (#1664).
        self.assertEqual(result['version'], 'LIO-answer-quality-checks.3')
        self.assertEqual(result['answered'], 2)
        self.assertEqual(result['rates']['has_action'], 0.5)
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'answers.json')
            with open(path, 'w') as handle:
                json.dump({'visa-card-en': ONE_SCREEN_PAY_EN}, handle)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(main(['score', '--profile', ONE_SCREEN, path]), 0)
            self.assertIn('"has_action": 1.0', out.getvalue())
            with self.assertRaises(SystemExit):
                main(['score', path])  # the default profile keeps plain text answers only




class SplitFirstParagraph(unittest.TestCase):
    """JT 2026-11-25 two bubbles: the first paragraph is only the answer (or the emergency action)."""

    def setUp(self):
        self.cases = {case['id']: case for case in load_cases()}

    def check(self, case_id, text, chips=('1', '2')):
        actions = ['Open guide'] if case_id in ('alipay-zh', 'visa-card-en') else []
        return check_answer(self.cases[case_id], dict(text=text, actions=actions, chips=list(chips)), profile=ONE_SCREEN)

    def test_first_paragraph_is_short_single_line_and_followed_by_a_blank_line(self):
        good = self.check('alipay-zh', '出发前把 Visa 卡绑到支付宝就能扫码付款。\n\n1. 下载支付宝。\n2. 添加 Visa 卡。')
        self.assertTrue(good['checks']['first_paragraph'], good)
        for text in ('出发前把 Visa 卡绑到支付宝就能扫码付款。\n1. 下载支付宝。',            # no blank line
                     '出发前把 Visa 卡绑到支付宝，\n就能扫码付款。\n\n1. 下载。',               # line break inside
                     '出发前先把你的 Visa 或者万事达卡绑定到支付宝的国际版账户里，之后在商店里就能直接扫码付款了。\n\n1. 下载。'):
            with self.subTest(text=text):
                self.assertFalse(self.check('alipay-zh', text)['checks']['first_paragraph'])
        english = self.check('visa-card-en', 'Visa works at big hotels, but link it to Alipay for everyday payments.\n\n1. Download Alipay.')
        self.assertTrue(english['checks']['first_paragraph'])
        long_en = self.check('visa-card-en', ' '.join(['word'] * 21) + '.\n\n1. Download Alipay.')
        self.assertFalse(long_en['checks']['first_paragraph'])
        # Emergencies split too: the first paragraph is only the action.
        self.assertTrue(self.check('collapse-en', 'Call 120 now.\n\n1. Check breathing.')['checks']['first_paragraph'])

    def test_single_layout_answers_are_not_checked_for_a_split(self):
        greeting = check_answer(self.cases['greeting-zh'], '你好！准备去哪儿玩？', profile=ONE_SCREEN)
        self.assertNotIn('first_paragraph', greeting['checks'])
        for case_id in ('plan-beijing-3d-zh', 'followup-hangzhou-zh'):
            with self.subTest(case=case_id):
                self.assertNotIn('first_paragraph', self.check(case_id, '先按两位成人排。\n第 1 天 故宫')['checks'])
        self.assertNotIn('first_paragraph', check_answer(self.cases['alipay-zh'], '绑卡。'))  # detail profile unchanged

    def test_one_screen_profile_version_moves_with_the_new_checks(self):
        from eval.lio_answer_quality import PROFILES
        self.assertEqual(PROFILES[ONE_SCREEN], 'LIO-answer-quality-checks.3')


if __name__ == '__main__':
    unittest.main()


def test_followup_cases_for_1728_load_and_score_on_the_last_answer():
    # W2-2 (#1728): ten follow-ups that refer to the previous Lio reply.
    from eval.lio_answer_quality import ROOT, load_cases, main, summarize
    cases = load_cases(ROOT / 'lio_followup_cases.v1.json')
    assert len(cases) == 10
    assert sorted(case['locale'] for case in cases) == ['en'] * 5 + ['zh'] * 5
    assert all(case['scenario'] == 'followup' and len(case['turns']) == 2 and case['forbid'] for case in cases)
    case = next(case for case in cases if case['id'] == 'followup-chengdu-food-first-zh')
    good = ('钟水饺最地道的是总府路的老店，春熙路一带也有分店，地铁2号线春熙路站步行几分钟就到。'
            '中午人多，建议错峰去，点一份红油钟水饺配甜水面，再加一碗赖汤圆。')
    vague = '你指的是哪一个小吃呢？可以告诉我名字，我再推荐地方，成都的小吃很多，各个街区都有不同的店铺。'
    rows = {row['id']: row for row in summarize([case], {case['id']: good})['rows']}
    assert rows[case['id']]['passed']
    rows = {row['id']: row for row in summarize([case], {case['id']: vague})['rows']}
    assert not rows[case['id']]['checks']['uses_context']
    assert main(['cases', '--cases', str(ROOT / 'lio_followup_cases.v1.json')]) == 0
