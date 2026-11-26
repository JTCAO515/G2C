"""One-screen layout switch, per-answer layout and fixed follow-up actions (W2-1, #1727). No wire, no model."""
import os
import unittest
from unittest import mock

from cj_api import lio_answer_layout as layout
from cj_message import lio_followups as followups
from cj_message.lio_context import answer_prompt

ONE, TWO, OTHER = 'm4-synthetic-demo-aaaaaaaaaaaa', 'm4-synthetic-demo-bbbbbbbbbbbb', 'm4-synthetic-demo-cccccccccccc'
LISTED = '["%s","%s"]' % (ONE, TWO)


def env(mode=None, subjects=None):
    values = {}
    if mode is not None:
        values['CJ_LIO_ANSWER_LAYOUT'] = mode
    if subjects is not None:
        values['CJ_LIO_ANSWER_LAYOUT_SUBJECTS_JSON'] = subjects
    return mock.patch.dict(os.environ, values, clear=False)


class Switch(unittest.TestCase):
    def setUp(self):
        for name in ('CJ_LIO_ANSWER_LAYOUT', 'CJ_LIO_ANSWER_LAYOUT_SUBJECTS_JSON'):
            patcher = mock.patch.dict(os.environ)
            patcher.start()
            self.addCleanup(patcher.stop)
            os.environ.pop(name, None)

    def test_default_is_flat_and_never_reads_the_list(self):
        self.assertEqual(layout.layout_mode(), 'flat')
        self.assertEqual(layout.subjects(), frozenset())
        with env('flat', 'not json'):
            self.assertEqual(layout.subjects(), frozenset())

    def test_value_must_be_explicit(self):
        for value in ('', 'one_screen', 'ONE-SCREEN', '1', 'on'):
            with self.subTest(value=value), env(value):
                with self.assertRaises(ValueError):
                    layout.layout_mode()

    def test_subject_list_is_strict_when_the_switch_is_on(self):
        with env('one-screen', LISTED):
            self.assertEqual(layout.subjects(), frozenset({ONE, TWO}))
        for bad in ('', 'null', '[]', '{}', '"%s"' % ONE, '["G2C@01"]', '["m4-synthetic-demo-short"]',
                    '["%s","%s"]' % (ONE, ONE), '["M4-SYNTHETIC-DEMO-AAAAAAAAAAAA"]', '[1]', '["%s", null]' % ONE,
                    '["%s "]' % ONE, '["m4-synthetic-one"]', 'nope'):
            with self.subTest(bad=bad), env('one-screen', bad):
                with self.assertRaises(ValueError):
                    layout.subjects()
        with env('one-screen'):
            with self.assertRaises(ValueError):
                layout.subjects()  # the list variable is required once the switch is on

    def test_answer_layout_is_none_when_flat_and_split_only_for_a_listed_account(self):
        with env('flat', LISTED):
            self.assertIsNone(layout.answer_layout(ONE, 'How do I pay with Alipay?'))
        with env('one-screen', LISTED):
            self.assertEqual(layout.answer_layout(ONE, 'How do I pay with Alipay?'), 'split')
            self.assertEqual(layout.answer_layout(OTHER, 'How do I pay with Alipay?'), 'single')   # not listed
            self.assertEqual(layout.answer_layout(None, 'How do I pay with Alipay?'), 'single')
            # an emergency is an ordinary answer and splits; the code-written self description does not
            self.assertEqual(layout.answer_layout(ONE, 'My friend collapsed on the street, call an ambulance'), 'split')
            for question in ('who are you', '你是谁', '你能做什么', 'what can you do'):
                self.assertEqual(layout.answer_layout(ONE, question), 'single', question)

    def test_prompt_layout_changes_the_prompt_only_for_split(self):
        self.assertEqual(layout.prompt_layout('split'), 'one-screen')
        for value in ('single', None):
            self.assertEqual(layout.prompt_layout(value), 'flat')
            self.assertEqual(answer_prompt('zh', layout=layout.prompt_layout(value)), answer_prompt('zh'))
        self.assertNotEqual(answer_prompt('zh', layout='one-screen'), answer_prompt('zh'))


class Actions(unittest.TestCase):
    def test_payment_and_taxi_questions_get_fixed_buttons(self):
        payment = followups.allowed_actions('外国游客在中国怎么用支付宝？', 'zh')
        self.assertEqual([a.wire() for a in payment], [dict(tool='payment-guide', parameters={}, label='打开支付开通指南')])
        self.assertEqual(followups.allowed_actions('支付宝绑卡失败了怎么办', 'zh')[0].label, '打开支付开通指南')
        self.assertEqual([a.label for a in followups.allowed_actions('How do I pay with Alipay?', 'en')], ['Payment setup guide'])
        taxi = followups.allowed_actions('怎么打车去机场', 'zh')
        self.assertEqual([a.wire() for a in taxi], [dict(tool='taxi', parameters={}, label='打车')])
        for question in ('Where can I get a taxi?', 'Are taxis expensive?', 'How do I hail a cab', 'Can I use Uber?', '怎么叫个车', '附近怎么打的'):
            self.assertEqual(followups.allowed_actions(question, 'en')[0].tool, 'taxi', question)

    def test_other_questions_and_look_alike_words_get_no_buttons(self):
        for question in ('成都有什么必吃的？', 'What is the weather in Beijing?', '你好', 'My visa application failed',
                         'Is visa-free entry available for me?', 'Do I need a visa for Chengdu?', '签证怎么办'):
            self.assertEqual(followups.allowed_actions(question, 'zh'), [], question)
        self.assertEqual(followups.allowed_actions('Can I use my Visa card in China?', 'en')[0].tool, 'payment-guide')

    def test_taxi_destination_comes_only_from_server_evidence_in_the_apps_parameter_names(self):
        place = followups.Destination('故宫博物院', '116.397026,39.918058', '景山前街4号', 'The Palace Museum')
        action, = followups.allowed_actions('怎么打车去故宫', 'zh', destination=place)
        self.assertEqual(action.label, '打车去这里')
        self.assertEqual(action.parameters, {'destination': '故宫博物院', 'lat': '39.918058', 'lng': '116.397026',
                                             'address': '景山前街4号', 'destinationEN': 'The Palace Museum'})
        # No coordinate, or one outside China or with too many decimals: the plain taxi page.
        for location in ('', '116.397026', '2.0,39.9', '116.4,60.0', '116.3970261,39.9', '0,0', 'x,y', '116.4,39.9,1'):
            with self.subTest(location=location):
                action, = followups.allowed_actions('打车去故宫', 'zh', destination=followups.Destination('故宫', location))
                self.assertEqual((action.label, action.parameters), ('打车', {}))
        bare = followups.Destination('故宫博物院', '116.397026,39.918058')
        parameters = followups.allowed_actions('打车去故宫', 'zh', destination=bare)[0].parameters
        self.assertEqual(set(parameters), {'destination', 'lat', 'lng'})

    def test_at_most_two_buttons_and_labels_fit_the_limits(self):
        place = followups.Destination('故宫', '116.4,39.9')
        actions = followups.allowed_actions('支付宝失败了，怎么打车去故宫', 'zh', destination=place)
        self.assertEqual([a.tool for a in actions], ['payment-guide', 'taxi'])
        for locale, cap in (('zh', 12), ('en', 24)):
            for label in followups.LABELS.values():
                self.assertLessEqual(len(label[0 if locale == 'zh' else 1]), cap)

    def test_parameter_rules_match_the_app_registry(self):
        check = followups.checked_parameters
        place = {'destination': '故宫', 'lat': '39.9', 'lng': '116.4'}
        self.assertEqual(check('payment-guide', {}), {})
        self.assertEqual(check('taxi', {}), {})
        self.assertEqual(check('taxi', {'destination': ' 故宫 ', 'lat': '39.9', 'lng': '116.4'}), place)
        for tool, parameters in (
                ('payment-guide', {'section': 'troubleshooting'}), ('payment-guide', {'x': 'y'}), ('unknown', {}), ('trip', {'trip_id': 'a'}),
                ('taxi', {'destination': '故宫'}), ('taxi', {'lat': '39.9', 'lng': '116.4'}),            # half a destination
                ('taxi', {**place, 'lat': 'bad'}), ('taxi', {**place, 'lng': '200'}), ('taxi', {**place, 'lat': '39.1234567'}),
                ('taxi', {**place, 'destination': '故宫\n'}), ('taxi', {**place, 'destination': 'x' * 201}),
                ('taxi', {**place, 'destination': '   '}), ('taxi', {**place, 'address': '\u200b'}),
                ('taxi', {**place, 'address': 'a\x85b'}), ('taxi', {**place, 'destination_name_zh': 'old name'}),
                ('taxi', {**place, 'lat': 39.9}), ('taxi', 'destination=x'), ('taxi', None)):
            with self.subTest(tool=tool, parameters=parameters):
                self.assertIsNone(check(tool, parameters))

    def test_parameter_size_limits_are_enforced_at_their_boundaries(self):
        check = followups.checked_parameters
        place = {'destination': '故', 'lat': '39.9', 'lng': '116.4'}
        self.assertEqual(check('taxi', {**place, 'destination': 'x' * 200}), {**place, 'destination': 'x' * 200})
        self.assertIsNone(check('taxi', {**place, 'destination': 'x' * 201}))
        # 600 bytes of compact JSON in all: a long Chinese address pushes it over, 190 characters stay under.
        self.assertIsNotNone(check('taxi', {**place, 'address': '街' * 150}))
        self.assertIsNone(check('taxi', {**place, 'address': '街' * 200}))
        # more than eight parameters can never happen with five names, but the cap is checked first
        with mock.patch.object(followups, 'MAX_PARAMETERS', 2):
            self.assertIsNone(check('taxi', place))

    def test_the_model_can_only_pick_from_the_offered_list(self):
        offered = followups.allowed_actions('支付宝怎么打车', 'zh')
        self.assertEqual(len(offered), 2)
        self.assertEqual(followups.pick_actions(offered, [1]), [offered[1]])
        self.assertEqual(followups.pick_actions(offered, [1, 1, 0, 0]), [offered[1], offered[0]])
        for chosen in ([2], [-1], ['0'], [True], [None], 0, 'all', None, [{'tool': 'taxi'}]):
            with self.subTest(chosen=chosen):
                self.assertEqual(followups.pick_actions(offered, chosen), [])

    def test_chips_are_bounded_and_clean(self):
        self.assertEqual(followups.chips(['付不了怎么办', '哪些地方不能用', '怎么开通地铁码', '第四个'], 'zh'),
                         ['付不了怎么办', '哪些地方不能用', '怎么开通地铁码'])
        self.assertEqual(followups.chips(['一二三四五六七八九十一二', '一二三四五六七八九十一二三'], 'zh'), ['一二三四五六七八九十一二'])  # 12 ok, 13 not
        self.assertEqual(followups.chips(['x' * 24, 'y' * 25], 'en'), ['x' * 24])
        self.assertEqual(followups.chips(['What if my card is declined?', 'Short one', 'Short one'], 'en'), ['Short one'])
        self.assertEqual(followups.chips(['a\nb', '正常', '', 5, None, '  多  余   空格  ', 'a\u200bb'], 'zh'), ['正常', '多 余 空格'])
        self.assertEqual(followups.chips(['打车'], 'zh', forbidden=('打车',)), [])
        for raw in (None, 'text', {'label': 'x'}, 7):
            self.assertEqual(followups.chips(raw, 'zh'), [])


if __name__ == '__main__':
    unittest.main()
