"""Synthetic DST/offset controls adjacent to the independent instant regressions."""
import json
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
import unittest
from zoneinfo import ZoneInfo

from cj_fact import (DateRange, Declared, Evidence, Excerpt, Query, Status, evaluate,
                     extract_structured_evidence, parse_document)
from test_fact import POLICY, URL

ZONE = ZoneInfo('America/New_York')


def local(hour, minute, fold=0):
    return datetime(2026, 11, 1, hour, minute, tzinfo=ZONE, fold=fold)


def evidence(retrieved, expiry, published=None):
    value = 'SYNTHETIC ONLY; original NOT eligible; CNY 100'
    lines = [value, 'fixture-city', '2026-11-01', '{}', expiry.isoformat()]
    if published is not None:
        lines.append(published.isoformat())
    text = '\n'.join(lines)
    document = parse_document(source_url=URL, retrieved_at=retrieved, content_type='text/plain',
                              body=text.encode(), policy=POLICY, synthetic=True)
    def declaration(value, raw):
        start = text.index(raw)
        return Declared(value, Excerpt(start, start + len(raw), raw))
    return Evidence('time-control', 'fixture-key', document, declaration(value, value),
                    declaration(('fixture-city',), 'fixture-city'),
                    declaration(DateRange(date(2026, 11, 1), date(2026, 11, 1)), '2026-11-01'),
                    declaration((), '{}'),
                    None if published is None else declaration(published, published.isoformat()),
                    declaration(expiry, expiry.isoformat()))


def query(at):
    return Query('fixture-key', 'fixture-city', DateRange(date(2026, 11, 1), date(2026, 11, 1)), (), at)


class InstantControls(unittest.TestCase):
    def test_future_publication_during_repeated_hour(self):
        item = evidence(local(1, 45), local(3, 0), local(1, 15, fold=1))
        result = evaluate(query(local(2, 0)), (item,))
        self.assertEqual(result.status, Status.UNKNOWN)
        self.assertIsNone(result.original_value)

    def test_earlier_publication_with_later_wall_time_is_supported(self):
        item = evidence(local(1, 15, fold=1), local(3, 0), local(1, 45))
        self.assertEqual(evaluate(query(local(2, 0)), (item,)).status, Status.SUPPORTED)

    def test_earlier_retrieval_with_later_wall_time_is_supported(self):
        item = evidence(local(1, 45), local(3, 0))
        self.assertEqual(evaluate(query(local(1, 15, fold=1)), (item,)).status, Status.SUPPORTED)

    def test_future_expiry_with_earlier_wall_time_is_supported(self):
        item = evidence(local(0, 30), local(1, 15, fold=1))
        self.assertEqual(evaluate(query(local(1, 45)), (item,)).status, Status.SUPPORTED)

    def test_invalid_validity_rejected_by_actual_instant(self):
        with self.assertRaisesRegex(ValueError, '^invalid_validity$'):
            evidence(local(2, 0), local(1, 45), local(1, 15, fold=1))

    def test_valid_validity_accepted_and_source_metadata_unchanged(self):
        retrieved, expiry, published = local(1, 0, fold=1), local(1, 15, fold=1), local(1, 45)
        item = evidence(retrieved, expiry, published)
        original = item.document.original
        result = evaluate(query(local(1, 5, fold=1)), (item,))
        self.assertEqual(result.status, Status.SUPPORTED)
        self.assertIs(item.document.retrieved_at, retrieved)
        self.assertIs(item.published_at.value, published)
        self.assertIs(item.expires_at.value, expiry)
        self.assertEqual(item.expires_at.value.fold, 1)
        self.assertEqual(item.expires_at.excerpt.text, '2026-11-01T01:15:00-05:00')
        self.assertEqual(item.document.original, original)
        self.assertIn(published.isoformat().encode(), original)
        self.assertIn(expiry.isoformat().encode(), original)

    def test_equal_instant_expiry_and_validity_with_different_offsets(self):
        expiry = local(1, 45)
        item = evidence(local(0, 30), expiry)
        for at in (expiry, expiry.astimezone(timezone.utc),
                   expiry.astimezone(timezone(timedelta(hours=8)))):
            with self.subTest(at=at):
                self.assertEqual(evaluate(query(at), (item,)).status, Status.EXPIRED)
        with self.assertRaisesRegex(ValueError, '^invalid_validity$'):
            evidence(local(2, 0), expiry, expiry.astimezone(timezone.utc))

    def test_structured_source_future_retrieval_with_zoneinfo_query(self):
        retrieved = local(1, 30, fold=1)
        record = {
            'notice': 'SYNTHETIC ONLY', 'value': 'NOT eligible; CNY 100',
            'regions': ['fixture-city'],
            'dates': {'start': '2026-11-01', 'end': '2026-11-01'},
            'conditions': {}, 'published_at': '2026-11-01T00:30:00-04:00',
            'expires_at': '2026-11-01T03:00:00-05:00',
        }
        document = parse_document(source_url=URL, retrieved_at=retrieved, content_type='application/json',
                                  body=json.dumps(record).encode(), policy=POLICY, synthetic=True)
        item = extract_structured_evidence(document, evidence_id='json-time', fact_key='fixture-key',
                                           policy=POLICY)
        result = evaluate(query(local(1, 45)), (item,))
        self.assertEqual(result.status, Status.UNKNOWN)
        self.assertIsNone(result.original_value)
        self.assertIs(item.document.retrieved_at, retrieved)
        self.assertIn(record['expires_at'], item.expires_at.excerpt.text)

    def test_source_calendar_window_not_converted_to_utc_dates(self):
        offset = timezone(timedelta(hours=14))
        retrieved = datetime(2026, 11, 1, 0, 15, tzinfo=offset)
        expiry = datetime(2026, 11, 1, 2, 0, tzinfo=offset)
        item = evidence(retrieved, expiry)
        at = datetime(2026, 11, 1, 0, 30, tzinfo=offset)
        self.assertEqual(at.astimezone(timezone.utc).date(), date(2026, 10, 31))
        self.assertEqual(evaluate(query(at), (item,)).status, Status.SUPPORTED)
        self.assertEqual(item.dates.value.start, date(2026, 11, 1))
        outside = replace(query(at), dates=DateRange(date(2026, 10, 31), date(2026, 10, 31)))
        self.assertEqual(evaluate(outside, (item,)).status, Status.OUT_OF_RANGE)


if __name__ == '__main__':
    unittest.main(verbosity=2)
