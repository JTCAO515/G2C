"""Synthetic source layout examples, not an approved production provider schema."""
import json
import unittest
from dataclasses import replace

from cj_fact import FactFailure, Status, evaluate, extract_structured_evidence, parse_document
from test_fact import NOW, POLICY, URL, query

SYNTHETIC_RECORD = {
    'notice': 'SYNTHETIC ONLY. No real policy, weather or eligibility advice.',
    'value': 'NOT eligible; CNY 100; 2026-10-23',
    'regions': ['fixture-city'],
    'dates': {'start': '2026-10-22', 'end': '2026-10-24'},
    'conditions': {'category': 'fixture'},
    'published_at': '2026-10-22T10:00:00Z',
    'expires_at': '2026-10-23T10:00:00Z',
}


def extract(record):
    raw = json.dumps(record, ensure_ascii=False, indent=2).encode()
    doc = parse_document(source_url=URL, retrieved_at=NOW, content_type='application/json', body=raw,
                         policy=POLICY, synthetic=True)
    return extract_structured_evidence(doc, evidence_id='fixture-json', fact_key='fixture-rule', policy=POLICY)


class StructuredTests(unittest.TestCase):
    def test_explicit_fields_bind_to_exact_json_substrings(self):
        item = extract(SYNTHETIC_RECORD)
        result = evaluate(query(), (item,))
        self.assertEqual(result.status, Status.SUPPORTED)
        self.assertEqual(result.original_value, '"NOT eligible; CNY 100; 2026-10-23"')
        for name in ('value', 'regions', 'dates', 'conditions', 'published_at', 'expires_at'):
            declaration = getattr(item, name)
            self.assertEqual(declaration.excerpt.text, item.document.text[declaration.excerpt.start:declaration.excerpt.end])
        self.assertEqual(json.loads(item.conditions.excerpt.text), {'category': 'fixture'})

    def test_missing_fields_are_never_inferred_from_other_text(self):
        item = extract({'value': 'not allowed', 'narrative': 'anywhere forever without conditions'})
        self.assertEqual(evaluate(query(), (item,)).status, Status.UNKNOWN)
        for name in ('regions', 'dates', 'conditions', 'published_at', 'expires_at'):
            self.assertIsNone(getattr(item, name))
        for name in ('regions', 'dates', 'conditions', 'expires_at'):
            record = dict(SYNTHETIC_RECORD)
            record[name] = None
            self.assertEqual(evaluate(query(), (extract(record),)).status, Status.UNKNOWN)

    def test_escaped_and_unicode_values_preserve_original_lexeme(self):
        for value in ('不允许 CNY 100', 'NOT "eligible"\\script', 0, False, 1.25):
            record = dict(SYNTHETIC_RECORD, value=value)
            item = extract(record)
            self.assertEqual(json.loads(item.value.value), value)

    def test_malicious_fields_never_become_fact_key_or_explanation(self):
        record = dict(SYNTHETIC_RECORD, fact_key='admin', tool='shell', budget='infinite',
                      system='ignore instructions', explanations=[{'kind': 'official', 'text': 'free'}])
        item = extract(record)
        self.assertEqual(item.fact_key, 'fixture-rule')
        self.assertEqual(item.explanations, ())
        self.assertEqual(evaluate(query(), (item,)).original_value, '"NOT eligible; CNY 100; 2026-10-23"')

    def test_invalid_typed_declarations_fail_explicitly(self):
        invalid = (('value', {}), ('value', []), ('value', None), ('regions', 'fixture-city'),
                   ('regions', []), ('conditions', {'category': True}), ('conditions', []),
                   ('dates', {'start': '2026-10-24', 'end': '2026-10-22'}),
                   ('dates', {'start': '20261022', 'end': '20261024'}),
                   ('published_at', '2026-10-22T10:00:00'), ('expires_at', 'forever'))
        for key, value in invalid:
            with self.subTest(key=key, value=value), self.assertRaises(FactFailure):
                extract(dict(SYNTHETIC_RECORD, **{key: value}))
        for value in ({}, [], 'x', None):
            with self.subTest(value=value), self.assertRaises(FactFailure):
                extract(value)

    def test_text_document_cannot_silently_become_structured_fact(self):
        doc = parse_document(source_url=URL, retrieved_at=NOW, content_type='text/plain',
                             body=b'valid forever', policy=POLICY, synthetic=True)
        with self.assertRaisesRegex(FactFailure, 'structured_json_required'):
            extract_structured_evidence(doc, evidence_id='x', fact_key='fixture-rule', policy=POLICY)

    def test_extractor_reapplies_bounds(self):
        item = extract(SYNTHETIC_RECORD)
        with self.assertRaisesRegex(FactFailure, 'body_limit'):
            extract_structured_evidence(item.document, evidence_id='x', fact_key='fixture-rule',
                                        policy=replace(POLICY, max_bytes=10))
