from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
import unittest
from cj_fact import DateRange, Declared, Evidence, Excerpt, Query, Status, evaluate, parse_document
from test_fact import POLICY, URL

ZONE = ZoneInfo('America/New_York')

def evidence(retrieved, expiry):
    value = 'SYNTHETIC fact; retain original'
    text = '\n'.join([value, 'fixture-city', '2026-11-01', '{}', expiry.isoformat()])
    doc = parse_document(source_url=URL, retrieved_at=retrieved, content_type='text/plain',
                         body=text.encode(), policy=POLICY, synthetic=True)
    def declaration(value, raw):
        start = text.index(raw)
        return Declared(value, Excerpt(start, start + len(raw), raw))
    return Evidence('independent-time', 'fixture-key', doc,
                    declaration(value, value), declaration(('fixture-city',), 'fixture-city'),
                    declaration(DateRange(date(2026, 11, 1), date(2026, 11, 1)), '2026-11-01'),
                    declaration((), '{}'), expires_at=declaration(expiry, expiry.isoformat()))

def query(at):
    return Query('fixture-key', 'fixture-city', DateRange(date(2026, 11, 1), date(2026, 11, 1)), (), at)

class IndependentFactInstantChecks(unittest.TestCase):
    def test_expired_evidence_not_supported_during_repeated_hour(self):
        retrieved = datetime(2026, 11, 1, 0, 30, tzinfo=ZONE)
        expiry = datetime(2026, 11, 1, 1, 45, tzinfo=ZONE, fold=0)
        evaluated = datetime(2026, 11, 1, 1, 15, tzinfo=ZONE, fold=1)
        self.assertEqual((evaluated.astimezone(timezone.utc) - expiry.astimezone(timezone.utc)).total_seconds(), 1800)
        result = evaluate(query(evaluated), (evidence(retrieved, expiry),))
        self.assertEqual(result.status, Status.EXPIRED, 'Evidence expired thirty actual minutes before evaluation')
        self.assertIsNone(result.original_value)

    def test_future_observation_not_supported_during_repeated_hour(self):
        retrieved = datetime(2026, 11, 1, 1, 30, tzinfo=ZONE, fold=1)
        evaluated = datetime(2026, 11, 1, 1, 45, tzinfo=ZONE, fold=0)
        expiry = datetime(2026, 11, 1, 3, 0, tzinfo=ZONE)
        self.assertEqual((retrieved.astimezone(timezone.utc) - evaluated.astimezone(timezone.utc)).total_seconds(), 2700)
        result = evaluate(query(evaluated), (evidence(retrieved, expiry),))
        self.assertEqual(result.status, Status.UNKNOWN, 'Observation is forty-five actual minutes in the future')
        self.assertIsNone(result.original_value)

if __name__ == '__main__':
    unittest.main(verbosity=2)
