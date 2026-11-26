"""FACT-query.3 (#1756): an optional city; without one only nationwide entries match. v2 is unchanged."""
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from cj_fact.policy import FactFailure
from cj_fact.visitor import CITIES, Query, decode_query, decode_query_v3, lookup

ROOT = Path(__file__).resolve().parents[3]
NOW = datetime(2026, 11, 26, 4, tzinfo=timezone.utc)
ALL = sorted(CITIES)


def entry(identifier, cities, topic='payment', expires='2026-12-26'):
    return dict(id=identifier, topic=topic, cities=cities, text_zh='合成测试正文，不代表真实指引。',
                text_en='Synthetic test text, not guidance.', source_urls=['https://english.www.gov.cn/synthetic-fixture'],
                checked_on='2026-11-25', expires_on=expires)


class NationwideQuery(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory(); self.addCleanup(folder.cleanup)
        self.directory = Path(folder.name)
        (self.directory / 'entries.json').write_text(json.dumps([
            entry('visitor.fixture.nationwide', ALL),
            entry('visitor.fixture.nationwide-expired', ALL, expires='2026-11-26'),
            entry('visitor.fixture.nationwide-internet', ALL, topic='internet'),
            entry('visitor.fixture.six-cities', [c for c in ALL if c != 'shenzhen']),
            entry('visitor.fixture.chengdu-only', ['chengdu']),
        ], ensure_ascii=False))

    def read(self, raw):
        query = decode_query_v3(json.dumps(raw).encode()) if raw['version'] == 'FACT-query.3' else decode_query(json.dumps(raw).encode())
        return json.loads(lookup(self.directory, query, evaluated_at=NOW, request_ref='original-ref'))

    def test_without_a_city_only_nationwide_unexpired_entries_of_the_topic_match(self):
        result = self.read(dict(version='FACT-query.3', topic='payment'))
        self.assertEqual((result['version'], result['status']), ('FACT-result.3', 'matched'))
        self.assertEqual(result['query'], dict(version='FACT-query.3', topic='payment'))
        # Not the six-city entry, not the city-only entry, not the expired one, not another topic.
        self.assertEqual([e['id'] for e in result['entries']], ['visitor.fixture.nationwide'])

    def test_with_a_city_v3_matches_exactly_what_v2_matches(self):
        for city in ('成都', 'Chengdu', '510100', '广州'):
            with self.subTest(city=city):
                v2 = self.read(dict(version='FACT-query.2', topic='payment', city=city))
                v3 = self.read(dict(version='FACT-query.3', topic='payment', city=city))
                self.assertEqual(v2['version'], 'FACT-result.2'); self.assertEqual(v3['version'], 'FACT-result.3')
                self.assertEqual(v3['query'], dict(version='FACT-query.3', topic='payment', city=city))
                self.assertEqual((v3['status'], v3['entries']), (v2['status'], v2['entries']))
        chengdu = self.read(dict(version='FACT-query.3', topic='payment', city='chengdu'))
        self.assertEqual([e['id'] for e in chengdu['entries']],
                         ['visitor.fixture.chengdu-only', 'visitor.fixture.nationwide', 'visitor.fixture.six-cities'])

    def test_no_nationwide_entry_is_no_match_not_a_default_city(self):
        result = self.read(dict(version='FACT-query.3', topic='emergency'))
        self.assertEqual((result['status'], result['entries']), ('no_match', []))

    def test_v3_decoder_is_strict_and_v2_still_requires_a_city(self):
        self.assertEqual(decode_query_v3(b'{"version":"FACT-query.3","topic":"payment"}'), Query('payment', None, 'FACT-query.3'))
        for bad in (dict(version='FACT-query.3', topic='payment', city=''), dict(version='FACT-query.3', topic='payment', city=None),
                    dict(version='FACT-query.2', topic='payment'), dict(version='FACT-query.3', topic='visa'),
                    dict(version='FACT-query.3', topic='payment', owner='foreign'), dict(version='FACT-query.3')):
            with self.subTest(value=bad), self.assertRaises(FactFailure):
                decode_query_v3(json.dumps(bad).encode())
        with self.assertRaises(FactFailure):
            decode_query_v3(b'{"version":"FACT-query.3","topic":"payment","topic":"internet"}')
        with self.assertRaises(FactFailure):
            decode_query(b'{"version":"FACT-query.2","topic":"payment"}')

    def test_a_cityless_query_must_be_v3(self):
        with self.assertRaises(FactFailure):
            lookup(self.directory, Query('payment', None), evaluated_at=NOW, request_ref='original-ref')
        with self.assertRaises(FactFailure):
            lookup(self.directory, Query('payment', 'chengdu', 'FACT-query.9'), evaluated_at=NOW, request_ref='original-ref')

    def test_wire_examples_and_actual_results_match_the_v3_schema(self):
        from jsonschema import Draft202012Validator, FormatChecker
        schema = json.loads((ROOT / 'contracts/fact/visitor-schema.3.json').read_text())
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        for case in json.loads((ROOT / 'contracts/fact/visitor-examples.3.json').read_text())['cases']:
            with self.subTest(case=case['id']):
                self.assertEqual(validator.is_valid(case['value']), case['valid'])
        for raw in (dict(version='FACT-query.3', topic='payment'), dict(version='FACT-query.3', topic='payment', city='chengdu'),
                    dict(version='FACT-query.3', topic='emergency')):
            with self.subTest(raw=raw):
                validator.validate(self.read(raw))

    def test_v2_schema_and_examples_are_untouched(self):
        schema = json.loads((ROOT / 'contracts/fact/visitor-schema.2.json').read_text())
        self.assertEqual(schema['$defs']['query']['required'], ['version', 'topic', 'city'])
        self.assertEqual(schema['$defs']['query']['properties']['version'], {'const': 'FACT-query.2'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
