"""Health and religion never become a memory candidate (#2000, M-2). Candidate discovery only: no wire, no model."""
import unittest
from types import SimpleNamespace

from cj_api.lio_memory_preferences import (PREFERENCE_SLOTS, allows_pilot_preference_write, explicit_pilot_preference,
                                           explicit_pilot_preferences, sensitive, supported_preference)

HEALTH = (
    '我对花生过敏', '我有哮喘，喜欢慢节奏的旅行', '我有糖尿病所以不吃甜口', '我需要坐轮椅，喜欢安静的酒店', '我行动不便',
    '我怀孕了，想要轻松的行程', '我每天要吃药，喜欢慢节奏', '我有心脏病，不能走太多路', '我对乳糖不耐受', '我不能吃麸质',
    '我有抑郁症，喜欢安静的入口', '我是视障人士', '我需要拐杖，每天只去两个景点', '我正在康复期，喜欢慢节奏的旅行',
    'I am allergic to peanuts', 'I have asthma, I prefer slow trips', 'I have diabetes so no sweet food', 'I use a wheelchair, I like quiet hotels',
    'I am pregnant and prefer relaxed trips', 'I take medication every day, I prefer slow trips', 'I have a heart condition',
    'I am lactose intolerant', 'I cannot eat gluten', 'I have a disability and like quiet hotels', 'I have limited mobility, I prefer slow trips',
    'I am recovering from surgery and prefer slow trips', 'I have anxiety disorder, I like quiet entrances', 'I need a walking stick',
)
RELIGION = (
    '我是穆斯林，只吃清真食物', '我信佛，不吃荤', '我是基督徒，周日要做礼拜', '我是犹太人，只吃洁食', '斋月期间我白天不吃东西',
    '我不吃猪肉', '我不吃牛肉，喜欢博物馆', '我吃素', '我是素食者', '我信仰伊斯兰教，喜欢慢节奏的旅行', '我要祷告，喜欢安静的酒店',
    'I am Muslim and only eat halal food', 'I am Buddhist, I prefer slow trips', 'I am Christian and go to church on Sundays',
    'I keep kosher', 'I fast during Ramadan', "I don't eat pork", 'I never eat beef, I like museums', 'I am vegetarian', 'I am vegan and prefer quiet hotels',
    'My religion matters to me, I prefer slow trips', 'I need a prayer room, I like quiet hotels', 'I am Hindu and like museums',
)
FINE = (
    ('我喜欢慢节奏的旅行', 'travel.pace'), ('我喜欢博物馆', 'travel.interests'), ('I prefer slow trips', 'travel.pace'),
    ('I like museums', 'travel.interests'), ('我喜欢住安静的酒店', 'lodging.style'), ('I like quiet hotels', 'lodging.style'),
    ('我喜欢粤菜', 'diet.taste'), ('我喜欢佛山美食', None),   # 佛山 is a city, not a faith
)
SLOTS = PREFERENCE_SLOTS - {'diet.spicy', 'quiet.entrance'}


def entry(slot, text, quote=None):
    return SimpleNamespace(slot=slot, kind='preference', text=text, evidence=[SimpleNamespace(quote=quote or text)])


class Sensitive(unittest.TestCase):
    def test_health_and_religion_statements_are_recognised(self):
        for text in HEALTH + RELIGION:
            with self.subTest(text=text):
                self.assertTrue(sensitive(text))

    def test_ordinary_travel_taste_is_not(self):
        for text, _ in FINE:
            with self.subTest(text=text):
                self.assertFalse(sensitive(text))
        for text in ('我想去故宫', 'Where is the Temple of Heaven?', '我喜欢吃辣', 'I like spicy food', '我不吃辣', 'I prefer quiet entrances'):
            self.assertFalse(sensitive(text), text)

    def test_non_text_is_treated_as_sensitive(self):
        for value in (None, 7, b'x', ['a']):
            self.assertTrue(sensitive(value))

    def test_zero_candidates_from_every_gate_for_a_sensitive_turn(self):
        for text in HEALTH + RELIGION:
            with self.subTest(text=text):
                self.assertIsNone(explicit_pilot_preference(text, SLOTS))
                self.assertIsNone(explicit_pilot_preferences(text, SLOTS, max_entries=4))
                for slot in PREFERENCE_SLOTS:
                    self.assertFalse(supported_preference(entry(slot, text), text))
                    self.assertFalse(allows_pilot_preference_write(SimpleNamespace(slot=slot, kind='preference', text=text)))

    def test_a_model_entry_cannot_smuggle_a_sensitive_turn_through_a_clean_quote(self):
        # the extractor proposes a clean entry, but the traveler's whole turn says something sensitive
        for original in ('我喜欢慢节奏的旅行。我对花生过敏。', 'I prefer slow trips. I am allergic to peanuts.', 'I like museums. I am Muslim.',
                         '我喜欢博物馆，我是佛教徒'):
            with self.subTest(original=original):
                clean = entry('travel.pace' if 'slow' in original or '慢' in original else 'travel.interests',
                              'I prefer slow trips' if 'slow' in original else '我喜欢慢节奏的旅行' if '慢' in original else 'I like museums' if 'museums' in original else '我喜欢博物馆')
                self.assertFalse(supported_preference(clean, original))

    def test_a_sensitive_entry_text_or_evidence_is_refused_even_in_a_clean_turn(self):
        bad_quote = entry('travel.pace', 'I prefer slow trips', quote='I have asthma')
        self.assertFalse(supported_preference(bad_quote, 'I prefer slow trips'))
        bad_text = entry('travel.pace', 'I prefer slow trips because of my asthma', quote='I prefer slow trips')
        self.assertFalse(supported_preference(bad_text, 'I prefer slow trips'))

    def test_ordinary_preferences_still_produce_candidates(self):
        for text, slot in FINE:
            if slot is None:
                continue
            with self.subTest(text=text):
                self.assertEqual(explicit_pilot_preference(text, SLOTS), (slot, text))
                self.assertTrue(supported_preference(entry(slot, text), text))

    def test_the_slot_whitelist_has_no_health_or_religion_slot(self):
        for slot in PREFERENCE_SLOTS:
            self.assertFalse(any(word in slot for word in ('health', 'allerg', 'religion', 'faith', 'halal', 'medical', 'disab')), slot)


if __name__ == '__main__':
    unittest.main()
