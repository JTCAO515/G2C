"""Affected instant controls; synthetic data and the original parser boundary."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import unittest

from cj_place import Outcome, parse_response, prepare
from test_gaode import CONFIG, SEARCH, poi, pois, response


class InstantControls(unittest.TestCase):
    def parse_at(self, start, received, now, config=CONFIG):
        request = prepare(config, SEARCH, "instant-control", start)
        original_digest = request.binding_digest
        result = parse_response(config, request, response(request, pois(poi()), received=received), now=now)
        self.assertEqual(request.binding_digest, original_digest)
        if result.source is not None:
            self.assertIs(result.source.query_started_at, start)
            self.assertIs(result.source.received_at, received)
            self.assertEqual(result.source.binding_digest, original_digest)
        return result

    def test_limits_are_inclusive_across_spring_transition(self):
        zone = ZoneInfo("America/New_York")
        start = datetime(2026, 3, 8, 1, 59, 59, tzinfo=zone)
        received = datetime(2026, 3, 8, 3, 0, 2, tzinfo=zone)
        now = datetime(2026, 3, 8, 3, 0, 59, tzinfo=zone)
        self.assertEqual((received.astimezone(timezone.utc) - start.astimezone(timezone.utc)).total_seconds(), 3)
        self.assertEqual((now.astimezone(timezone.utc) - start.astimezone(timezone.utc)).total_seconds(), 60)
        self.assertEqual(self.parse_at(start, received, now).outcome, Outcome.OK)
        self.assertEqual(self.parse_at(start, received, now + timedelta(microseconds=1)).outcome, Outcome.STALE)
        late = received + timedelta(microseconds=1)
        self.assertEqual(self.parse_at(start, late, now).outcome, Outcome.UNKNOWN)

    def test_receipt_before_start_is_invalid_despite_later_wall_time(self):
        zone = ZoneInfo("America/New_York")
        start = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=1)
        received = datetime(2026, 11, 1, 1, 45, tzinfo=zone, fold=0)
        now = start.astimezone(timezone.utc) + timedelta(seconds=1)
        self.assertLess(received.astimezone(timezone.utc), start.astimezone(timezone.utc))
        result = self.parse_at(start, received, now)
        self.assertEqual(result.outcome, Outcome.INVALID_RESPONSE)
        self.assertEqual(result.reason, "response_time")
        self.assertFalse(result.places)

    def test_different_timezone_representations_use_same_instants(self):
        zone = ZoneInfo("America/New_York")
        start = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=1)
        received = start.astimezone(timezone.utc) + timedelta(seconds=1)
        now = (received + timedelta(seconds=1)).astimezone(ZoneInfo("Asia/Shanghai"))
        self.assertEqual(self.parse_at(start, received, now).outcome, Outcome.OK)

    def test_fold_source_and_binding_are_not_rewritten_to_utc(self):
        zone = ZoneInfo("America/New_York")
        start = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=0)
        received = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=1)
        result = self.parse_at(start, received, received, replace(CONFIG, timeout_seconds=3600, max_age_seconds=3600))
        self.assertEqual(result.outcome, Outcome.OK)
        self.assertEqual(result.source.query_started_at.fold, 0)
        self.assertEqual(result.source.received_at.fold, 1)
        self.assertEqual(result.source.query_started_at.isoformat(), "2026-11-01T01:30:00-04:00")
        self.assertEqual(result.source.received_at.isoformat(), "2026-11-01T01:30:00-05:00")

    def test_unrepresentable_utc_instant_is_invalid_not_exception(self):
        start = datetime(1, 1, 1, tzinfo=timezone(timedelta(hours=14)))
        result = self.parse_at(start, start, start)
        self.assertEqual(result.outcome, Outcome.INVALID_RESPONSE)
        self.assertEqual(result.reason, "response_time")
