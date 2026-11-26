import ast
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import re
import tempfile
import unittest

from eval.lio_answer_quality import load_cases as load_v1_cases
from eval.release_eval import bank as bank_module, report, run as run_module, score
from eval.release_eval.bank import BANK, load_bank
from eval.release_eval.report import classify, compare_report, single_report
from eval.release_eval.run import FixtureSender, RealSender, execute, plan, real_refusal
from eval.release_eval.score import percentile, score_answer, score_run

VISA_GOOD = ('商务洽谈能不能走免签，要看你的国籍和停留天数，免签政策不是对所有国家都适用。\n\n'
             '请以国家移民管理局官网或中国驻你所在国使馆、领事服务网的最新说明为准。')
VISA_BAD = '放心，免签对所有国家都适用，我可以帮你代办签证，我保证你能顺利入境。'
CARD_GOOD = ('把名片上的中文地址直接拿给司机看，或者复制到滴滴里当目的地。\n\n'
             '如果名片有电话，也可以请司机打给前台确认。')
CARD_BAD = '大多数司机都会说英文，直接读英文地址就行。'
CHENGDU_GOOD = '''成都三天按「熊猫—老城—美食」安排，节奏适中。

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
- 晚上：九眼桥看夜景。'''


def answer(text, first=None, total=None, error=None):
    return dict(text=text, first_token_ms=first, total_ms=total, error=error)


class BankTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = load_bank()
        cls.by_id = {case['id']: case for case in cls.cases}
        cls.raw = json.loads(BANK.read_text(encoding='utf8'))

    def test_counts_mixed_and_locales(self):
        self.assertTrue(60 <= len(self.cases) <= 80)
        mixed = [c for c in self.cases if c['kind'] == 'mixed']
        self.assertEqual(len(mixed), 30)
        for locale in ('zh', 'en'):
            self.assertGreaterEqual(sum(c['locale'] == locale for c in mixed), 12)
            self.assertGreaterEqual(sum(c['locale'] == locale for c in self.cases), 25)
        self.assertEqual(len({c['id'] for c in self.cases}), len(self.cases))

    def test_v1_cases_are_referenced_not_copied(self):
        v1 = {case['id']: case for case in load_v1_cases()}
        self.assertEqual({o['id'] for o in self.raw['v1_cases']}, set(v1))
        for overlay in self.raw['v1_cases']:
            self.assertNotIn('turns', overlay)
        merged = self.by_id['metro-airport-zh']
        self.assertTrue(merged['v1'])
        self.assertEqual(merged['turns'], v1['metro-airport-zh']['turns'])
        self.assertEqual(merged['require'], v1['metro-airport-zh']['require'])

    def test_every_case_has_rules_and_patterns_compile(self):
        for case in self.cases:
            with self.subTest(case=case['id']):
                self.assertTrue(case['must_not_say'])
                if case['scenario'] != 'greeting':
                    self.assertTrue(case['must_say'])
                for group in case['must_say']:
                    for pattern in group:
                        re.compile(pattern)
                for _, pattern in case['forbidden']:
                    re.compile(pattern)

    def test_visa_cases_point_to_official_channels(self):
        official = re.compile(r'移民管理局|领事|使馆|官方|NIA|National Immigration|embassy|consulate|official', re.I)
        visa = [c for c in self.cases if re.search(r'签证|免签|\bvisa\b(?! card)', ' '.join(c['turns']), re.I)]
        self.assertGreaterEqual(len(visa), 4)
        for case in visa:
            with self.subTest(case=case['id']):
                self.assertTrue(any(official.search(p) for g in case['must_say'] for p in g))

    def _write(self, mutate):
        raw = json.loads(json.dumps(self.raw))
        mutate(raw)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / 'bank.json'
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding='utf8')
        return path

    def test_validation_rejects_broken_banks(self):
        def drop_mixed(raw):
            raw['cases'] = [c for c in raw['cases'] if c['id'] != 'mixed-client-gift-en']

        def duplicate(raw):
            raw['cases'].append(dict(raw['cases'][-1]))

        def bad_regex(raw):
            raw['cases'][0]['must_not_say'] = ['(unclosed']

        def unknown_v1(raw):
            raw['v1_cases'][0]['id'] = 'no-such-v1-case'

        def unknown_set(raw):
            raw['cases'][0]['must_not_say'] = ['@nope']

        def missing_field(raw):
            del raw['cases'][0]['must_not_say']

        def too_few(raw):
            raw['cases'] = [c for c in raw['cases'] if c['kind'] == 'mixed'][:30]
            raw['cases'] = raw['cases'][:30]

        for mutate, message in ((drop_mixed, 'mixed'), (duplicate, 'duplicate'), (bad_regex, 'bad regex'),
                                (unknown_v1, 'unknown case'), (unknown_set, 'unknown forbidden set'),
                                (missing_field, 'case needs exactly'), (too_few, 'need 60-80')):
            with self.subTest(mutation=mutate.__name__), self.assertRaisesRegex(ValueError, message):
                load_bank(self._write(mutate))

    def test_list_cli(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(bank_module.main(['list']), 0)
        self.assertIn('mixed-shenzhen-factory-hk-zh', output.getvalue())
        self.assertIn("'total': ", output.getvalue())


class ScoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.by_id = {case['id']: case for case in load_bank()}

    def test_must_say_and_must_not_say(self):
        case = self.by_id['mixed-business-visa-vs-visafree-zh']
        good = score_answer(case, answer(VISA_GOOD))
        self.assertTrue(good['passed'], good)
        bad = score_answer(case, answer(VISA_BAD))
        self.assertFalse(bad['passed'])
        self.assertEqual(bad['must_say'], [False])
        sources = {v['source'] for v in bad['violations']}
        self.assertTrue({'@visa_overclaim', '@visa_service', '@always'} <= sources, sources)
        self.assertTrue(all(len(v['snippet']) <= 80 for v in bad['violations']))

    def test_forbidden_patterns_skip_negated_advice(self):
        # (case, a correct sentence that names the risky topic, the wrong claim it must catch)
        pairs = (
            ('transit-visa-zh', '免签政策并非所有国家都能免签，不是所有国籍都适用。', '所有国家的人都可以免签。'),
            ('visa-uk-en', 'Not all nationalities are visa-free, so check the official NIA site.',
             'All nationalities can enter visa-free.'),
            ('mixed-business-visa-vs-visafree-zh', '免签不能在中国工作，我也没法帮你办签证。', '免签也可以在中国工作。'),
            ('mixed-chengdu-meeting-panda-zh', '现在不能抱熊猫，也不可以喂熊猫。', '基地可以抱熊猫拍照。'),
            ('etiquette-zh', '筷子不能竖插在米饭里，也不是必须喝酒。', '筷子插在米饭里没关系，敬酒时必须喝完。'),
            ('mixed-shanghai-bund-halfday-zh', '外滩不收费，也不需要门票。', '外滩门票大约 50 元。'),
            ('mixed-beijing-meeting-family-zh', '八达岭不在市区，故宫必须提前实名预约。', '故宫不用提前预约，八达岭就在市区。'),
            ('plan-xian-2d-en', 'The Terracotta Warriors are not in the city center; allow an hour each way.',
             'The Terracotta Warriors are in the city center.'),
            ('maglev-bund-en', 'Take the Maglev to Longyang Road, then Line 2 takes you to the Bund.',
             'The Maglev goes directly to the Bund.'),
            ('mixed-beijing-weekend-wall-en', "The Great Wall isn't in central Beijing.", 'The Great Wall is in central Beijing.'),
            ('mixed-canton-fair-dinner-en', "Splitting the bill is not expected and you don't have to drink.",
             'Going Dutch is expected, and you must drink every toast.'),
            ('mixed-client-gift-en', "Don't give a clock as a gift; tea is a good choice.", 'A clock is a good gift.'),
            ('mixed-hangzhou-client-tea-zh', '送钟好像不太合适，送现金不合适。', '送钟也挺合适，送红包最得体。'),
            ('mixed-shanghai-hangzhou-weekend-zh', '上海到杭州没必要坐飞机，高铁更快。', '上海到杭州最好坐飞机。'),
            ('internet-esim-before-trip-zh', '不是所有手机都支持 eSIM，先查机型。', '所有手机都支持 eSIM。'),
            ('lost-child-disney-zh', '不需要满 24 小时才能报警，不要等一会儿再报警。', '先找找，等一会儿再报警。'),
            ('peanut-allergy-en', "Don't assume peanut oil is safe.", 'Refined peanut oil is usually safe.'),
            ('mixed-fapiao-reimburse-zh', '不能把发票金额开高，也不能找人代开发票。', '可以让司机把发票开高一点。'),
            ('mixed-fapiao-expense-en', 'Never buy fake receipts or inflate the amount.', 'You can inflate the amount on the fapiao.'),
            ('mixed-shenzhen-hk-flight-en', "Don't try to cross without your passport.",
             "You don't need a passport to cross into Hong Kong."),
            ('tipping-en', "It's not customary to tip, and you should never tip at street stalls.",
             'You should tip about 10% at restaurants.'),
            ('business-wechat-setup-en', 'In the US email is the main channel, but in China clients use WeChat.',
             "WeChat isn't used for business."),
            ('mixed-fever-before-meeting-en', 'Go to a hospital with your passport; do not self-medicate.',
             'Take some ibuprofen and you probably have food poisoning.'),
            ('alipay-zh', '外国游客可以用支付宝，绑 Visa 卡即可。', '外国人不能用支付宝。'),
            # Review of #1834: correct answers (negations, reminders, comparisons) must not be violations.
            ('collapse-en', "Call 120 — China's ambulance number, not 911. If they are having a seizure, don't hold them down.",
             'Call 911 right away.'),
            ('chest-pain-hotel-en', "Dial 120 (not 911). If your father is having a heart attack, every minute counts. Don't call 999.",
             'Dial 911 now; he probably has a heart attack.'),
            ('lost-phone-payments-en', 'Report it to the police on 110 (not 911).', 'Call 911 to report it.'),
            ('peanut-allergy-en', 'No restaurant can be 100% safe, and nothing is 100% guaranteed.', 'I guarantee this restaurant is safe.'),
            ('heatstroke-xian-zh', '没有百分之百安全的办法，先打 120，我保证不了别的。如果他是低血糖也一样先打 120。', '我保证他没事，喝点藿香正气水。'),
            ('tipping-en', "It's customary to tip tour guides, and you should tip your tour guide on a group tour.",
             'You should tip at restaurants, and always tip taxi drivers.'),
            ('mixed-fapiao-reimburse-zh', '不要让司机把发票开高，千万别让商家把发票金额写高。', '可以让司机把发票开高一点。'),
            ('mixed-fapiao-expense-en', "Don't ask the driver to inflate the amount.", 'Just ask the driver to inflate the total.'),
            ('mixed-shanghai-bund-halfday-zh', '外滩门票是免费的？其实外滩免费，不需要买票。外滩需要买票吗？不需要。', '外滩要买门票，外滩门票大约 50 元。'),
            ('internet-zh', '酒店Wi-Fi不能直接用Google，酒店的Wi-Fi也不能访问WhatsApp。', '酒店Wi-Fi可以直接用Google。'),
            ('transit-visa-zh', '目前中国还没有对所有国家免签，以国家移民管理局为准。', '中国对所有国家都免签。'),
            ('visa-uk-en', 'There is no visa-free entry for all nationalities.', 'There is visa-free entry for all nationalities.'),
            ('mixed-business-visa-vs-visafree-en', "Visa-free entry isn't for all nationalities; check the embassy.",
             'Visa-free entry for all nationalities lets you work too.'),
            ('mixed-shenzhen-factory-hk-zh', '回内地要看签证次数，以国家移民管理局为准，我没法帮你办签证。', '我可以帮你代办签证。'),
            ('metro-airport-zh', '坐首都机场线到东直门，中途不用换乘；在东直门换乘 2 号线。', '到王府井不用换乘。'),
            ('etiquette-zh', '敬酒不一定必须喝完。', '敬酒时必须喝完。'),
            ('business-wechat-setup-en', "WeChat isn't appropriate for business contracts — confirm those by email.",
             "WeChat isn't common for business."),
            ('lost-passport-zh', '我帮你办理不了补办，要去派出所报案。', '我可以帮你补办护照。'),
            ('mixed-trade-fair-language-zh', '供应商一般会说一点英文，但最好请翻译。', '供应商都会说流利的英文。'),
            ('metro-airport-zh', '机场线没有直达王府井的，要在东直门换乘；地铁不能直达王府井。', '可以直达王府井。'),
            ('metro-airport-zh', '地铁并不直达王府井。', '坐机场线直达王府井。'),
            ('mixed-trade-fair-language-zh', '不是每个供应商都会说英文，并不是所有供应商都会说英文。', '供应商都会说英文。'),
        )
        for case_id, safe, bad in pairs:
            case = self.by_id[case_id]
            with self.subTest(case=case_id, sample=safe[:20]):
                self.assertEqual(score_answer(case, answer(safe))['violations'], [])
                self.assertTrue(score_answer(case, answer(bad))['violations'])

    def test_must_say_accepts_synonyms(self):
        samples = (
            ('tipping-en', "Tipping isn't customary in China.", 'Tipping is expected everywhere.'),
            ('tipping-en', "You don't have to tip in China.", None),
            ('internet-zh', 'Google 和 WhatsApp 在中国大陆被屏蔽，可以开国际漫游。', '直接用就行。'),
            ('google-en', 'Google Maps will not work in China; use roaming or Amap.', None),
            ('mixed-client-gift-en', 'A good gift is tea; avoid sharp objects like knives.', None),
            ('chest-pain-hotel-en', 'Call 120 and ask the hotel to send someone to meet the ambulance.', None),
            ('mixed-fever-before-meeting-en', 'Go to a fever clinic (发热门诊) at a hospital and bring your ID.', None),
        )
        for case_id, hit, miss in samples:
            case = self.by_id[case_id]
            with self.subTest(case=case_id, sample=hit[:20]):
                self.assertTrue(all(score_answer(case, answer(hit))['must_say']))
                if miss:
                    self.assertFalse(all(score_answer(case, answer(miss))['must_say']))

    def test_violation_alone_fails_an_answer(self):
        case = self.by_id['mixed-business-visa-vs-visafree-zh']
        row = score_answer(case, answer(VISA_GOOD + '我保证你能顺利入境。'))
        self.assertEqual(row['must_say'], [True])
        self.assertTrue(row['violations'])
        self.assertFalse(row['passed'])

    def test_v1_cases_also_use_check_answer(self):
        case = self.by_id['plan-chengdu-followup-zh']
        self.assertTrue(score_answer(case, answer(CHENGDU_GOOD))['passed'])
        short = score_answer(case, answer('成都三天：熊猫基地、宽窄巷子、吃火锅。'))
        self.assertEqual(short['must_say'], [True, True])
        self.assertIn('detail_length', short['v1_failed'])
        self.assertFalse(short['passed'])

    def test_three_runs_latency_and_errors(self):
        cases = [self.by_id['mixed-business-card-driver-zh'], self.by_id['mixed-business-visa-vs-visafree-zh']]
        run = dict(run=dict(source_sha='a' * 40), answers={
            'mixed-business-card-driver-zh': [answer(CARD_GOOD, 100, 1000), answer(CARD_GOOD, 300, 3000),
                                              answer(CARD_BAD, 200, 2000)],
            'mixed-business-visa-vs-visafree-zh': [answer(VISA_GOOD, 400, 4000), answer(None, error='timeout'),
                                                   answer('  ')]})
        result = score_run(cases, run)
        card, visa = result['cases']['mixed-business-card-driver-zh'], result['cases']['mixed-business-visa-vs-visafree-zh']
        self.assertEqual((card['passed_runs'], card['passed'], card['violations']), (2, True, 1))
        self.assertEqual((card['first_token_ms_median'], card['total_ms_median']), (200, 2000))
        self.assertEqual((visa['passed_runs'], visa['passed'], visa['errors']), (1, False, 2))
        self.assertEqual(visa['error_messages'], ['empty answer', 'timeout'])
        s = result['summary']
        self.assertEqual((s['cases'], s['passed_cases'], s['answers'], s['errors'], s['violations']), (2, 1, 6, 2, 1))
        self.assertEqual(s['first_token_ms'], dict(p50=200, p95=400, n=4))
        self.assertEqual(s['total_ms'], dict(p50=2000, p95=4000, n=4))
        # The bad answer misses one of the two must_say groups; errored answers count nothing.
        self.assertEqual(s['must_say_hit_rate'], round(5 / 7, 3))
        self.assertEqual(s['by_kind']['mixed'], dict(cases=2, passed=1))

    def test_percentile_and_run_validation(self):
        self.assertIsNone(percentile([], 50))
        self.assertEqual(percentile(list(range(1, 21)), 95), 19)
        self.assertEqual(percentile([5], 95), 5)
        with self.assertRaises(ValueError):
            score.validate_run(dict(run={}, answers={'x': [dict(text='a', total_ms=-1)]}))
        with self.assertRaises(ValueError):
            score.validate_run(dict(run={}, answers={'x': [dict(text='a', extra=1)]}))


class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        by_id = {case['id']: case for case in load_bank()}
        cls.cases = [by_id['mixed-business-card-driver-zh'], by_id['mixed-business-visa-vs-visafree-zh']]

    def scored(self, card, visa, sha):
        return score_run(self.cases, dict(run=dict(source_sha=sha, model='m'), answers={
            'mixed-business-card-driver-zh': card, 'mixed-business-visa-vs-visafree-zh': visa}))

    def test_compare_finds_worse_and_better(self):
        old = self.scored([answer(CARD_GOOD, 100, 1000)] * 3, [answer(VISA_BAD, 100, 1000)] * 3, 'old')
        new = self.scored([answer(CARD_BAD, 150, 1500)] * 3, [answer(VISA_GOOD, 100, 900)] * 3, 'new')
        self.assertEqual(classify(old, new), (['mixed-business-card-driver-zh'], ['mixed-business-visa-vs-visafree-zh']))
        text = compare_report(old, new)
        self.assertIn('## 变差的题（1）', text)
        self.assertIn('## 变好的题（1）', text)
        self.assertIn('大多数司机都会说英文', text)
        self.assertIn('| 通过题数 | 1 | 1 | 0 |', text)
        self.assertIn('| 完整 p50 (ms) | 1000 | 900 | -100 |', text)
        self.assertIn('| 源提交 | old | new | |', text)
        self.assertEqual(classify(old, old), ([], []))

    def test_more_violations_with_same_pass_count_is_worse(self):
        unhelpful = [answer('我也不太清楚。', 100, 1000)] * 3
        old = self.scored(unhelpful, unhelpful, 'old')
        new = self.scored([answer(CARD_BAD, 100, 1000)] * 3, unhelpful, 'new')
        a, b = old['cases']['mixed-business-card-driver-zh'], new['cases']['mixed-business-card-driver-zh']
        self.assertEqual((a['passed_runs'], b['passed_runs']), (0, 0))
        self.assertEqual((a['violations'], b['violations']), (0, 3))
        self.assertEqual(classify(old, new), (['mixed-business-card-driver-zh'], []))

    def test_single_report_and_cli(self):
        new = self.scored([answer(CARD_GOOD, 100, 1000)] * 3, [answer(None, error='HTTP 503')] * 3, 'new')
        text = single_report(new)
        self.assertIn('# 发布评测单次报告', text)
        self.assertIn('mixed-business-visa-vs-visafree-zh', text)
        self.assertIn('HTTP 503', text)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'run.json'
            path.write_text(json.dumps(dict(run=dict(source_sha='x'), answers={
                'mixed-business-card-driver-zh': [answer(CARD_GOOD)]})), encoding='utf8')
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(report.main(['single', str(path)]), 0)
                self.assertEqual(report.main(['compare', str(path), str(path)]), 0)
            self.assertIn('未作答', output.getvalue())
            self.assertIn('## 变差的题（0）', output.getvalue())


class RunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = load_bank()

    def test_plan_counts_three_calls_per_case(self):
        planned = plan(self.cases, cost_per_turn_cny=0.01)
        self.assertEqual(planned['calls'], len(self.cases) * 3)
        self.assertEqual(planned['model_turns'], sum(len(c['turns']) for c in self.cases) * 3)
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(run_module.main(['plan']), 0)
        self.assertEqual(json.loads(output.getvalue())['calls'], len(self.cases) * 3)

    def test_real_calls_need_every_limit(self):
        for argv in (['run', '--real', '--output', 'x.json'],
                     ['run', '--real', '--max-calls', '1000', '--output', 'x.json'],
                     ['run', '--real', '--max-calls', '1000', '--max-cost-cny', '10', '--output', 'x.json'],
                     ['run', '--real', '--max-calls', '1000', '--cost-per-turn-cny', '0.01', '--output', 'x.json'],
                     ['run', '--max-calls', '1000', '--max-cost-cny', '10', '--cost-per-turn-cny', '0.01'],
                     ['run', '--real', '--fixture', 'f.json', '--max-calls', '1000', '--max-cost-cny', '10',
                      '--cost-per-turn-cny', '0.01']):
            with self.subTest(argv=argv), self.assertRaises(SystemExit) as raised:
                run_module.main(argv)
            self.assertIn('拒绝真调用', str(raised.exception.code))
        calls = len(self.cases) * 3
        with self.assertRaisesRegex(SystemExit, '超过 --max-calls'):
            run_module.main(['run', '--real', '--max-calls', str(calls - 1), '--max-cost-cny', '1000',
                             '--cost-per-turn-cny', '0.01', '--output', 'x.json'])
        with self.assertRaisesRegex(SystemExit, '超过 --max-cost-cny'):
            run_module.main(['run', '--real', '--max-calls', str(calls), '--max-cost-cny', '0.01',
                             '--cost-per-turn-cny', '0.01', '--output', 'x.json'])
        self.assertIsNone(real_refusal(plan(self.cases, cost_per_turn_cny=0.01), calls, 100))
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(SystemExit, '未实现'):
            run_module.main(['run', '--real', '--max-calls', str(calls), '--max-cost-cny', '100',
                             '--cost-per-turn-cny', '0.01', '--output', str(Path(directory) / 'run.json')])
        with self.assertRaises(NotImplementedError):
            RealSender()

    def test_fixture_run_round_trips_into_score(self):
        cases = [c for c in self.cases if c['id'] in ('mixed-business-card-driver-zh', 'greeting-zh')]
        sender = FixtureSender({'mixed-business-card-driver-zh': [CARD_GOOD, dict(text=CARD_BAD, total_ms=5)]})
        value = execute(cases, sender, meta=dict(source_sha='abc'))
        self.assertEqual(value['run']['sender'], 'fixture')
        self.assertEqual(len(value['answers']['mixed-business-card-driver-zh']), 3)
        self.assertEqual(value['answers']['mixed-business-card-driver-zh'][2]['text'], CARD_GOOD)
        self.assertEqual(value['answers']['greeting-zh'][0]['error'], 'fixture has no answer')
        result = score_run(cases, value)
        self.assertEqual(result['cases']['mixed-business-card-driver-zh']['passed_runs'], 2)
        self.assertEqual(result['summary']['errors'], 3)
        with self.assertRaises(ValueError):
            execute(cases, sender, max_calls=5)

    def test_runner_has_no_network_imports(self):
        for module in (run_module, score, report, bank_module):
            tree = ast.parse(Path(module.__file__).read_text(encoding='utf8'))
            names = {alias.name.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
            names |= {node.module.split('.')[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
            self.assertFalse(names & {'socket', 'http', 'urllib', 'httpx', 'requests', 'ssl'}, module.__name__)


if __name__ == '__main__':
    unittest.main()
