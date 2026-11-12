"""Approved #842 voice rules and user-visible disclosure boundaries."""
from types import SimpleNamespace
import unittest

from cj_api.lio_dialogue_routes import _message
from cj_message.lio_context import PERSONA, answer_prompt, display_answer
from cj_message.lio_timeline import TimelineMessage


class LioVoice(unittest.TestCase):
    def test_voice_tiers_and_helpful_uncertainty_are_explicit(self):
        self.assertLessEqual(len(PERSONA.split()), 450)
        for clause in (
            'foreign-passport visitor', 'Chinese ID card', 'Chinese phone number',
            'WeChat Pay or Alipay', '30 Chinese characters or 20 English words',
            '80 characters or 50 words', '150 characters or 90 words', 'at most 3 list items',
            'Count the closing question', 'do not count towards English word limits',
            'first answer what you can', 'once in the first person', 'keep helping',
            'The app handles saving', 'end with one specific question',
            'Chinese name in bold', 'omit unknown names', '110 (police)', '120 (ambulance)',
            '我综合了地图、天气等多方面的信息', 'I combine maps, weather and other trusted information',
        ):
            with self.subTest(clause=clause):
                self.assertIn(clause, PERSONA)
        for term in ('noted', '记住了', '记下了'):
            self.assertNotIn(term, PERSONA.casefold())
        for locale, ending in (('zh', 'Reply in Chinese.'), ('en', 'Reply in English.')):
            self.assertEqual(answer_prompt(locale), PERSONA + ' ' + ending)

    def test_coordinate_pairs_fail_closed_at_the_timeline(self):
        for text in (
            '位置：(116.397, 39.908)。', '坐标39.908，116.397。',
            'Meet at -33.8688, 151.2093.', 'The location is 39.908/116.397.',
            'latitude: 39.9, longitude: 116.4', 'lng=116.4; lat=39.9',
            '{"lat":39,"lng":116}', '纬度：40，经度：116',
            'longitude 116.4 latitude 39.9', '北纬40度，东经116度',
        ):
            for locale in ('zh', 'en'):
                with self.subTest(text=text, locale=locale):
                    original = SimpleNamespace(status='completed', text=text, draft_outcome=None,
                                               effects=(), budget_exhausted_stage='none')
                    entry = TimelineMessage('coordinate-test', 'original', 1, 'How do I get there?', locale)
                    shown = _message(entry, original)
                    self.assertEqual((shown['status'], shown['answer']), ('failed', ''))
                    self.assertEqual(original.text, text)

    def test_internal_identifiers_are_not_user_visible(self):
        for text in (
            'trip_id=original', 'job_id=original', 'attempt_id=original',
            'operation_id=original', 'candidate_id=original', 'source_id=original',
            'input_sha256=original', 'Original 12345678-1234-1234-1234-123456789abc',
            'The RUN has run_id=original', '规划候选在原运行中',
        ):
            with self.subTest(text=text):
                self.assertIsNone(display_answer(text, 'en'))

    def test_supplier_interfaces_include_ports_and_query_only_urls(self):
        for address in (
            'https://restapi.amap.com/v3/weather/weatherInfo?key=synthetic',
            'https://restapi.amap.com:443?key=synthetic',
            'https://dashscope.aliyuncs.com/compatible-mode/v1',
            'https://dashscope-intl.aliyuncs.com:443/api/v1?key=synthetic',
            'https://api-beta.go2china.space/v1/lio/messages?key=synthetic',
        ):
            for locale, replacement in (('zh', '服务方'), ('en', 'the service provider')):
                with self.subTest(address=address, locale=locale):
                    self.assertEqual(display_answer('Read ' + address + ' please', locale),
                                     'Read ' + replacement + ' please')

    def test_normal_travel_text_and_existing_memory_filters_are_preserved(self):
        for text in (
            '交通工具可以选地铁，坐地铁 2 号线。', 'Metro lines 2, 3 and 4 are options.',
            '成人票39.90元，儿童票19.90元。', 'The alternatives cost 39.90 and 116.40 yuan.',
            '预算850.50，1200.25元。', 'https://www.nia.gov.cn/',
        ):
            self.assertEqual(display_answer(text, 'zh'), text)
        self.assertEqual(display_answer('我记住了你的偏好。', 'zh'), '我了解了你的偏好。')
        self.assertEqual(display_answer("I've noted your preference.", 'en'),
                         'I understand your preference.')


if __name__ == '__main__':
    unittest.main()
