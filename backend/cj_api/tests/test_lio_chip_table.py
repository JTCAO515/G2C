"""Tap-to-ask chip table, topic selection, "save to trips" chip and the save-button sentence filter (#1976, #1978).

No wire, no model: the table and the pure selection functions only.
"""
import unittest

from cj_api.lio_planning_grounding import planning_withdrawn, requests_save
from cj_message import lio_chip_table, lio_followups as followups
from cj_message.lio_context import display_answer

ZH_QUESTIONS = (
    '帮我规划北京三天行程', '北京到上海怎么去最方便', '故宫需要提前预约吗', '推荐几家北京烤鸭店', '住哪个区域比较方便',
    '在中国怎么换人民币', '手机怎么上网', '免签入境要注意什么', '长城怎么走', '你好，我下个月去成都', '广州有什么好玩的',
    '地铁怎么买票', '带小孩去重庆玩什么', '深圳一日游怎么安排', '我想吃不辣的菜', '酒店可以寄存行李吗',
)
EN_QUESTIONS = (
    'Plan a 3-day trip in Beijing', 'How do I get from the airport to the city center?', 'Do I need to book the Forbidden City?',
    'Where can I find halal food in Shanghai?', 'Which area should I stay in Chengdu?', 'Can I use my foreign card in China?',
    'How do I get a SIM card?', 'What do I need to enter China visa-free?', 'Is the Great Wall far from Beijing?',
    'Hi, I am going to Guangzhou next month', 'What should I see in Chongqing?', 'How does the metro work?',
    'Any tips for traveling with kids?', 'What is a good day trip from Shenzhen?', 'Is tipping expected?', 'Hello',
)


class Table(unittest.TestCase):
    def test_table_follows_its_own_rules(self):
        self.assertTrue(lio_chip_table.validate())
        self.assertGreaterEqual(min(len(rows) for rows in lio_chip_table.TABLE['topics'].values()), lio_chip_table.MIN_PER_TOPIC)
        self.assertEqual(set(lio_chip_table.MISSING_TO_GROUP.values()) - set(lio_chip_table.GROUPS), set())

    def test_validate_rejects_a_bad_table(self):
        import copy
        for mutate in (
            lambda t: t['topics']['food'].append({'zh': '一二三四五六七八九十一二三', 'en': 'ok'}),   # 13 characters
            lambda t: t['topics']['food'].append({'zh': '好', 'en': 'x' * 25}),
            lambda t: t['topics']['food'].append({'zh': '换\n行', 'en': 'two\nlines'}),
            lambda t: t['topics']['food'].append(dict(t['topics']['food'][0])),                 # repeat
            lambda t: t['topics'].pop('entry'),
            lambda t: t['missing_info']['days'].pop(),
            lambda t: t['topics']['trip'].append({'zh': '好'}),
        ):
            table = copy.deepcopy(lio_chip_table.TABLE)
            mutate(table)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                lio_chip_table.validate(table)

    def test_every_row_passes_the_chip_checks_in_its_language(self):
        for rows in lio_chip_table.TABLE['topics'].values():
            self.assertEqual(len(followups.chips([row['zh'] for row in rows], 'zh')), min(len(rows), followups.MAX_CHIPS))
            self.assertEqual(len(followups.chips([row['en'] for row in rows], 'en')), min(len(rows), followups.MAX_CHIPS))

    def test_no_row_asks_for_business_or_a_judgement(self):
        banned = ('展会', '商务', '合同', '诊断', '用药', 'trade fair', 'exhibition', 'business', 'diagnos', 'medic', 'prescription', 'religio')
        for rows in (*lio_chip_table.TABLE['topics'].values(), *lio_chip_table.TABLE['missing_info'].values()):
            for row in rows:
                for text in row.values():
                    self.assertFalse(any(word in text.casefold() for word in banned), text)


class Selection(unittest.TestCase):
    def test_every_normal_answer_gets_two_or_three_chips(self):
        for locale, questions in (('zh', ZH_QUESTIONS), ('en', EN_QUESTIONS)):
            for question in questions:
                with self.subTest(question=question):
                    labels = followups.chips_for(question, locale)
                    self.assertTrue(followups.MIN_CHIPS <= len(labels) <= followups.MAX_CHIPS, labels)
                    self.assertEqual(len(set(labels)), len(labels))
                    self.assertNotIn(question.strip(), labels)
                    self.assertEqual(labels, followups.chips_for(question, locale))      # deterministic

    def test_topics_are_found(self):
        for question, topic in (('故宫需要提前预约吗', 'sight'), ('住哪个区域比较方便', 'stay'), ('手机怎么上网', 'network'),
                                ('在中国怎么换人民币', 'money'), ('免签入境要注意什么', 'entry'), ('我想吃不辣的菜', 'food'),
                                ('地铁怎么买票', 'route'), ('帮我规划北京三天行程', 'trip'),
                                ('Where can I find halal food in Shanghai?', 'food'), ('How do I get a SIM card?', 'network')):
            with self.subTest(question=question):
                self.assertIn(topic, followups.chip_topics(question))

    def test_topic_chips_come_from_the_topics_table(self):
        sight = {row['zh'] for row in lio_chip_table.TABLE['topics']['sight']}
        labels = followups.chips_for('故宫需要提前预约吗', 'zh')
        self.assertTrue(sight & set(labels), labels)

    def test_payment_and_taxi_keep_their_reviewed_rows(self):
        for question, topic in (('怎么用支付宝付款', 'payment'), ('怎么打车去故宫', 'taxi'),
                                ('How do I pay with Alipay?', 'payment'), ('How do I get a taxi?', 'taxi')):
            for index, locale in ((0, 'zh' if question[0] > 'z' else 'en'),):
                expected = [row[0 if locale == 'zh' else 1] for row in followups.CHIP_TABLE[topic]]
                with self.subTest(question=question):
                    self.assertEqual(followups.chips_for(question, locale), expected)

    def test_missing_fact_chips_answer_the_question_the_answer_asks(self):
        for field, group in lio_chip_table.MISSING_TO_GROUP.items():
            for locale in ('zh', 'en'):
                with self.subTest(field=field, locale=locale):
                    expected = [row[locale] for row in lio_chip_table.TABLE['missing_info'][group]][:2]
                    labels = followups.chips_for('我想去北京玩' if locale == 'zh' else 'I want to visit Beijing', locale, missing=field)
                    self.assertEqual(labels[:2], expected)
                    self.assertLessEqual(len(labels), followups.MAX_CHIPS)

    def test_a_missing_fact_without_a_group_adds_nothing_special(self):
        for field in ('venue', 'hotel', 'nationality', 'unknown', None):
            self.assertEqual(followups.chips_for('故宫需要提前预约吗', 'zh', missing=field), followups.chips_for('故宫需要提前预约吗', 'zh'))

    def test_save_chip_only_after_a_plan(self):
        zh_save, en_save = followups.SAVE_CHIP
        self.assertIn(zh_save, followups.chips_for('帮我规划北京三天行程', 'zh'))
        self.assertIn(en_save, followups.chips_for('Plan a 3-day trip in Beijing', 'en'))
        self.assertNotIn(zh_save, followups.chips_for('故宫需要提前预约吗', 'zh'))
        self.assertNotIn(en_save, followups.chips_for('Is tipping expected?', 'en'))
        self.assertIn(zh_save, followups.chips_for('故宫需要提前预约吗', 'zh', plan_answer=True))
        self.assertNotIn(zh_save, followups.chips_for('帮我规划北京三天行程', 'zh', plan_answer=False))

    def test_save_chip_text_is_read_by_the_server_as_a_request_to_save(self):
        for label in followups.SAVE_CHIP:
            with self.subTest(label=label):
                self.assertTrue(requests_save(label))
                self.assertFalse(planning_withdrawn(label))
        for text in ('保存到行程', '保存到我的行程', '保存到 trip', '保存到行程页', '保存到行程里', 'Save to trip', 'save to my trips', 'please save it to my trips'):
            with self.subTest(text=text):
                self.assertTrue(requests_save(text))
                self.assertFalse(planning_withdrawn(text))

    def test_other_save_words_are_not_a_save_request(self):
        for text in ('保存到手机相册', 'Save to my phone', '保存成图片'):
            with self.subTest(text=text):
                self.assertFalse(requests_save(text))

    def test_odd_question_text_never_raises(self):
        for question in ('', '   ', 'x' * 100000, '\ud800坏', '😀' * 50):
            labels = followups.chips_for(question, 'zh')
            self.assertTrue(followups.MIN_CHIPS <= len(labels) <= followups.MAX_CHIPS)

    def test_hint_is_data_only(self):
        self.assertEqual(followups.FollowupHint('dates').missing, 'dates')
        with self.assertRaises(Exception):
            followups.FollowupHint('dates').missing = 'days'


class SaveButtonSentences(unittest.TestCase):
    def test_a_sentence_that_tells_to_tap_a_button_to_save_is_dropped(self):
        self.assertEqual(display_answer('第一天去故宫。点「记住」即可保存到行程卡。第二天去长城。', 'zh'), '第一天去故宫。第二天去长城。')
        self.assertEqual(display_answer('第一天去故宫。点击记住就可以保存行程。', 'zh'), '第一天去故宫。')
        self.assertEqual(display_answer('Day 1 Forbidden City. Tap Remember to save this plan to your trip. Day 2 Wall.', 'en'),
                         'Day 1 Forbidden City. Day 2 Wall.')

    def test_ordinary_text_and_memory_wording_are_kept(self):
        for text, locale in (('点「记住」之后，下次规划就会用上。', 'zh'), ('You can remember the metro line. It costs 3.5 yuan.', 'en'),
                             ('Whatever you tap Remember on, I will use in future chats.', 'en'), ('第一天去故宫，第二天去长城。', 'zh')):
            with self.subTest(text=text):
                self.assertEqual(display_answer(text, locale), text)

    def test_text_with_nothing_to_drop_is_returned_byte_for_byte(self):
        # postgres shard 5 (lio_ordinary_unsettled_pg) compares a stored reply that ends in a blank
        for text, locale in (('Start in one city and leave time to explore. ' * 8, 'en'), ('先去故宫。  \n', 'zh'), (' lead', 'en')):
            self.assertEqual(display_answer(text, locale), text)

    def test_the_fixed_copy_that_mentions_remember_is_untouched(self):
        # CI found the first version cutting "Tap Remember and I'll use it next time I plan." out of the approved
        # capability copy; every fixed text of the module that says Remember or 记住 must come through unchanged.
        from cj_message import lio_context
        texts = [(name, value) for name, value in vars(lio_context).items()
                 if name.isupper() and type(value) is str and ('Remember' in value or '记住' in value)
                 and name != 'PERSONA' and not name.endswith('_PROMPT')]   # prompts are instructions, not answers
        self.assertIn('CAPABILITIES_EN', [name for name, _ in texts])
        for name, value in texts:
            with self.subTest(name=name):
                self.assertEqual(display_answer(value, 'zh' if name.endswith('_ZH') else 'en'), value)

    def test_an_answer_that_is_only_such_a_sentence_is_not_emptied(self):
        text = '点「记住」即可保存到行程卡。'
        self.assertEqual(display_answer(text, 'zh'), text)


if __name__ == '__main__':
    unittest.main()
