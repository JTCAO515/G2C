"""Offline #860 schema/semantic examples. No publisher or provider admission."""
from copy import deepcopy
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker
from cj_trip.structured_v2 import validate_document as validate_legacy_fields
from cj_trip.structured import validate_document as validate_legacy_v1
from cj_trip.domain import packed

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SCHEMA = json.loads((HERE / 'structured-schema.3.json').read_bytes())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())


def validate(document):
    """Contract shape and calendar consistency only, never source truth or authority."""
    VALIDATOR.validate(document)
    days = document['days']
    indices = [d['day_index'] for d in days]
    if any(type(i) is not int for i in indices) or indices != list(range(1, len(days) + 1)):
        raise ValueError('contiguous explicit integer day indices required')
    calendar = document['calendar']
    dated = calendar['state'] == 'dated'
    if dated:
        start = date.fromisoformat(calendar['start_date'])
        try:
            expected = [(start + timedelta(days=i-1)).isoformat() for i in indices]
        except OverflowError:
            raise ValueError('calendar date overflow') from None
        if [d['date'] for d in days] != expected:
            raise ValueError('calendar day mapping mismatch')
    items = document['items']
    legacy = dict(content_version='structured.2', title=document['title'],
                  sources=document['sources'], items=[])
    for item in items:
        converted = deepcopy(item)
        for edge in ('start', 'end'):
            event = item['schedule'][edge]
            index = event['day_index']
            if type(index) is not int or index not in indices:
                raise ValueError('schedule day outside calendar')
            if not dated and event['utc_offset']['state'] == 'known':
                raise ValueError('undated offset cannot claim a resolved instant')
            converted['schedule'][edge] = {k: v for k, v in event.items() if k != 'day_index'}
            converted['schedule'][edge]['date'] = (dict(state='known', value=days[index-1]['date'])
                                                   if dated else dict(state='unknown'))
        legacy['items'].append(converted)
    # Reuse the unchanged v2 field/source grammar, on a local validation-only copy.
    # The copied document is never stored, published or returned as another version.
    validate_legacy_fields(legacy)
    item_ids = {i['id'] for i in items}
    checks = document['date_checks']
    if {c['kind'] for c in checks} != {'weather', 'day_opening'}:
        raise ValueError('both date-dependent check kinds required exactly once')
    for check in checks:
        if (any(type(i) is not int or i not in indices for i in check['day_indices'])
                or not set(check['item_ids']) <= item_ids):
            raise ValueError('date-check reference outside document')
        if not dated:
            if (check['state'] != 'not_checked' or check['reason'] != 'date_not_set'
                    or check['evidence_refs']):
                raise ValueError('undated checks must remain explicitly unconfirmed')
        elif check['state'] == 'not_checked':
            raise ValueError('dated checks need an explicit result or unknown')
        elif check['state'] in ('clear', 'conflict') and not check['evidence_refs']:
            raise ValueError('date-dependent claim needs original evidence references')


def materialize(fixtures, case):
    value = deepcopy(fixtures['dated' if case.get('dated') else 'base'])
    for change in case['changes']:
        parent = value
        for part in change['path'][:-1]:
            parent = parent[part]
        if change.get('delete'):
            del parent[change['path'][-1]]
        else:
            parent[change['path'][-1]] = deepcopy(change['value'])
    return value


def validate_read(document):
    schema = json.loads((HERE / 'structured-read-schema.2.json').read_bytes())
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(document)
    trip = document.get('trip')
    if trip is not None:
        content = trip['content']
        {'structured.1': validate_legacy_v1, 'structured.2': validate_legacy_fields,
         'structured.3': validate}[content['content_version']](content)
        if hashlib.sha256(packed(content)).hexdigest() != trip['content_sha256']:
            raise ValueError('detail content hash mismatch')


class ContractChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = json.loads((HERE / 'structured-examples.3.json').read_bytes())

    def test_schema_and_dated_undated_without_mutating_input(self):
        Draft202012Validator.check_schema(SCHEMA)
        for name in ('base', 'dated'):
            value = deepcopy(self.fixtures[name])
            original = deepcopy(value)
            validate(value)
            self.assertEqual(value, original)
        for case in self.fixtures['schema_accept']:
            with self.subTest(case=case['name']):
                value = materialize(self.fixtures, case)
                original = deepcopy(value)
                validate(value)
                self.assertEqual(value, original)

    def test_mixed_fields_and_invalid_shapes_reject(self):
        for case in self.fixtures['schema_reject']:
            with self.subTest(case=case['name']):
                self.assertTrue(list(VALIDATOR.iter_errors(materialize(self.fixtures, case))))

    def test_semantic_constraints_are_not_claimed_by_json_schema(self):
        for case in self.fixtures['semantic_reject']:
            with self.subTest(case=case['name']):
                value = materialize(self.fixtures, case)
                VALIDATOR.validate(value)
                with self.assertRaises(ValueError):
                    validate(value)

    def test_old_frozen_contract_bytes_unchanged(self):
        for path, digest in self.fixtures['frozen_files_sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest, path)

    def test_new_read_projection_and_old_content_examples(self):
        schema = json.loads((HERE / 'structured-read-schema.2.json').read_bytes())
        examples = json.loads((HERE / 'structured-read-examples.2.json').read_bytes())
        Draft202012Validator.check_schema(schema)
        checker = Draft202012Validator(schema, format_checker=FormatChecker())
        for case in examples['positive']:
            with self.subTest(case=case['name']):
                validate_read(case['value'])
        for case in examples['negative']:
            with self.subTest(case=case['name']):
                self.assertTrue(list(checker.iter_errors(case['value'])))
        for case in examples['semantic_reject']:
            with self.subTest(case=case['name']):
                checker.validate(case['value'])
                with self.assertRaises(ValueError):
                    validate_read(case['value'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
