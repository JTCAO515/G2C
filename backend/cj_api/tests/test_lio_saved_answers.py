"""Saved itinerary follow-ups read protected snapshots without authorizing edits."""
from datetime import date
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from cj_api.lio_exploration_profile import Original
from cj_api.local_lio_exploration import ExplorationPlanning, SAVED_REFERENCE_DATA, UNDERSTANDING
from cj_api.local_lio_exploration_profile import ProfileView
from cj_message.demo_dialogue import LIO_VERSION_V4
from cj_message.lio_context import LioOriginal
from cj_trip.domain import Denied, packed
from test_lio_pipeline_compilation import build, prepared


class SavedAnswers(unittest.TestCase):
    def setup_details(self, current, text):
        planner = ExplorationPlanning(None, SimpleNamespace(), generation=object())
        view = SimpleNamespace(profile={}, references=('current-original',), originals=(Original('current', 1, text),))
        planner.profiles = SimpleNamespace(read=Mock(return_value=view))
        planner._model = Mock(side_effect=AssertionError('saved detail request entered a new questionnaire'))
        planner._finish = lambda worker, binding, state, body, *args: body
        active = []

        def read(binding, invoke):
            active.append(True)
            try:
                return object(), invoke()
            finally:
                active.pop()

        def saved(binding):
            self.assertTrue(active)
            if isinstance(current, Exception):
                raise current
            return current

        planner.current = Mock(side_effect=saved)
        answer = Mock(return_value=iter(['A read-only answer.']))
        worker = SimpleNamespace(_step=read, memory_run=None, tools=SimpleNamespace(answer=answer),
                                 runs=SimpleNamespace(snapshot=lambda _: object()))
        return planner, worker, answer

    def test_saved_detail_uses_exact_saved_items_and_no_new_questionnaire(self):
        document = build(prepared()).document
        current = SimpleNamespace(trip=SimpleNamespace(trip_id='private-trip-id', content=packed(document)))
        for locale, text in (('zh', '具体的行程呢'), ('en', 'What is the detailed itinerary?')):
            with self.subTest(locale=locale):
                planner, worker, answer = self.setup_details(current, text)
                result = planner.execute(worker, 'binding', 'state', text, LioOriginal(locale, date(2026,11,20), LIO_VERSION_V4))
                self.assertEqual(result, 'A read-only answer.')
                planner._model.assert_not_called()
                messages = answer.call_args.args[2]
                supplied = '\n'.join(message['content'] for message in messages)
                snapshot, = (m for m in messages if m['content'].startswith(SAVED_REFERENCE_DATA))
                self.assertEqual(snapshot['role'], 'user')
                self.assertIn(document['items'][0]['text'], supplied)
                self.assertIn('duration_seconds', supplied)
                self.assertNotIn('private-trip-id', supplied)
                self.assertNotIn(document['items'][0]['id'], supplied)
                self.assertEqual(messages[-1], dict(role='user', content=text))
                self.assertEqual(answer.call_args.kwargs['message_refs'], ('current-original',))

    def test_denied_saved_read_does_not_dispatch_model(self):
        text = 'What is the detailed itinerary?'
        error = Denied('read denied')
        planner, worker, answer = self.setup_details(error, text)
        with self.assertRaises(Denied) as caught:
            planner.execute(worker, 'binding', 'state', text, LioOriginal('en', date(2026,11,20), LIO_VERSION_V4))
        self.assertIs(caught.exception, error)
        answer.assert_not_called()

    def test_unrelated_continuation_does_not_load_saved_details(self):
        document = build(prepared()).document
        current = SimpleNamespace(trip=SimpleNamespace(content=packed(document)))
        for locale, previous, text in (('zh','地铁怎么付费？','继续'),('en','How do I pay for the subway?','Continue')):
            with self.subTest(locale=locale):
                planner, worker, answer = self.setup_details(current, text)
                view = ProfileView(originals=(Original('previous',1,previous), Original('current',2,text)),
                                   references=('current-original',), profile={}, signature='fixture')
                planner.profiles.read.return_value = view
                planner.profiles.accept = Mock(return_value=('state',view.profile))
                planner._phase = Mock(return_value='before_trip')
                planner._model = Mock(return_value=json.dumps(dict(version=UNDERSTANDING,intent='practical',
                                                                  current_source_index=1,updates=[])))
                result = planner.execute(worker,'binding','state',text,LioOriginal(locale,date(2026,11,20),LIO_VERSION_V4))
                self.assertEqual(result,'A read-only answer.')
                planner._model.assert_called_once()
                planner.current.assert_not_called()
                messages = answer.call_args.args[2]
                self.assertFalse(any(m['content'].startswith(SAVED_REFERENCE_DATA) for m in messages))

    def test_compact_reference_preserves_saved_clocks_and_all_legs(self):
        from cj_api.local_lio_exploration import saved_trip_reference
        from test_lio_pipeline_document import build as document_for

        document, _, _, _ = document_for(12)
        current = SimpleNamespace(trip=SimpleNamespace(content=packed(document)))
        value = saved_trip_reference(current)
        supplied = [dict(zip(value['item_columns'], item, strict=True)) for day in value['days'] for item in day['items']]
        self.assertEqual(len(supplied), 60)
        self.assertEqual(len(value['legs']), len(document['legs']))
        for projected, original in zip(supplied, document['items'], strict=True):
            self.assertEqual(projected['text'], original['text'])
            for edge in ('start', 'end'):
                day, clock, context = projected[edge]
                expanded = dict(day_index=day, time=value['time_values'][clock], **value['clock_contexts'][context])
                self.assertEqual(expanded, original['schedule'][edge])
        encoded = json.dumps(json.dumps(value, ensure_ascii=False, separators=(',',':')), ensure_ascii=False).encode()
        self.assertLess(len(encoded), 22000)
