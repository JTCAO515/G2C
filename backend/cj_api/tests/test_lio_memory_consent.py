"""#1970: memory suggestions need the account's consent, behind CJ_LIO_MEMORY_CONSENT_REQUIRED (default off)."""
import json
import os
import unittest
from types import SimpleNamespace
from unittest import mock

from cj_api import lio_memory_consent as consent
from cj_api import lio_memory_routes
from cj_api.lio_memory_routes import LioMemoryCards
from cj_api.local_lio_memory import LioMemoryExtraction
from cj_memory_jobs.codec import Conflict


def switch(value):
    return mock.patch.dict(os.environ, {'CJ_LIO_MEMORY_CONSENT_REQUIRED': value})


class Boom:
    """A consent store or collaborator that must not be touched."""
    def granted(self, scope):
        raise AssertionError('consent was read')

    def __getattr__(self, name):
        raise AssertionError('unexpected use: ' + name)


class Store:
    def __init__(self, granted):
        self.answer, self.asked = granted, []

    def granted(self, scope):
        self.asked.append(scope)
        return self.answer


PROJECTED = '{"candidates": [], "memory_epoch": 1}'


def cards(consent_store, projected=PROJECTED):
    calls = []
    context = SimpleNamespace(scope='scope-a', query_lio_message=lambda mid: calls.append('message') or SimpleNamespace(
        receipt=SimpleNamespace(run_id='r')))
    collection = SimpleNamespace(boundary=SimpleNamespace(with_history_context=lambda token, fn: fn(context)))
    result = LioMemoryCards(collection, lambda *args: calls.append('read') or projected, consent_store)
    return result, context, calls


class Switch(unittest.TestCase):
    def test_default_is_off_and_values_are_strict(self):
        with mock.patch.dict(os.environ):
            os.environ.pop('CJ_LIO_MEMORY_CONSENT_REQUIRED', None)
            self.assertFalse(consent.consent_required())
        with switch('1'):
            self.assertTrue(consent.consent_required())
        with switch('0'):
            self.assertFalse(consent.consent_required())
        for value in ('', 'true', 'on', '2', 'yes', ' 1'):
            with self.subTest(value=value), switch(value):
                with self.assertRaises(ValueError):
                    consent.consent_required()


class Request(unittest.TestCase):
    def body(self, **change):
        value = dict(version='LIO-memory-consent.1', state='granted', consent_text_version='consent-2026-11', request_id='r1')
        value.update(change)
        import json
        return json.dumps(value).encode()

    def test_a_strict_body_parses(self):
        self.assertEqual(consent.parse_request(self.body()), ('granted', 'consent-2026-11', 'r1'))
        self.assertEqual(consent.parse_request(self.body(state='withdrawn'))[0], 'withdrawn')

    def test_everything_else_is_refused(self):
        for raw in (b'', b'null', b'[]', b'{}', b'not json', '\xff'.encode('latin-1'), self.body(extra=1),
                    self.body(version='LIO-memory-consent.2'), self.body(state='GRANTED'), self.body(state=True),
                    self.body(consent_text_version=''), self.body(consent_text_version='x' * 65),
                    self.body(consent_text_version='a b'), self.body(consent_text_version=3),
                    self.body(request_id=''), self.body(request_id='x' * 129), self.body(request_id='a/b'),
                    self.body(request_id=None), b'{"version":"LIO-memory-consent.1","state":"granted","state":"withdrawn",'
                    b'"consent_text_version":"v","request_id":"r"}'):
            with self.subTest(raw=raw[:40]), self.assertRaises(ValueError):
                consent.parse_request(raw)

    def test_the_wire_shape(self):
        from datetime import datetime, timezone
        self.assertEqual(consent.wire(dict(recorded=False, state='withdrawn', consent_text_version=None, changed_at=None)),
                         dict(version='LIO-memory-consent.1', state='withdrawn', recorded=False, consent_text_version=None, changed_at=None))
        shown = consent.wire(dict(recorded=True, state='granted', consent_text_version='v1',
                                  changed_at=datetime(2026, 11, 27, 1, 2, 3, 456789, tzinfo=timezone.utc)))
        self.assertEqual(shown['changed_at'], '2026-11-27T01:02:03.456+00:00')


class Delivery(unittest.TestCase):
    def test_off_reads_nothing_and_behaves_as_before(self):
        with switch('0'):
            shown, _, calls = cards(Boom())
            self.assertIsNone(shown.project(SimpleNamespace(scope='s', query_lio_message=lambda mid: SimpleNamespace(
                receipt=SimpleNamespace(run_id='r'))), 't', 'm'))
            self.assertIsNone(cards(None)[0].project(cards(None)[1], 't', 'm'))   # no store at all is fine while off

    def test_on_without_a_store_or_consent_delivers_nothing(self):
        with switch('1'):
            for store in (None, Store(False)):
                shown, context, calls = cards(store)
                self.assertIsNone(shown.project(context, 't', 'm'))
                self.assertEqual(calls, [])                      # the message and the candidates were never read

    def test_on_with_consent_reads_the_candidates_as_before(self):
        with switch('1'):
            store = Store(True)
            shown, context, calls = cards(store)
            shown.project(context, 't', 'm')
            self.assertEqual(calls, ['message', 'read'])
            self.assertEqual(store.asked, ['scope-a'])

    def test_an_invalid_switch_value_makes_the_projection_raise(self):
        for value in ('', 'true', 'on', ' 1'):
            with self.subTest(value=value), switch(value):
                shown, context, calls = cards(Store(True))
                with self.assertRaises(ValueError):
                    shown.project(context, 't', 'm')
                self.assertEqual(calls, [])

    def test_remember_and_dismiss_are_refused_without_consent(self):
        def apply(*args):
            raise AssertionError('a suggestion was applied without consent')
        with switch('1'), mock.patch.object(lio_memory_routes, '_decode_target', lambda token: dict(message_id='m')), \
                mock.patch.object(lio_memory_routes, '_action', lambda a, o, t: ('i', b'x')):
            for store in (None, Store(False)):
                shown, _, _ = cards(store)
                shown.collection.apply_candidate = apply
                with mock.patch.object(LioMemoryCards, '_decision_exists', lambda *a: False):
                    with self.assertRaises(Conflict):
                        shown.decide('token', dict(action_id='a', operation='remember', target='t'))
                    with self.assertRaises(Conflict):
                        shown.decide('token', dict(action_id='a', operation='dismiss', target='t'))


class Generation(unittest.TestCase):
    def extraction(self, prepared):
        return LioMemoryExtraction(database=SimpleNamespace(), candidates=SimpleNamespace(prepare=prepared), credential=lambda: 'token')

    def test_without_consent_nothing_is_prepared_and_no_model_is_called(self):
        def prepare(*args, **kwargs):
            raise AssertionError('a suggestion was prepared without consent')
        worker = SimpleNamespace(_registered_stream=Boom(), provider=Boom(), budget_exit=Boom())
        binding = SimpleNamespace(scope='scope-a', message_id='m', run_id='r')
        with switch('1'), mock.patch.object(consent.ConsentStore, 'granted', lambda self, scope: False):
            self.assertIsNone(self.extraction(prepare).extract(worker, binding))

    def test_off_or_consented_goes_on_to_prepare(self):
        class Reached(Exception):
            pass

        def prepare(*args, **kwargs):
            raise Reached
        binding = SimpleNamespace(scope='scope-a', message_id='m', run_id='r')
        with switch('0'):
            with self.assertRaises(Reached):
                self.extraction(prepare).extract(SimpleNamespace(), binding)
        with switch('1'), mock.patch.object(consent.ConsentStore, 'granted', lambda self, scope: True):
            with self.assertRaises(Reached):
                self.extraction(prepare).extract(SimpleNamespace(), binding)

    def _prepared(self, consent_answers, transitions):
        """An extraction whose collaborators are fakes, and the `publish` it hands back (the model call is a fake stream)."""
        text = json.dumps(dict(slots=[], max_entries=1, max_text_bytes=200, messages=[dict(text='随便聊聊', ref='r1')]))
        model_input = json.dumps(dict(system='s', messages=[dict(role='user', content=text)])).encode()

        class Candidates:
            published = []
            collection = SimpleNamespace(boundary=SimpleNamespace(with_history_context=lambda token, operation: operation(context)))

            def prepare(self, token, **options):
                return json.dumps(dict(prepared_input_utf8='{}', job_id='j', attempt_id='a', source=dict(
                    conversation_id='c', generation='g', epoch=1, after=0, through=1, source_version=1, withdrawal_epoch=1)))

            def processing_policy(self, *args, **options):
                return SimpleNamespace(with_input=lambda snapshot, fn: model_input)

            def transition_original_in_context(self, ctx, token, job, attempt, target, **coordinates):
                transitions.append(target)

            def publication_policy(self, *args, **options):
                self.published.append('policy')
                raise AssertionError('published')

        context = SimpleNamespace(with_enabled_source=lambda source, policy, fn: fn(None))
        answers = iter(consent_answers)
        worker = SimpleNamespace(_registered_stream=lambda *args: ['{}'], provider=None,
                                 budget_exit=SimpleNamespace(prepare_publication=lambda binding: (lambda: None)))
        binding = SimpleNamespace(scope='scope-a', message_id='m', run_id='r')
        candidates = Candidates()
        extraction = LioMemoryExtraction(database=SimpleNamespace(), candidates=candidates, credential=lambda: 'token')
        with mock.patch.object(consent.ConsentStore, 'granted', lambda self, scope: next(answers)):
            publish = extraction.extract(worker, binding)
        return publish, candidates, answers

    def test_a_consent_withdrawn_while_the_suggestion_was_prepared_publishes_nothing(self):
        transitions = []
        with switch('1'):
            publish, candidates, answers = self._prepared([True, False], transitions)
            self.assertTrue(callable(publish))
            with mock.patch.object(consent.ConsentStore, 'granted', lambda self, scope: next(answers)):
                publish()
        self.assertEqual(transitions, ['failed'])                         # the original is held, never published
        self.assertEqual(candidates.published, [])

    def test_a_consent_still_granted_at_publication_goes_on_to_publish(self):
        transitions = []
        with switch('1'):
            publish, candidates, answers = self._prepared([True, True], transitions)
            with mock.patch.object(consent.ConsentStore, 'granted', lambda self, scope: next(answers)):
                with self.assertRaises(AssertionError):                     # the fake policy refuses to write: the step was reached
                    publish()
        self.assertEqual(candidates.published, ['policy'])
        self.assertEqual(transitions, [])

    def test_a_consent_that_cannot_be_read_counts_as_none(self):
        store = consent.ConsentStore(SimpleNamespace(connect=Boom()))
        self.assertFalse(store.granted('scope-a'))


class Contract(unittest.TestCase):
    def test_the_examples_match_the_schema_and_the_servers_own_parser(self):
        import json
        from pathlib import Path
        import jsonschema
        root = Path(__file__).resolve().parents[3] / 'contracts/message'
        schema = json.loads((root / 'lio-memory-consent-schema.1.json').read_text())
        examples = json.loads((root / 'lio-memory-consent-examples.1.json').read_text())
        for kind in ('request', 'response'):
            definition = dict(schema, **{'$ref': '#/$defs/' + kind})
            validator = jsonschema.Draft202012Validator(definition, format_checker=jsonschema.FormatChecker())
            for value in examples['valid_' + kind]:
                validator.validate(value)
                if kind == 'request':
                    self.assertEqual(consent.parse_request(json.dumps(value).encode()), (value['state'], value['consent_text_version'], value['request_id']))
            for value in examples['invalid_' + kind]:
                self.assertFalse(validator.is_valid(value), value)
                if kind == 'request':
                    with self.assertRaises(ValueError):
                        consent.parse_request(json.dumps(value).encode())


if __name__ == '__main__':
    unittest.main()
