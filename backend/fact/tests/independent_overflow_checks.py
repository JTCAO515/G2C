import json
import unittest
from datetime import datetime, timezone
from cj_fact import FactFailure, extract_structured_evidence, parse_document
from test_fact import POLICY, URL

class IndependentInstantBoundary(unittest.TestCase):
    def test_source_timestamp_conversion_does_not_escape_raw_overflow(self):
        for field in ('published_at', 'expires_at'):
            with self.subTest(field=field):
                record = {'value':'SYNTHETIC ONLY', 'regions':['fixture-city'],
                          'dates':{'start':'2026-11-01','end':'2026-11-01'}, 'conditions':{},
                          'published_at':'2026-01-01T00:00:00+00:00',
                          'expires_at':'2027-01-01T00:00:00+00:00'}
                record[field] = '0001-01-01T00:00:00+14:00'
                doc = parse_document(source_url=URL, retrieved_at=datetime(2026, 10, 22, tzinfo=timezone.utc),
                                     content_type='application/json', body=json.dumps(record).encode(),
                                     policy=POLICY, synthetic=True)
                try:
                    extract_structured_evidence(doc, evidence_id='independent-boundary', fact_key='fixture-key', policy=POLICY)
                except (FactFailure, ValueError):
                    pass  # Explicit bounded source rejection is acceptable.
                except OverflowError:
                    self.fail('Untrusted source '+field+' escaped as raw UTC-conversion OverflowError')

if __name__ == '__main__': unittest.main(verbosity=2)
