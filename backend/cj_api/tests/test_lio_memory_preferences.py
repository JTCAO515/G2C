from datetime import datetime, timezone
from types import SimpleNamespace
import unittest

from cj_api.lio_memory_preferences import explicit_pilot_preference, supported_preference
from cj_api.local_lio_memory import pilot_write_configuration
from cj_memory.domain import Unavailable
from cj_memory.local import LocalMemoryConfiguration, LocalMemoryProfile, SlotPolicy
from cj_memory.typed_local import TypedConfiguration
from cj_memory_jobs.extraction import Entry, Evidence


def entry(slot, text, *, quote=None, kind='preference'):
    return Entry('self', slot, kind, text, 'long_term', 'date unknown',
                 (Evidence('original', quote if quote is not None else text),))


class LioMemoryPreferenceTest(unittest.TestCase):
    def test_common_explicit_preference_forms(self):
        for slot, text in [
            ('travel.pace', 'I always prefer a slower travel pace.'),
            ('travel.pace', '我平时喜欢慢节奏旅行。'),
            ('travel.budget', 'I prefer a budget of around 400 yuan per day.'),
            ('travel.budget', 'I usually budget 500 yuan per day when I travel.'),
            ('travel.budget', '旅行预算通常是每天400元。'),
            ('lodging.style', 'I prefer staying in central hotels.'),
            ('lodging.style', '我通常喜欢住精品酒店。'),
            ('travel.interests', 'I enjoy museums and architecture.'),
            ('travel.interests', '我喜欢博物馆和历史。'),
            ('diet.taste', 'I prefer Cantonese cuisine.'),
            ('diet.spicy', '我不吃辣。'),
            ('quiet.entrance', 'I prefer using quieter entrances at attractions.'),
        ]:
            with self.subTest(slot=slot, text=text):
                self.assertTrue(supported_preference(entry(slot, text), text))

    def test_sensitive_or_mislabeled_content_does_not_become_a_tag(self):
        for candidate in [
            entry('health.condition', 'I have asthma.', kind='fact'),
            entry('religion', 'I prefer museums.'),
            entry('travel.interests', 'I attend services because I am Catholic.'),
            entry('travel.pace', 'I prefer a slow pace because I have asthma.'),
            entry('diet.spicy', '我不吃辣，因为我有胃病。'),
            entry('travel.interests', 'I prefer museums.', quote='I am Catholic.'),
            entry('travel.pace', 'I have asthma.', quote='I prefer a slow pace.'),
            entry('travel.budget', 'My salary is 500 yuan per day.'),
        ]:
            with self.subTest(candidate=candidate):
                self.assertFalse(supported_preference(candidate, candidate.evidence[0].quote))

    def test_preference_must_match_the_actual_complete_original(self):
        text = 'I prefer a slow travel pace.'
        candidate = entry('travel.pace', 'a slow travel pace', quote=text)
        self.assertTrue(supported_preference(candidate, text))
        self.assertTrue(supported_preference(candidate, text + ' I like museums.'))
        for original in ('I never said I prefer a slow travel pace.',
                         text + ' I have asthma.',
                         text + ' I prefer a fast travel pace.',
                         'I prefer a slow travel pace because of my asthma.',
                         'I prefer a fast travel pace.'):
            with self.subTest(original=original):
                self.assertFalse(supported_preference(candidate, original))
        changed = entry('travel.pace', 'a fast travel pace', quote=text)
        self.assertFalse(supported_preference(changed, text))

    def test_explicit_remember_request_yields_the_same_preference_value(self):
        for original, quote, text in [
            ('我喜欢慢节奏。', '我喜欢慢节奏', '慢节奏旅行'),
            ('请记住，我喜欢慢节奏旅行。', '我喜欢慢节奏旅行', '慢节奏'),
            ('请记住，我旅行时喜欢慢节奏。', '我旅行时喜欢慢节奏', '慢节奏'),
            ('Please remember that I prefer a slow pace when I travel.',
             'I prefer a slow pace when I travel.', 'slow pace'),
        ]:
            with self.subTest(original=original):
                self.assertTrue(supported_preference(entry('travel.pace', text, quote=quote), original))

    def test_typed_write_policy_applies_only_to_demo_and_new_slots(self):
        preference = SlotPolicy('preference', True, True)
        profile = LocalMemoryProfile(frozenset({'self'}),
                                     {'travel.pace': preference, 'quiet.entrance': preference},
                                     frozenset({'long_term'}), frozenset(),
                                     datetime.max.replace(tzinfo=timezone.utc))
        configuration = TypedConfiguration(LocalMemoryConfiguration({'demo': profile, 'other': profile}),
                                           {'demo': frozenset(), 'other': frozenset()})
        pilot = pilot_write_configuration(configuration, frozenset({'demo'}))

        def command(slot, text):
            return SimpleNamespace(slot=slot, text=text, kind='preference', subject='self', extent='long_term')

        sensitive = command('travel.pace', 'I prefer a slow pace because I have asthma.')
        with self.assertRaises(Unavailable):
            pilot.policy('demo').evaluate(sensitive, b'')
        self.assertTrue(pilot.policy('demo').evaluate(command('travel.pace', 'I prefer a slow pace.'), b''))
        self.assertTrue(pilot.policy('demo').evaluate(command('quiet.entrance', 'Use a different quiet entrance.'), b''))
        self.assertIs(pilot.collection.profiles['other'], profile)

    def test_exact_pilot_preferences_use_the_original_quote(self):
        slots = {'travel.pace', 'quiet.entrance'}
        for original, quote in [
            ('请记住，我旅行时喜欢慢节奏。', '我旅行时喜欢慢节奏。'),
            ('Please remember that I prefer a slow pace when I travel.',
             'I prefer a slow pace when I travel.'),
        ]:
            with self.subTest(original=original):
                self.assertEqual(explicit_pilot_preference(original, slots), ('travel.pace', quote))
        for text in ('I prefer a slow pace because I have asthma.',
                     'I never said I prefer a slow pace.',
                     'I prefer a slow pace. I prefer a fast pace.',
                     'I prefer quiet entrances.'):
            with self.subTest(text=text):
                self.assertIsNone(explicit_pilot_preference(text, slots))
        self.assertIsNone(explicit_pilot_preference('I prefer a slow pace.', {'quiet.entrance'}))
