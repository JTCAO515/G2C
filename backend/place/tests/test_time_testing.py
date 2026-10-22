from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import unittest
from cj_place import prepare, parse_response, Outcome
from test_gaode import CONFIG, SEARCH, response, pois, poi

class IndependentElapsedTimeChecks(unittest.TestCase):
    def test_fold_does_not_hide_one_hour_deadline_and_age(self):
        zone = ZoneInfo('America/New_York')
        started = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=0)
        received = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=1)
        self.assertEqual((received.astimezone(timezone.utc) - started.astimezone(timezone.utc)).total_seconds(), 3600)
        request = prepare(CONFIG, SEARCH, 'independent-fold', started)
        result = parse_response(CONFIG, request, response(request, pois(poi()), received=received), now=received)
        self.assertEqual(result.outcome, Outcome.UNKNOWN, 'Actual one-hour response exceeds the explicit three-second timeout')
        self.assertFalse(result.places)

    def test_fold_does_not_hide_one_hour_query_age(self):
        zone = ZoneInfo('America/New_York')
        started = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=0)
        now = datetime(2026, 11, 1, 1, 30, tzinfo=zone, fold=1)
        self.assertEqual((now.astimezone(timezone.utc) - started.astimezone(timezone.utc)).total_seconds(), 3600)
        request = prepare(CONFIG, SEARCH, 'independent-fold-age', started)
        result = parse_response(CONFIG, request, response(request, pois(poi()), received=started), now=now)
        self.assertEqual(result.outcome, Outcome.STALE, 'Actual one-hour age exceeds explicit sixty-second maximum age')
        self.assertFalse(result.places)

    def test_spring_forward_one_second_is_not_a_one_hour_timeout(self):
        zone = ZoneInfo('America/New_York')
        started = datetime(2026, 3, 8, 1, 59, 59, tzinfo=zone)
        received = datetime(2026, 3, 8, 3, 0, 0, tzinfo=zone)
        self.assertEqual((received.astimezone(timezone.utc) - started.astimezone(timezone.utc)).total_seconds(), 1)
        request = prepare(CONFIG, SEARCH, 'independent-spring', started)
        result = parse_response(CONFIG, request, response(request, pois(poi()), received=received), now=received)
        self.assertEqual(result.outcome, Outcome.OK, 'Actual one-second response is within explicit timeout and maximum age')
        self.assertEqual(len(result.places), 1)

if __name__ == '__main__':
    unittest.main(verbosity=2)
