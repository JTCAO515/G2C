"""A read-only preview must describe the same day activities shown to the traveler."""
from dataclasses import replace
from datetime import date
import json
import unittest

from cj_api.lio_itinerary_preview import read_preview
from cj_api.local_lio_planning import PlanningTurn, discuss
from cj_run.core import Binding, State


class DiscussionWorker:
    memory_run = None
    message_context = None
    provider = None

    def __init__(self, packet):
        self.packet = packet
        self.calls = []

    def _registered_stream(self, binding, key, registration, argument, **kwargs):
        self.calls.append((key, registration))
        return iter((json.dumps(self.packet, ensure_ascii=False),))

    def _event(self, binding, state, kind, value=''):
        if kind == 'text_delta':
            return replace(state, text=state.text + value)
        if kind == 'effect_committed':
            return replace(state, effects=(*state.effects, value))
        return replace(state, status=kind)


class ItineraryPreview(unittest.TestCase):
    def run_discussion(self, packet, locale, question, destination, *, days=3):
        binding = Binding('scope', 'conversation', 'generation', 'message', 'run', 1)
        worker = DiscussionWorker(packet)
        state = discuss(worker, binding, State(binding, status='running'), locale,
                        (PlanningTurn(question, date(2026, 11, 21)),), (),
                        day_count=days, destination=destination)
        self.assertEqual(worker.calls, [('model.lio_discussion.0', 'model.answer')])
        self.assertEqual(state.status, 'completed')
        self.assertFalse(state.trip_proposal_published)
        return state

    def test_same_model_plan_drives_visible_days_and_read_only_preview(self):
        for locale, question, city, names, day_one in (
            ('zh', '北京三日游', '北京', ('故宫博物院', '慕田峪长城', '颐和园'), '第1天：上午参观故宫博物院。'),
            ('en', 'Three days in Beijing', 'Beijing', ('Forbidden City', 'Mutianyu Great Wall', 'Summer Palace'),
             'Day 1: Morning: Visit Forbidden City.'),
        ):
            with self.subTest(locale=locale):
                days = [dict(day_index=i, activities=[dict(place_name=name, verb='visit', period='morning')])
                        for i, name in enumerate(names, 1)]
                state = self.run_discussion(dict(answer='Which place would you like to see?', days=days),
                                            locale, question, city)
                self.assertIn(day_one, state.text)
                self.assertNotIn('Which place would you like to see?', state.text)
                self.assertEqual(read_preview(state, locale), dict(destination=None, days=[
                    dict(day_index=i, activities=[dict(place_name=name, cancelled=False)])
                    for i, name in enumerate(names, 1)]))
                self.assertIsNone(read_preview(replace(state, text=state.text + ' changed'), locale))
                prefix, payload = state.effects[0].split(':', 1)
                changed = json.loads(payload)
                changed['days'][0]['activities'][0]['place_name'] = 'Different place'
                tampered = replace(state, effects=(prefix+':'+json.dumps(changed), *state.effects[1:]))
                self.assertIsNone(read_preview(tampered, locale))
                for status in ('running', 'unknown', 'failed'):
                    self.assertIsNone(read_preview(replace(state, status=status), locale))

    def test_missing_or_invalid_days_keep_the_model_answer(self):
        answer = 'Visit the Forbidden City, the Great Wall and the Summer Palace over three days.'
        first = dict(day_index=1, activities=[dict(place_name='Forbidden City', verb='visit', period=None)])
        for packet in (dict(answer=answer), dict(answer=answer, days=[first]),
                       dict(answer=answer, days=[first, first, first]), dict(answer=answer, days='Day 1: Forbidden City'),
                       dict(answer=answer, metadata={'city_adcode': '110000'})):
            with self.subTest(packet=packet):
                state = self.run_discussion(packet, 'en', 'Three days in Beijing', 'Beijing')
                self.assertTrue(state.text.endswith(answer))
                self.assertIsNone(read_preview(state, 'en'))

    def test_model_cannot_supersede_place_authority_or_include_hidden_activities(self):
        answer = 'Visit the Forbidden City on your first day.'
        days = [dict(day_index=1, activities=[dict(place_name='Forbidden City', verb='visit', period=None)])]
        for field, value in (('city_adcode', '110000'), ('cancelled', True)):
            with self.subTest(field=field):
                activity = dict(days[0]['activities'][0], **{field: value})
                state = self.run_discussion(dict(answer=answer, days=[dict(days[0], activities=[activity])]),
                                            'en', 'One day in Beijing', 'Beijing', days=1)
                self.assertIsNone(read_preview(state, 'en'))
                self.assertTrue(state.text.endswith(answer))
