"""Offline WP7 schema/binding vectors; no actual provider or publishing admission."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import socket
import unittest
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource
from cj_trip.domain import packed
from cj_trip.rich_source import capture
from cj_trip.rich_undo import RichUndo
from cj_trip.lio_history import Undo
from cj_trip.calendar_history import CalendarUndo
from cj_trip.structured import validate_document as v1
from cj_trip.structured_v2 import validate_document as v2
from cj_trip.structured_v3 import validate_document as v3
from cj_trip.structured_v4 import validate_document as v4, validate_candidate, parse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FIXTURES = json.loads((HERE / 'structured-examples.4.json').read_bytes())
SCHEMA = json.loads((HERE / 'structured-schema.4.json').read_bytes())
READ_SCHEMA = json.loads((HERE / 'structured-read-schema.3.json').read_bytes())
SOURCE_SCHEMA = json.loads((HERE / 'rich-source-schema.1.json').read_bytes())
REGISTRY = Registry()
for name in ('structured-schema.3.json', 'structured-read-schema.2.json', 'structured-schema.4.json',
             'structured-read-schema.3.json', 'rich-source-schema.1.json'):
    resource = json.loads((HERE / name).read_bytes())
    REGISTRY = REGISTRY.with_resource(resource['$id'], Resource.from_contents(resource))
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker(), registry=REGISTRY)
READ_VALIDATOR = Draft202012Validator(READ_SCHEMA, format_checker=FormatChecker(), registry=REGISTRY)
SOURCE_VALIDATOR = Draft202012Validator(SOURCE_SCHEMA, format_checker=FormatChecker(), registry=REGISTRY)


def changed(value, changes):
    result = deepcopy(value)
    for change in changes:
        parent = result
        for part in change['path'][:-1]: parent = parent[part]
        parent[change['path'][-1]] = deepcopy(change['value'])
    return result


def validate(value, source, expected):
    VALIDATOR.validate(value)
    SOURCE_VALIDATOR.validate(source)
    validate_candidate(value, capture(packed(source), **expected))


def validate_read(value):
    READ_VALIDATOR.validate(value)
    trip = value.get('trip')
    if trip is not None:
        content = trip['content']
        {'structured.1': v1, 'structured.2': v2, 'structured.3': v3, 'structured.4': v4}[content['content_version']](content)
        if sha256(packed(content)).hexdigest() != trip['content_sha256']:
            raise ValueError('exact original content hash required')


class RichContractChecks(unittest.TestCase):
    def test_vendored_schemas_resolve_offline_and_all_positive_binding_vectors(self):
        Draft202012Validator.check_schema(SCHEMA)
        Draft202012Validator.check_schema(READ_SCHEMA)
        Draft202012Validator.check_schema(SOURCE_SCHEMA)
        for name, case in FIXTURES['cases'].items():
            with self.subTest(case=name):
                before = deepcopy(case)
                with patch.object(socket.socket, 'connect', side_effect=AssertionError('offline contracts prohibit sockets')):
                    validate(case['content'], case['source'], case['host_expected'])
                self.assertEqual(parse(packed(case['content'])), case['content'])
                self.assertEqual(before, case)

    def test_source_price_booking_adjacency_and_calendar_negatives(self):
        for case in FIXTURES['reject']:
            with self.subTest(case=case['name']):
                original = FIXTURES['cases'][case['case']]
                value = changed(original['content'], [case, *case.get('also', [])])
                with self.assertRaises((ValueError, ValidationError)):
                    validate(value, original['source'], original['host_expected'])

    def test_model_cannot_supply_actual_original_policy_or_accepted_states(self):
        case = FIXTURES['cases']['matched']
        for bad in FIXTURES['source_reject']:
            with self.subTest(case=bad['name']), self.assertRaises(ValueError):
                capture(packed(changed(case['source'], [bad])), **case['host_expected'])
        # A real old protocol is not admitted by simply making both claims old.
        source = deepcopy(case['source']); expected = deepcopy(case['host_expected'])
        source['original']['protocol'] = expected['expected_original']['protocol'] = 'LIO-message.3'
        with self.assertRaises(ValueError): capture(packed(source), **expected)
        expected = deepcopy(case['host_expected']); expected['expected_original']['protocol'] = 'LIO-message.3'
        with self.assertRaises(ValueError): capture(packed(case['source']), **expected)
        expected = deepcopy(case['host_expected']); expected['expected_plan_now'] = None
        with self.assertRaises(ValueError): capture(packed(case['source']), **expected)
        source = deepcopy(case['source']); source['plan_now'] = None
        with self.assertRaises(ValueError): capture(packed(source), **expected)

    def test_later_adjustment_preserves_the_actual_earlier_default_trigger(self):
        case = deepcopy(FIXTURES['cases']['matched'])
        old_trigger = deepcopy(case['source']['plan_now'])
        case['source']['original'].update(message_id='later-adjustment', run_id='later-run',
                                        input_sha256=sha256(b'later actual adjustment').hexdigest())
        case['host_expected']['expected_original'] = deepcopy(case['source']['original'])
        source = capture(packed(case['source']), **case['host_expected'])
        self.assertEqual(source.document['plan_now'], old_trigger)
        validate_candidate(case['content'], source)

    def test_complete_ordered_adjacency_including_explicit_hotel_endpoints(self):
        case = deepcopy(FIXTURES['cases']['unconfirmed'])
        case['content']['items'][0]['kind'] = 'hotel'
        case['content']['items'][3]['kind'] = 'transport'
        validate(case['content'], case['source'], case['host_expected'])
        for legs in (case['content']['legs'][1:], case['content']['legs'] + case['content']['legs'][:1]):
            bad = deepcopy(case['content']); bad['legs'] = legs
            with self.assertRaises(ValueError): v4(bad)

    def test_raw_coordinate_role_and_unknown_quantities_are_not_repaired(self):
        case = FIXTURES['cases']['matched']
        for path, value in [(['items', 0, 'place', 'coordinate', 'longitude'], '116.3'),
                            (['items', 0, 'place', 'coordinate_role'], 'entrance'),
                            (['legs', 0, 'distance_m'], float('nan')),
                            (['legs', 0, 'duration_seconds'], True)]:
            with self.subTest(path=path), self.assertRaises(ValueError):
                validate_candidate(changed(case['content'], [dict(path=path, value=value)]),
                                   capture(packed(case['source']), **case['host_expected']))

    def test_strict_bytes_and_legacy_decoders_remain_mutually_exclusive(self):
        value = FIXTURES['cases']['unconfirmed']['content']; raw = packed(value)
        for bad in (raw[:-1], b'{"content_version":"structured.4","content_version":"structured.3"}'):
            with self.assertRaises(ValueError): parse(bad)
        for old in (v1, v2, v3):
            with self.assertRaises(ValueError): old(value)
        old = json.loads((HERE / 'structured-examples.3.json').read_bytes())['base']
        with self.assertRaises(ValueError): v4(old)

    def test_new_read_retains_original_versions_and_exact_canonical_content_hashes(self):
        old = json.loads((HERE / 'structured-read-examples.2.json').read_bytes())
        for example in old['positive']:
            value = deepcopy(example['value']); value['version'] = 'TRIP-structured-read.3'
            validate_read(value)
        for case in FIXTURES['cases'].values():
            content = deepcopy(case['content'])
            value = dict(version='TRIP-structured-read.3', request_id='00000000-0000-4000-8000-000000000004', trip=dict(
                trip_id='synthetic-trip', version=1, content_sha256=sha256(packed(content)).hexdigest(), content=content))
            validate_read(value)
            self.assertEqual(value['trip']['content'], content)
            value['trip']['content_sha256'] = '0'*64
            with self.assertRaises(ValueError): validate_read(value)

    def test_frozen_v1_v2_v3_contracts_and_negative_vectors_are_unchanged(self):
        for path, expected in FIXTURES['frozen_files_sha256'].items():
            self.assertEqual(sha256((ROOT / path).read_bytes()).hexdigest(), expected, path)

    def test_rich_undo_new_capability_preserves_original_bytes_and_old_mutual_exclusion(self):
        schema = json.loads((HERE / 'rich-undo-schema.1.json').read_bytes())
        checker = Draft202012Validator(schema)
        Draft202012Validator.check_schema(schema)
        for version in ('structured.1', 'structured.2', 'structured.3', 'structured.4'):
            value = dict(version='TRIP-lio-undo.3', action_id='synthetic-undo', trip_id='synthetic-trip',
                         expected_version=2, original_hash='a'*64, content_version=version)
            checker.validate(value); raw = packed(value); parsed = RichUndo.parse(raw)
            self.assertEqual(parsed.raw, raw); self.assertEqual(parsed.content_version, version)
            for old in (Undo, CalendarUndo):
                with self.assertRaises(ValueError): old.parse(raw)
            for field, bad in [('original_hash', 'bad'), ('expected_version', True),
                               ('expected_version', 1), ('content_version', 'opaque')]:
                with self.assertRaises(ValueError): RichUndo.parse(packed(dict(value, **{field: bad})))
            for old_version in ('TRIP-lio-undo.1', 'TRIP-lio-undo.2'):
                with self.assertRaises(ValueError): RichUndo.parse(packed(dict(value, version=old_version)))


if __name__ == '__main__':
    unittest.main(verbosity=2)
