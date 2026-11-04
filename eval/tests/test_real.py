"""Collector boundaries: safe replay and observed user-body timing."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('CJ_ENV', 'local')
import real


class RealCollectorChecks(unittest.TestCase):
    def test_existing_batch_never_reads_credentials_or_creates_authorization_intent(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(sys, 'argv', ['real.py', '--output', folder]), \
                    patch.object(real, 'keychain', side_effect=AssertionError('must not read keys')), \
                    patch.object(real, 'AuthorizationBudget', side_effect=AssertionError('must not open budget')):
                self.assertEqual(real.main(), 0)

    def test_source_link_is_not_the_first_answer_body(self):
        self.assertFalse(real.body_available('Source: https://example.com\n\n'))
        self.assertFalse(real.body_available('来源：https://example.com\n'))
        self.assertTrue(real.body_available('Source: https://example.com\nActual answer'))

    def test_first_body_and_complete_answer_use_the_actual_client_clock(self):
        snapshots = [dict(text='Source: https://example.com\n', status='running'),
                     dict(text='Source: https://example.com\nActual answer', status='running'),
                     dict(text='Source: https://example.com\nActual answer', status='completed')]
        class Response:
            status_code = 200
            def __init__(self, snapshot): self.snapshot = snapshot
            def json(self): return dict(snapshot=self.snapshot)
        class Client:
            def get(self, *args, **kwargs): return Response(snapshots.pop(0))
        class Future:
            def result(self, **kwargs): return ['original outcome']
        evidence = {}
        with patch.object(real.time, 'monotonic', side_effect=[0,1,2,3,4,5,6]), patch.object(real.time, 'sleep'):
            events, text, first, full, outcomes = real.stream_run(Client(), {}, 'original', Future(), 0, evidence)
        self.assertEqual((first, full, outcomes), (4, 6, ['original outcome']))
        self.assertEqual(evidence['events'], events)


if __name__ == '__main__': unittest.main()
