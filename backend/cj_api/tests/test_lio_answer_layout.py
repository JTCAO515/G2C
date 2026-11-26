"""One-screen layout switch, per-answer layout and fixed follow-up actions (W2-1, #1727). No wire, no model."""
import os
import unittest
from unittest import mock

from cj_api import lio_answer_layout as layout
from cj_message import lio_followups as followups
from cj_message.lio_context import answer_prompt

ACCEPTS = ['LIO-answer-followups.1']
LISTED = '["G2C@01","G2C@07"]'


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
            self.assertEqual(layout.subjects(), frozenset({'G2C@01', 'G2C@07'}))
        for bad in ('', 'null', '[]', '{}', '"G2C@01"', '["G2C@00"]', '["G2C@100"]', '["G2C@01","G2C@01"]',
                    '["g2c@01"]', '[1]', '["G2C@01", null]', '["G2C@01 "]', 'nope'):
            with self.subTest(bad=bad), env('one-screen', bad):
                with self.assertRaises(ValueError):
                    layout.subjects()
        with env('one-screen'):
            with self.assertRaises(ValueError):
                layout.subjects()  # the list variable is required once the switch is on

    def test_layout_needs_all_three_conditions(self):
        with env('one-screen', LISTED):
            self.assertEqual(layout.layout_for('G2C@01', accepts=ACCEPTS), 'split')
            self.assertEqual(layout.layout_for('G2C@02', accepts=ACCEPTS), 'single')  # not listed
            self.assertIsNone(layout.layout_for('G2C@01', accepts=None))              # did not declare
            self.assertIsNone(layout.layout_for('G2C@01', accepts=['LIO-answer-followups.9']))
            self.assertIsNone(layout.layout_for('G2C@01', accepts='LIO-answer-followups.1'))
        with env('flat'):
            self.assertEqual(layout.layout_for('G2C@01', accepts=ACCEPTS), 'single')  # switch off, declared
            self.assertIsNone(layout.layout_for('G2C@01', accepts=[]))

    def test_routes_the_code_writes_itself_are_one_bubble_and_emergencies_split(self):
        with env('one-screen', LISTED):
            for route in sorted(layout.SINGLE_ROUTES):
                self.assertEqual(layout.layout_for('G2C@01', accepts=ACCEPTS, route=route), 'single', route)
            self.assertEqual(layout.layout_for('G2C@01', accepts=ACCEPTS, route='answer'), 'split')
            with self.assertRaises(ValueError):
                layout.layout_for('G2C@01', accepts=ACCEPTS, route='emergency-ish')
            # a request that did not declare the version gets no field, whatever the route
            self.assertIsNone(layout.layout_for('G2C@01', accepts=None, route='greeting'))

    def test_prompt_layout_changes_the_prompt_only_for_split(self):
        self.assertEqual(layout.prompt_layout('split'), 'one-screen')
        for value in ('single', None):
            self.assertEqual(layout.prompt_layout(value), 'flat')
            self.assertEqual(answer_prompt('zh', layout=layout.prompt_layout(value)), answer_prompt('zh'))
        self.assertNotEqual(answer_prompt('zh', layout='one-screen'), answer_prompt('zh'))


class Actions(unittest.TestCase):
    def test_payment_and_taxi_questions_get_fixed_buttons(self):
        payment = followups.allowed_actions('外国游客在中国怎么用支付宝？', 'zh')
        self.assertEqual([a.wire() for a in payment],
                         [dict(tool='payment-guide', parameters={}, label='打开支付开通指南')])
        trouble = followups.allowed_actions('支付宝绑卡失败了怎么办', 'zh')
        self.assertEqual([a.label for a in trouble], ['打开支付开通指南', '支付遇到问题'])
        self.assertEqual(trouble[1].parameters, {'section': 'troubleshooting'})
        english = followups.allowed_actions('How do I pay with Alipay? My Visa was declined', 'en')
        self.assertEqual([a.label for a in english], ['Payment setup guide', 'Payment problems'])
        taxi = followups.allowed_actions('怎么打车去机场', 'zh')
        self.assertEqual([a.wire() for a in taxi], [dict(tool='taxi', parameters={}, label='打车')])
        self.assertEqual(followups.allowed_actions('Where can I get a taxi?', 'en')[0].label, 'Get a taxi')

    def test_other_questions_get_no_buttons(self):
        for question in ('成都有什么必吃的？', 'What is the weather in Beijing?', '你好'):
            self.assertEqual(followups.allowed_actions(question, 'zh'), [])

    def test_taxi_destination_comes_only_from_server_evidence(self):
        place = followups.Destination('故宫博物院', '116.397026,39.918058', '景山前街4号', 'The Palace Museum')
        action, = followups.allowed_actions('怎么打车去故宫', 'zh', destination=place)
        self.assertEqual(action.label, '打车去这里')
        self.assertEqual(action.parameters, {'destination_name_zh': '故宫博物院', 'destination_location': '116.397026,39.918058',
                                             'destination_address_zh': '景山前街4号', 'destination_name_en': 'The Palace Museum'})
        # No coordinate, or one outside China or with too many decimals: the plain taxi page.
        for location in ('', '116.397026', '2.0,39.9', '116.4,60.0', '116.3970261,39.9', '0,0', 'x,y'):
            with self.subTest(location=location):
                action, = followups.allowed_actions('打车去故宫', 'zh', destination=followups.Destination('故宫', location))
                self.assertEqual((action.label, action.parameters), ('打车', {}))
        bare = followups.Destination('故宫博物院', '116.397026,39.918058')
        self.assertNotIn('destination_name_en', followups.allowed_actions('打车去故宫', 'zh', destination=bare)[0].parameters)

    def test_trip_button_only_when_nothing_better_and_the_trip_is_saved(self):
        self.assertEqual(followups.allowed_actions('我的行程呢', 'zh', saved_trip_id='trip_A-1')[0].wire(),
                         dict(tool='trip', parameters={'trip_id': 'trip_A-1'}, label='查看行程'))
        self.assertEqual(followups.allowed_actions('我的行程呢', 'zh'), [])
        self.assertEqual(followups.allowed_actions('我的行程呢', 'zh', saved_trip_id='bad id'), [])
        self.assertEqual(followups.allowed_actions('我的行程呢', 'zh', saved_trip_id='x' * 129), [])

    def test_at_most_two_buttons_and_labels_fit_the_limits(self):
        place = followups.Destination('故宫', '116.4,39.9')
        actions = followups.allowed_actions('支付宝失败了，怎么打车去故宫', 'zh', destination=place)
        self.assertEqual(len(actions), 2)
        for locale, cap in (('zh', 12), ('en', 24)):
            index = 0 if locale == 'zh' else 1
            for label in followups.LABELS.values():
                self.assertLessEqual(len(label[index]), cap)

    def test_parameter_rules_match_the_app_registry(self):
        check = followups.checked_parameters
        self.assertEqual(check('payment-guide', {}), {})
        self.assertEqual(check('payment-guide', {'section': 'troubleshooting'}), {'section': 'troubleshooting'})
        for tool, parameters in (
                ('payment-guide', {'section': 'other'}), ('payment-guide', {'x': 'y'}), ('unknown', {}),
                ('trip', {}), ('trip', {'trip_id': ''}), ('trip', {'trip_id': 'a b'}), ('trip', {'trip_id': 1}),
                ('taxi', {'destination_name_zh': '故宫'}),  # a name without a coordinate
                ('taxi', {'destination_location': '116.4,39.9'}),
                ('taxi', {'destination_name_zh': '故宫', 'destination_location': 'bad'}),
                ('taxi', {'destination_name_zh': '故宫\n', 'destination_location': '116.4,39.9'}),
                ('taxi', {'destination_name_zh': 'x' * 201, 'destination_location': '116.4,39.9'}),
                ('taxi', {'destination_name_zh': '   ', 'destination_location': '116.4,39.9'}),
                ('trip', 'trip_id=1'), ('trip', None)):
            with self.subTest(tool=tool, parameters=parameters):
                self.assertIsNone(check(tool, parameters))
        self.assertEqual(check('taxi', {'destination_name_zh': ' 故宫 ', 'destination_location': '116.4,39.9'}),
                         {'destination_name_zh': '故宫', 'destination_location': '116.4,39.9'})

    def test_the_model_can_only_pick_from_the_offered_list(self):
        offered = followups.allowed_actions('支付宝失败了', 'zh')
        self.assertEqual(followups.pick_actions(offered, [1]), [offered[1]])
        self.assertEqual(followups.pick_actions(offered, [1, 1, 0, 0]), [offered[1], offered[0]])
        for chosen in ([2], [-1], ['0'], [True], [None], 0, 'all', None, [{'tool': 'taxi'}]):
            with self.subTest(chosen=chosen):
                self.assertEqual(followups.pick_actions(offered, chosen), [])

    def test_chips_are_bounded_and_clean(self):
        self.assertEqual(followups.chips(['付不了怎么办', '哪些地方不能用', '怎么开通地铁码', '第四个'], 'zh'),
                         ['付不了怎么办', '哪些地方不能用', '怎么开通地铁码'])
        self.assertEqual(followups.chips(['这个追问的长度超过了十二个字的上限', '好'], 'zh'), ['好'])
        # 28 characters is over the English limit of 24; a repeat is dropped.
        self.assertEqual(followups.chips(['What if my card is declined?', 'Short one', 'Short one'], 'en'), ['Short one'])
        self.assertEqual(followups.chips(['a\nb', '正常', '', 5, None, '  多  余   空格  '], 'zh'), ['正常', '多 余 空格'])
        self.assertEqual(followups.chips(['打车'], 'zh', forbidden=('打车',)), [])
        for raw in (None, 'text', {'label': 'x'}, 7):
            self.assertEqual(followups.chips(raw, 'zh'), [])


if __name__ == '__main__':
    unittest.main()
