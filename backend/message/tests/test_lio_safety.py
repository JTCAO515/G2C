"""W2-6 (#1733): safety essentials are appended by code when the answer misses them."""
import os
import unittest
from unittest.mock import patch

from cj_message.lio_safety import REQUIREMENTS, matched, safety_lines_enabled, supplement

POLICE = ('110', '报警', '报案', '派出所', 'police')
CONSULATE = ('使馆', '领馆', 'embassy', 'consulate')


class SafetyLines(unittest.TestCase):
    def test_lost_passport_answers_always_include_police_and_consulate(self):
        # Acceptance: a lost-passport question ends with both essentials whatever the model wrote.
        questions = {'zh': ('护照丢了怎么办', '我的护照被偷了', '在上海弄丢了护照', '证件丢了怎么补办'),
                     'en': ('I lost my passport, what should I do?', 'My passport was stolen in Beijing',
                            'Help, my passport is missing')}
        answers = {'zh': ('', '别着急，先回想一下最后在哪里用过。', '先去派出所报案。', '联系你国家的大使馆。',
                          '先报警，再联系驻华使馆。'),
                   'en': ('', 'Stay calm and retrace your steps.', 'Go to the police first.',
                          'Contact your embassy.', 'Call the police and then your consulate.')}
        for locale in ('zh', 'en'):
            for question in questions[locale]:
                for answer in answers[locale]:
                    with self.subTest(question=question, answer=answer):
                        self.assertIn('lost_documents', matched(question))
                        final = (answer + supplement(question, answer, locale)).casefold()
                        self.assertTrue(any(word.casefold() in final for word in POLICE))
                        self.assertTrue(any(word.casefold() in final for word in CONSULATE))

    def test_review_detection_cases(self):
        # Review of #1863: common lost-passport and fainting phrasings; idioms and medicine are not safety questions.
        for question, kind in (('护照找不到了怎么办', 'lost_documents'), ('找不到护照了', 'lost_documents'),
                               ('护照没了', 'lost_documents'), ('护照忘在出租车上了', 'lost_documents'),
                               ("I can't find my passport anywhere", 'lost_documents'),
                               ('I misplaced my passport', 'lost_documents'), ('I left my passport in a taxi', 'lost_documents'),
                               ('my friend fainted', 'emergency'), ('她晕过去了', 'emergency'), ('朋友昏过去了', 'emergency'),
                               ('he had a stroke', 'emergency'), ('I feel sick', 'medical'),
                               ('我对花生过敏', 'dietary'), ('I am allergic to peanuts', 'dietary')):
            with self.subTest(question=question):
                self.assertIn(kind, matched(question))
        for question in ("I'm sick of rice", 'that was ill-advised', 'what a stroke of luck', '过敏性鼻炎药哪里买',
                         '护照照片怎么拍', 'visa card'):
            with self.subTest(question=question):
                self.assertEqual(matched(question), ())

    def test_pre_switch_detection_fixes(self):
        # #1733 review follow-up (before turning the switch on): more emergencies, no false lost-passport lines.
        for question, kind in (('叫他没反应', 'emergency'), ('她倒地后没反应', 'emergency'), ('朋友叫不醒', 'emergency'), ('胸口疼得厉害', 'emergency'),
                               ('被车撞了', 'emergency'), ('手被烫伤了', 'emergency'), ('好像中暑了', 'emergency'),
                               ('I feel faint', 'emergency'), ('she passed out', 'emergency'), ('chest pain', 'emergency'),
                               ('someone stole my passport', 'lost_documents'), ('护照落在滴滴上了', 'lost_documents'), ('I forgot my passport in a taxi', 'lost_documents'), ('被摩托车撞了', 'emergency'), ('护照被抢了', 'lost_documents'),
                               ('I left my passport in a taxi', 'lost_documents'), ('护照忘在出租车上了', 'lost_documents')):
            with self.subTest(question=question):
                self.assertIn(kind, matched(question))
        for question in ('I forgot my passport number', 'I forgot to bring my passport', '护照落在酒店前台登记了',
                         'I left my passport at the hotel front desk', 'where to buy hay fever medicine',
                         'there is a faint smell', 'I passed out from laughing', '支付宝没反应了',
                         # Second review of #1918: passport handed over or photographed, messages not answered,
                         # prevention questions and pet allergies are not safety questions.
                         'where can I get my passport photo taken', 'my passport was taken by the hotel for registration',
                         'they took my passport to make a copy', 'he took my passport at check-in',
                         '我给房东发消息他没反应怎么办', '叫了滴滴，司机他一直没反应', '朋友微信没反应', '客服人员没反应',
                         '工作人员没反应', '孩子对熊猫没反应', '我妈妈对川菜没反应', '防中暑要带什么', '车祸多吗',
                         '烫伤膏哪里买', 'heatstroke prevention tips', 'allergic to cats', '我被他撞见了'):
            with self.subTest(question=question):
                self.assertEqual(matched(question), ())

    def test_negated_or_unrelated_mentions_do_not_count_as_present(self):
        # Review of #1863: "120 元", "别报警" and "这说明" are not the essentials.
        self.assertIn('120', supplement('朋友晕倒了', '打车大约 120 元。', 'zh'))
        self.assertIn('派出所', supplement('护照丢了', '别报警，先联系大使馆。', 'zh'))
        self.assertNotIn('使馆或领馆', supplement('护照丢了', '别报警，先联系大使馆。', 'zh'))
        self.assertIn('告诉店员', supplement('我对花生过敏', '这说明花生很常见。', 'zh'))
        self.assertIn('police', supplement('I lost my passport', "Don't call the police yet; contact your embassy.", 'en'))

    def test_only_missing_essentials_are_added(self):
        both = '先去派出所报案，再联系你国家的驻华使馆。'
        self.assertEqual(supplement('护照丢了怎么办', both, 'zh'), '')
        police_only = supplement('护照丢了怎么办', '先去派出所报案。', 'zh')
        self.assertIn('使馆或领馆', police_only)
        self.assertNotIn('派出所报案并开具', police_only)

    def test_other_safety_kinds(self):
        for question, answer, locale, expected in (
                ('我朋友晕倒了怎么办', '让他平躺。', 'zh', '120'),
                ('My friend collapsed', 'Keep them lying down.', 'en', '120'),
                ('发烧了去哪看病', '多喝水休息。', 'zh', '医院'),
                ('I have a fever, where can I see a doctor?', 'Rest and drink water.', 'en', 'hospital'),
                ('我对花生过敏，点菜要注意什么', '川菜常用花生。', 'zh', '告诉店员'),
                ('I am vegetarian, what can I eat in Chengdu?', 'Try mapo tofu without meat.', 'en', 'tell the staff')):
            with self.subTest(question=question):
                self.assertIn(expected, supplement(question, answer, locale))

    def test_complete_or_unrelated_answers_get_nothing(self):
        self.assertEqual(supplement('我朋友晕倒了', '马上拨打 120。', 'zh'), '')
        self.assertEqual(supplement('成都有什么好吃的', '火锅。', 'zh'), '')
        self.assertEqual(supplement('护照丢了怎么办', '', 'fr'), '')

    def test_several_kinds_in_one_question_and_no_duplicate_lines(self):
        lines = supplement('护照丢了，而且发烧了', '', 'zh')
        self.assertIn('派出所', lines)
        self.assertIn('使馆', lines)
        self.assertIn('医院', lines)
        self.assertEqual(len(lines.strip().split('\n')), len(set(lines.strip().split('\n'))))

    def test_every_fixed_line_satisfies_its_own_check(self):
        for requirement in REQUIREMENTS:
            for pattern, line in requirement.essentials:
                for locale in ('zh', 'en'):
                    with self.subTest(key=requirement.key, locale=locale):
                        self.assertIsNotNone(pattern.search(line[locale]))

    def test_switch_is_off_by_default_and_accepts_only_zero_or_one(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('CJ_LIO_SAFETY_LINES', None)
            self.assertFalse(safety_lines_enabled())
        with patch.dict(os.environ, {'CJ_LIO_SAFETY_LINES': '1'}):
            self.assertTrue(safety_lines_enabled())
        with patch.dict(os.environ, {'CJ_LIO_SAFETY_LINES': 'on'}), self.assertRaises(ValueError):
            safety_lines_enabled()


if __name__ == '__main__':
    unittest.main()
