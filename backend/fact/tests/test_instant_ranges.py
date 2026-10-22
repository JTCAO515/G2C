"""Synthetic UTC representability boundary controls; no source/network calls."""
import json
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from cj_fact import FactFailure, Status, evaluate, extract_structured_evidence, parse_document
from test_fact import NOW, POLICY, URL, source
from test_time_instants import evidence, query

OUT_OF_RANGE = (
    datetime.fromisoformat('0001-01-01T00:00:00+14:00'),
    datetime.fromisoformat('9999-12-31T23:59:59.999999-14:00'),
)


class InstantRangeControls(unittest.TestCase):
    def test_document_and_query_reject_unrepresentable_instants(self):
        item = source()
        for stamp in OUT_OF_RANGE:
            with self.subTest(stamp=stamp):
                with self.assertRaisesRegex(ValueError, '^instant_out_of_range$'):
                    replace(item.document, retrieved_at=stamp)
                with self.assertRaisesRegex(ValueError, '^instant_out_of_range$'):
                    replace(query(NOW), evaluated_at=stamp)

    def test_manual_evidence_checks_optional_timestamps_without_companion(self):
        item = source()
        for name, other in (('published_at', 'expires_at'), ('expires_at', 'published_at')):
            for stamp in OUT_OF_RANGE:
                with self.subTest(field=name, stamp=stamp):
                    declaration = replace(getattr(item, name), value=stamp)
                    with self.assertRaisesRegex(ValueError, '^instant_out_of_range$'):
                        replace(item, **{name: declaration, other: None})

    def test_structured_optional_timestamps_always_use_typed_rejection(self):
        for field in ('published_at', 'expires_at'):
            for stamp in OUT_OF_RANGE:
                with self.subTest(field=field, stamp=stamp):
                    record = {'value': 'SYNTHETIC ONLY', field: stamp.isoformat()}
                    document = parse_document(source_url=URL, retrieved_at=NOW, content_type='application/json',
                                              body=json.dumps(record).encode(), policy=POLICY, synthetic=True)
                    with self.assertRaisesRegex(FactFailure, '^invalid_structured_evidence$'):
                        extract_structured_evidence(document, evidence_id='range', fact_key='fixture-key', policy=POLICY)
                    self.assertIn(stamp.isoformat().encode(), document.original)

    def test_representable_lower_boundary_evaluates_and_preserves_offsets(self):
        retrieved = datetime(1, 1, 1, 14, tzinfo=timezone(timedelta(hours=14)))
        expiry = retrieved + timedelta(minutes=1)
        item = evidence(retrieved, expiry, retrieved.astimezone(timezone.utc))
        before = datetime(1, 1, 1, 0, 0, 30, tzinfo=timezone.utc)
        self.assertEqual(evaluate(query(before), (item,)).status, Status.SUPPORTED)
        self.assertEqual(evaluate(query(expiry.astimezone(timezone.utc)), (item,)).status, Status.EXPIRED)
        self.assertIs(item.document.retrieved_at, retrieved)
        self.assertEqual(item.document.retrieved_at.utcoffset(), timedelta(hours=14))

    def test_representable_upper_boundary_evaluates_and_preserves_offsets(self):
        expiry = datetime(9999, 12, 31, 9, 59, 59, 999999, tzinfo=timezone(-timedelta(hours=14)))
        retrieved = expiry - timedelta(minutes=1)
        item = evidence(retrieved, expiry, retrieved.astimezone(timezone.utc))
        before = datetime.max.replace(tzinfo=timezone.utc) - timedelta(seconds=30)
        self.assertEqual(evaluate(query(before), (item,)).status, Status.SUPPORTED)
        self.assertEqual(evaluate(query(datetime.max.replace(tzinfo=timezone.utc)), (item,)).status, Status.EXPIRED)
        self.assertIs(item.expires_at.value, expiry)
        self.assertEqual(item.expires_at.value.utcoffset(), -timedelta(hours=14))


if __name__ == '__main__':
    unittest.main(verbosity=2)
